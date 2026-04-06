from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Dict, List
from src.models import (
    GridAction, GridObservation, GridReward,
    MultiAgentAction, MultiAgentStepResult,
)
from src.environment import OpenGridEnv
from src.tasks import TASKS
from src.grader import RobustnessGrader, normalize_score, _SCORE_EPSILON, _clamp_score
from src.baseline import heuristic_policy, llm_policy
from src.visualization import generate_dashboard
import copy
import uuid
import os
import time
import pathlib
import threading
import warnings

app = FastAPI(
    title="OpenGrid Environment",
    description="Multi-agent renewable energy grid load-balancing environment with safety constraints",
    version="2.0.0"
)

# Static files — mount only if present (allows API-only or test deployments)
STATIC_DIR = pathlib.Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
else:
    warnings.warn(
        f"Static directory not found: {STATIC_DIR}. "
        "Dashboard UI disabled; API endpoints remain available."
    )

# ---------------------------------------------------------------------------
# Session storage with TTL + per-session locking
# ---------------------------------------------------------------------------
# _session_lock guards the sessions/history *dicts* for insert/delete/lookup.
# Each session also has its own lock ("lock" key) that serializes env
# operations, preventing race conditions when concurrent requests target
# the same session (e.g. two /step calls, or /step racing with /grader).
# ---------------------------------------------------------------------------
sessions: Dict[str, Dict] = {}
history: Dict[str, List] = {}
MAX_SESSIONS = 100
SESSION_TTL_SECONDS = 3600  # 1 hour
_session_lock = threading.Lock()

# Grader cache: bounds are expensive (10 rollouts per task), compute once.
# Construction AND bounds estimation are serialized under _grader_lock.
_grader_cache: Dict[str, RobustnessGrader] = {}
_grader_lock = threading.Lock()


def _new_session(env: OpenGridEnv, task_id: str, mode: str, **extra) -> dict:
    """Create a session dict with per-session lock and metadata."""
    session = {
        "env": env,
        "created": time.time(),
        "last_access": time.time(),
        "task_id": task_id,
        "rewards": [],
        "mode": mode,
        "done": False,
        "is_blackout": False,
        "lock": threading.Lock(),
    }
    session.update(extra)
    return session


def _session_age(s: dict, now: float) -> float:
    """Return the last-access timestamp for a session (for eviction sorting)."""
    ts = s.get("last_access")
    if ts is None:
        ts = s.get("created")
    return float(ts) if ts is not None else now


def _cleanup_sessions():
    """Evict expired and excess sessions. Caller must hold _session_lock."""
    now = time.time()

    # Phase 1: evict expired sessions (actual TTL)
    expired = [
        sid for sid, s in sessions.items()
        if now - _session_age(s, now) > SESSION_TTL_SECONDS
    ]
    for sid in expired:
        sessions.pop(sid, None)
        history.pop(sid, None)

    # Phase 2: evict oldest if still over limit
    while len(sessions) >= MAX_SESSIONS:
        oldest_sid = min(
            sessions,
            key=lambda k: _session_age(sessions[k], 0.0),
        )
        sessions.pop(oldest_sid, None)
        history.pop(oldest_sid, None)


def _get_session(session_id: str) -> dict:
    """Look up session, update last_access, raise 404 if missing.
    Caller must NOT hold _session_lock (this acquires it)."""
    with _session_lock:
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(404, "Session not found")
        session["last_access"] = time.time()
        return session


def _get_grader(task_id: str) -> RobustnessGrader:
    """Get or create a cached RobustnessGrader for a task.

    Both construction and bounds estimation run under _grader_lock
    so concurrent /grader requests don't duplicate or race on
    _estimate_bounds() mutations.
    """
    with _grader_lock:
        if task_id not in _grader_cache:
            grader = RobustnessGrader(copy.deepcopy(TASKS[task_id]))
            grader.get_bounds()  # force expensive mutation while locked
            _grader_cache[task_id] = grader
        return _grader_cache[task_id]


@app.get("/")
def root():
    """Serve the interactive dashboard (or API info if static files absent)."""
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"status": "OpenGrid API", "version": "2.0.0", "docs": "/docs"}


@app.get("/health")
def health():
    """Health check endpoint (JSON)."""
    return {"status": "OpenGrid Running", "version": "2.0.0", "docs": "/docs"}


