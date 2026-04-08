from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Dict, List
from src.models import GridAction, GridObservation, GridReward
from src.environment import OpenGridEnv
from src.tasks import TASKS
from src.grader import RobustnessGrader, normalize_score, _SCORE_EPSILON, _clamp_score
from src.baseline import heuristic_policy, llm_policy
from src.visualization import generate_dashboard
import uuid
import os
import time
import pathlib
import threading

app = FastAPI(
    title="OpenGrid Environment",
    description="Renewable energy grid load-balancing environment for AI agents",
    version="1.0.0"
)

# Pre-flight check: verify static directory exists before mounting
STATIC_DIR = pathlib.Path(__file__).parent / "static"
if not STATIC_DIR.exists():
    raise RuntimeError(
        f"Static directory not found: {STATIC_DIR}. "
        "Create it with index.html, style.css, and app.js, or disable static serving."
    )
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Session storage with TTL
# Lock guards ALL session reads and writes — not just cleanup — to prevent
# race conditions under concurrent requests (e.g. two agents stepping
# simultaneously, or a step racing with a grader call).
sessions: Dict[str, Dict] = {}
history: Dict[str, List] = {}
MAX_SESSIONS = 100
_session_lock = threading.Lock()

# Grader cache: bounds are expensive (10 rollouts per task), compute once.
# Double-checked locking prevents duplicate computation under concurrent /grader calls.
_grader_cache: Dict[str, RobustnessGrader] = {}
_grader_lock = threading.Lock()


def _cleanup_sessions():
    """Evict oldest sessions if over limit. Caller must hold _session_lock."""
    if len(sessions) > MAX_SESSIONS:
        oldest = sorted(sessions.keys(), key=lambda k: sessions[k].get('created', 0))
        for sid in oldest[:len(sessions) - MAX_SESSIONS]:
            sessions.pop(sid, None)
            history.pop(sid, None)


def _get_grader(task_id: str) -> RobustnessGrader:
    """Get or create a cached RobustnessGrader for a task.

    Uses double-checked locking: the fast path (cache hit) is lock-free,
    but construction is serialized to avoid duplicate _estimate_bounds()
    calls which each run 10 environment rollouts.
    """
    if task_id not in _grader_cache:
        with _grader_lock:
            if task_id not in _grader_cache:  # double-check after acquiring lock
                _grader_cache[task_id] = RobustnessGrader(TASKS[task_id])
    return _grader_cache[task_id]


@app.get("/")
def root():
    """Serve the interactive dashboard."""
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/health")
def health():
    """Health check endpoint (JSON)."""
    return {"status": "OpenGrid Running", "version": "1.0.0", "docs": "/docs"}


@app.get("/tasks")
def get_tasks():
    """List available tasks with metadata."""
    action_schema = GridAction.model_json_schema()
    obs_schema = GridObservation.model_json_schema()
    return [
        {
            "id": k,
            "difficulty": v.get("difficulty", k.split('_')[1]),
            "num_buses": v["num_buses"],
            "max_steps": v["max_steps"],
            "action_schema": action_schema,
            "observation_schema": obs_schema
        } for k, v in TASKS.items()
    ]


@app.post("/reset")
def reset(task_id: str = "task_easy"):
    """Reset (or create) an environment session. Returns initial observation."""
    if task_id not in TASKS:
        raise HTTPException(404, f"Task '{task_id}' not found. Available: {list(TASKS.keys())}")

    env = OpenGridEnv(TASKS[task_id])
    obs = env.reset()
    sid = str(uuid.uuid4())

    with _session_lock:
        _cleanup_sessions()
        sessions[sid] = {"env": env, "created": time.time(), "task_id": task_id, "rewards": []}
        history[sid] = [obs]

    return {"session_id": sid, "observation": obs.model_dump()}


@app.post("/step")
def step(session_id: str, action: GridAction):
    """Execute one step in the environment."""
    with _session_lock:
        if session_id not in sessions:
            raise HTTPException(404, "Session not found")
        env = sessions[session_id]["env"]

    # Step is CPU-bound on one env instance — safe outside the lock
    # since each session is used by one agent at a time.
    obs, reward, done, info = env.step(action)

    with _session_lock:
        history[session_id].append(obs)
        sessions[session_id]["rewards"].append(reward.value)

    return {
        "observation": obs.model_dump(),
        "reward": reward.model_dump(),
        "done": done,
        "info": info.model_dump()
    }


@app.get("/state")
def get_state(session_id: str):
    """Get current state of a session."""
    with _session_lock:
        if session_id not in sessions:
            raise HTTPException(404, "Session not found")
        env = sessions[session_id]["env"]
    return env.state().model_dump()


@app.get("/grader")
def run_grader(session_id: str):
    """
    Grade a completed (or in-progress) session.
    Returns a score strictly in the open interval (0, 1) using the same
    normalization as the /baseline endpoint (analytical ceiling + empirical floor).
    """
    with _session_lock:
        if session_id not in sessions:
            raise HTTPException(404, "Session not found")
        session = sessions[session_id]
        rewards = list(session["rewards"])  # snapshot under lock
        task_id = session["task_id"]
        env = session["env"]

    if not rewards:
        return {"score": _SCORE_EPSILON, "message": "No steps taken yet. Run /step first."}

    cumulative = sum(rewards)
    n_steps = len(rewards)
    is_blackout = env.state().is_blackout

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
    Run baseline policy on all 3 tasks. Returns 0.0–1.0 scores.
    Default: heuristic (reproducible). Set use_llm=true for LLM agent.

    Uses the same cached grader as /grader — bounds are computed once
    and reused across all endpoints.
    """
    api_key = os.getenv("HF_TOKEN", os.getenv("OPENAI_API_KEY", ""))
    policy = llm_policy if use_llm and api_key else heuristic_policy

    results = {}
    for task_id, config in TASKS.items():
        grader = _get_grader(task_id)  # cached — no duplicate rollouts
        res = grader.evaluate_policy(policy, n_episodes=3)
        results[task_id] = res

    return {"baseline_scores": results}


@app.get("/visualize")
def visualize(session_id: str):
    """Generate a visualization of the current grid state and frequency history."""
    with _session_lock:
        if session_id not in sessions:
            raise HTTPException(404, "Session not found")
        env = sessions[session_id]["env"]
        hist = list(history[session_id])  # snapshot under lock

    obs = env.state()
    img_str = generate_dashboard(hist, obs)
    return {"image_base64": img_str}