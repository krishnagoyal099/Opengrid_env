from fastapi import FastAPI, HTTPException
from typing import Dict, List
from src.models import GridAction, GridObservation, GridReward
from src.environment import OpenGridEnv
from src.tasks import TASKS
from src.grader import RobustnessGrader, normalize_score
from src.baseline import heuristic_policy, llm_policy
from src.visualization import generate_dashboard
import uuid
import os
import time

app = FastAPI(
    title="OpenGrid Environment",
    description="Renewable energy grid load-balancing environment for AI agents",
    version="1.0.0"
)

# Session storage with TTL
sessions: Dict[str, Dict] = {}
history: Dict[str, List] = {}
MAX_SESSIONS = 100


def _cleanup_sessions():
    """Evict oldest sessions if over limit."""
    if len(sessions) > MAX_SESSIONS:
        oldest = sorted(sessions.keys(), key=lambda k: sessions[k].get('created', 0))
        for sid in oldest[:len(sessions) - MAX_SESSIONS]:
            sessions.pop(sid, None)
            history.pop(sid, None)


@app.get("/")
def root():
    """Health check endpoint."""
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

    _cleanup_sessions()

    env = OpenGridEnv(TASKS[task_id])
    obs = env.reset()

    sid = str(uuid.uuid4())
    sessions[sid] = {"env": env, "created": time.time(), "task_id": task_id, "rewards": []}
    history[sid] = [obs]

    return {"session_id": sid, "observation": obs.model_dump()}


@app.post("/step")
def step(session_id: str, action: GridAction):
    """Execute one step in the environment."""
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")

    env = sessions[session_id]["env"]
    obs, reward, done, info = env.step(action)

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
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    return sessions[session_id]["env"].state().model_dump()


# Cache grader instances per task (so bounds are computed once)
_grader_cache: Dict[str, RobustnessGrader] = {}


def _get_grader(task_id: str) -> RobustnessGrader:
    """Get or create a cached RobustnessGrader for a task."""
    if task_id not in _grader_cache:
        _grader_cache[task_id] = RobustnessGrader(TASKS[task_id])
    return _grader_cache[task_id]


@app.get("/grader")
def run_grader(session_id: str):
    """
    Grade a completed (or in-progress) session.
    Returns a score between 0.0 and 1.0 using the same normalization
    as the /baseline endpoint (empirical reward bounds).
    """
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")

    session = sessions[session_id]
    rewards = session["rewards"]
    task_id = session["task_id"]
    env = session["env"]

    if not rewards:
        return {"score": 0.0, "message": "No steps taken yet. Run /step first."}

    cumulative = sum(rewards)
    n_steps = len(rewards)
    is_blackout = env.state().is_blackout

    # Use the SAME empirical bounds and normalization as /baseline
    grader = _get_grader(task_id)
    bounds = grader.get_bounds()
    n1_rate = 0.0 if is_blackout else 1.0

    score = normalize_score(
        cumulative_reward=cumulative,
        reward_floor=bounds["reward_floor"],
        reward_ceiling=bounds["reward_ceiling"],
        n1_survival_rate=n1_rate
    )

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
    """
    api_key = os.getenv("HF_TOKEN", os.getenv("OPENAI_API_KEY", ""))
    policy = llm_policy if use_llm and api_key else heuristic_policy

    results = {}
    for task_id, config in TASKS.items():
        grader = RobustnessGrader(config)
        res = grader.evaluate_policy(policy, n_episodes=3)
        results[task_id] = res

    return {"baseline_scores": results}


@app.get("/visualize")
def visualize(session_id: str):
    """Generate a visualization of the current grid state and frequency history."""
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")

    env = sessions[session_id]["env"]
    obs = env.state()
    img_str = generate_dashboard(history[session_id], obs)
    return {"image_base64": img_str}