@app.get("/tasks")
def get_tasks():
    """List available tasks with metadata including multi-agent zone info."""
    action_schema = GridAction.model_json_schema()
    obs_schema = GridObservation.model_json_schema()
    return [
        {
            "id": k,
            "difficulty": v.get("difficulty", k.split('_')[1]),
            "num_buses": v["num_buses"],
            "max_steps": v["max_steps"],
            "num_agents": v.get("num_agents", 1),
            "zone_names": v.get("zone_names", []),
            "buses": v.get("buses", []),
            "action_schema": action_schema,
            "observation_schema": obs_schema
        } for k, v in TASKS.items()
    ]


# ===========================================================================
# Single-Agent API (backward compatible)
# ===========================================================================

@app.post("/reset")
def reset(task_id: str = "task_easy"):
    """Reset (or create) an environment session. Returns initial observation."""
    if task_id not in TASKS:
        raise HTTPException(404, f"Task '{task_id}' not found. Available: {list(TASKS.keys())}")

    env = OpenGridEnv(copy.deepcopy(TASKS[task_id]))
    obs = env.reset()
    sid = str(uuid.uuid4())

    with _session_lock:
        _cleanup_sessions()
        sessions[sid] = _new_session(env, task_id, mode="single")
        history[sid] = [obs]

    return {"session_id": sid, "observation": obs.model_dump()}


@app.post("/step")
def step(session_id: str, action: GridAction):
    """Execute one step in the environment."""
    session = _get_session(session_id)

    # Per-session lock serializes all env operations for this session
    with session["lock"]:
        if session.get("done"):
            raise HTTPException(400, "Episode already done. Call /reset to start a new session.")

        env = session["env"]
        obs, reward, done, info = env.step(action)

        session["rewards"].append(reward.value)
        session["done"] = done
        session["is_blackout"] = info.is_blackout

        with _session_lock:
            history[session_id].append(obs)

    return {
        "observation": obs.model_dump(),
        "reward": reward.model_dump(),
        "done": done,
        "info": info.model_dump()
    }


@app.get("/state")
def get_state(session_id: str):
    """Get current state of a session."""
    session = _get_session(session_id)

    with session["lock"]:
        return session["env"].state().model_dump()


# ===========================================================================
# Multi-Agent POMDP API
# ===========================================================================

@app.post("/reset_multi")
def reset_multi(task_id: str = "task_easy"):
    """Reset environment in multi-agent mode. Returns per-agent partial observations."""
    if task_id not in TASKS:
        raise HTTPException(404, f"Task '{task_id}' not found. Available: {list(TASKS.keys())}")

    env = OpenGridEnv(copy.deepcopy(TASKS[task_id]))
    zone_obs = env.reset_multi()
    sid = str(uuid.uuid4())

    zone_info = env.get_zone_info()

    with _session_lock:
        _cleanup_sessions()
        sessions[sid] = _new_session(
            env, task_id, mode="multi",
            per_agent_rewards={i: [] for i in range(env.num_agents)},
        )
        # Store full-grid observation for visualization history
        history[sid] = [env.state()]

    return {
        "session_id": sid,
        "num_agents": env.num_agents,
        "zone_info": {str(k): v.model_dump() for k, v in zone_info.items()},
        "observations": {str(k): v.model_dump() for k, v in zone_obs.items()},
    }


@app.post("/step_multi")
def step_multi(session_id: str, actions: MultiAgentAction):
    """Multi-agent step with safety layer and oversight.

    Each agent submits actions for their zone. The safety layer validates,
    the oversight agent evaluates coordination, and per-agent rewards are computed.
    """
    session = _get_session(session_id)

    with session["lock"]:
        if session.get("done"):
            raise HTTPException(400, "Episode already done. Call /reset_multi to start a new session.")

        env = session["env"]
        if session.get("mode") != "multi":
            raise HTTPException(400, "Session not in multi-agent mode. Use /reset_multi first.")

        # Convert string keys from JSON to int keys, with validation
        agent_actions = {}
        for k, v in actions.agent_actions.items():
            try:
                agent_id = int(k) if isinstance(k, str) else k
            except (TypeError, ValueError):
                raise HTTPException(400, f"Invalid agent_id: {k!r}")
            if not (0 <= agent_id < env.num_agents):
                raise HTTPException(
                    400,
                    f"Invalid agent_id {agent_id}; expected 0..{env.num_agents - 1}",
                )
            agent_actions[agent_id] = v

        result = env.step_multi(agent_actions)

        session["rewards"].append(result.team_reward)
        session["done"] = result.done
        session["is_blackout"] = result.info.is_blackout
        for agent_id, reward in result.rewards.items():
            if agent_id in session.get("per_agent_rewards", {}):
                session["per_agent_rewards"][agent_id].append(reward.value)

        # Store full-grid observation for visualization
        with _session_lock:
            history[session_id].append(env.state())

    return {
        "observations": {str(k): v.model_dump() for k, v in result.observations.items()},
        "rewards": {str(k): v.model_dump() for k, v in result.rewards.items()},
        "team_reward": result.team_reward,
        "done": result.done,
        "safety_reports": {str(k): v.model_dump() for k, v in result.safety_reports.items()},
        "oversight_report": result.oversight_report.model_dump(),
        "info": result.info.model_dump(),
    }


@app.get("/zones")
def get_zones(session_id: str):
    """Get zone assignments and agent info for a multi-agent session."""
    session = _get_session(session_id)

    with session["lock"]:
        zone_info = session["env"].get_zone_info()

    return {
        "num_agents": session["env"].num_agents,
        "zones": {str(k): v.model_dump() for k, v in zone_info.items()},
    }


# ===========================================================================
# Grading & Baseline
# ===========================================================================

@app.get("/grader")
def run_grader(session_id: str):
    """
    Grade a completed (or in-progress) session.
    Returns a score strictly in the open interval (0, 1) using the same
    normalization as the /baseline endpoint (analytical ceiling + empirical floor).
    """
    session = _get_session(session_id)

    with session["lock"]:
        rewards = list(session["rewards"])  # snapshot under lock
        task_id = session["task_id"]
        is_blackout = session.get("is_blackout", False)

    if not rewards:
        return {"score": _SCORE_EPSILON, "message": "No steps taken yet. Run /step first."}

    cumulative = sum(rewards)
    n_steps = len(rewards)

    grader = _get_grader(task_id)
    bounds = grader.get_bounds()
    n1_rate = 0.0 if is_blackout else 1.0

    score = normalize_score(
        cumulative_reward=cumulative,
        reward_floor=bounds["reward_floor"],
        reward_ceiling=bounds["reward_ceiling"],
        n1_survival_rate=n1_rate
    )

    # Defense-in-depth: clamp again at the API boundary
    score = _clamp_score(score)

    return {
        "score": score,
        "cumulative_reward": round(cumulative, 4),
        "steps": n_steps,
        "is_blackout": is_blackout,
        "task_id": task_id,
        "reward_floor": bounds["reward_floor"],
        "reward_ceiling": bounds["reward_ceiling"]
    }


@app.get("/baseline")
def run_baseline(use_llm: bool = False):
    """
    Run baseline policy on all registered tasks. Returns 0.0–1.0 scores.
    Default: heuristic (reproducible). Set use_llm=true for LLM agent.

    Uses the same cached grader as /grader — bounds are computed once
    and reused across all endpoints.
    """
    api_key = os.getenv("HF_TOKEN", os.getenv("OPENAI_API_KEY", ""))
    if use_llm and not api_key:
        raise HTTPException(
            400,
            "use_llm=true requires HF_TOKEN or OPENAI_API_KEY environment variable",
        )

    policy = llm_policy if use_llm and api_key else heuristic_policy
    policy_name = "llm" if policy is llm_policy else "heuristic"

    results = {}
    for task_id, config in TASKS.items():
        grader = _get_grader(task_id)  # cached — no duplicate rollouts
        res = grader.evaluate_policy(policy, n_episodes=3)
        results[task_id] = res

    return {"policy": policy_name, "baseline_scores": results}


@app.get("/visualize")
def visualize(session_id: str):
    """Generate a visualization of the current grid state and frequency history."""
    session = _get_session(session_id)

    with session["lock"]:
        obs = session["env"].state()
        with _session_lock:
            hist = list(history.get(session_id, []))

    img_str = generate_dashboard(hist, obs)
    return {"image_base64": img_str}