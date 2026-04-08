"""
OpenGrid Inference Script
=========================
Runs an LLM agent against all 3 OpenGrid tasks via the OpenAI-compatible API.

Required environment variables:
  API_BASE_URL  — The API endpoint for the LLM
  MODEL_NAME    — The model identifier to use for inference
  HF_TOKEN      — Your Hugging Face / API key

Emits structured [START], [STEP], [END] logs to stdout.
"""

import os
import sys
import json
import math
import httpx

from openai import OpenAI

# ---------- Configuration ----------

API_BASE_URL = os.environ.get("API_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.environ.get("MODEL_NAME", "gpt-4o")
API_KEY = os.environ.get("HF_TOKEN", os.environ.get("OPENAI_API_KEY", ""))

ENV_URL = os.environ.get("ENV_URL", "http://localhost:7860")
BENCHMARK = "OpenGrid"
MAX_STEPS = 50
SUCCESS_SCORE_THRESHOLD = 0.5

TASKS = ["task_easy", "task_medium", "task_hard"]

SYSTEM_PROMPT = """You are a Power Grid Controller AI. Your goal is to maintain grid stability.

Key objectives:
1. Keep grid frequency close to 50.0 Hz (acceptable: 49.5–50.5 Hz)
2. Prevent transmission line overloads (rho < 1.0)
3. Avoid grid islanding (blackout)

Available actions:
1. bus_adjustments: List of {"bus_id": int, "delta": float}
   - Positive delta = increase power injection (discharge battery / ramp up generator)
   - Negative delta = decrease power injection (charge battery / ramp down generator)
   - Only works on battery and generator/slack buses
2. topology_actions: List of {"line_id": str, "action": "open" | "close"}
   - Opening a line removes it; closing reconnects. 3-step cooldown.
   - WARNING: Opening lines can cause islanding → blackout

Strategy:
- If frequency < 50 Hz → discharge batteries, ramp up generators
- If frequency > 50 Hz → charge batteries, ramp down generators
- If a line rho > 0.9 → reduce generation near that line, do NOT open it
- Prefer minimal actions over aggressive switching

Respond with ONLY a valid JSON object. Example:
{"bus_adjustments": [{"bus_id": 2, "delta": 5.0}], "topology_actions": []}
"""


# ---------- Structured Logging (mandatory key=value format) ----------

def log_start(task: str, env: str, model: str):
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error=None):
    done_val = str(done).lower()
    error_val = str(error) if error else "null"
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def clamp_score(s: float) -> float:
    """Ensure score is strictly in (0, 1). Mirrors grader._clamp_score."""
    try:
        s = float(s)
    except (TypeError, ValueError):
        return 0.5
    if not math.isfinite(s):
        return 0.5
    s = max(0.02, min(0.98, s))
    s = math.floor(s * 10000) / 10000
    return max(0.02, min(0.98, s))


def log_end(success: bool, steps: int, score: float, rewards: list):
    clamped = clamp_score(score)
    success_val = str(success).lower()
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={success_val} steps={steps} score={clamped:.2f} rewards={rewards_str}",
        flush=True,
    )


# ---------- LLM Call ----------

def get_model_message(client: OpenAI, step: int, obs_json: str, last_reward: float, history: list) -> str:
    """Ask the LLM what action to take given the current observation."""
    context = f"Step {step} | Last reward: {last_reward:+.2f}\n"
    if history:
        context += "Recent history (last 3):\n" + "\n".join(history[-3:]) + "\n\n"
    context += f"Current Grid State:\n{obs_json}"

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": context}
            ],
            temperature=0.0,
            max_tokens=300
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        print(f"[DEBUG] Model request failed: {exc}", flush=True)
        return '{"bus_adjustments": [], "topology_actions": []}'


# ---------- Environment Client ----------

class EnvClient:
    """HTTP client for the OpenGrid FastAPI environment."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=30.0)
        self.session_id = None

    def reset(self, task_id: str) -> dict:
        resp = self.client.post(f"{self.base_url}/reset", params={"task_id": task_id})
        resp.raise_for_status()
        data = resp.json()
        self.session_id = data["session_id"]
        return data["observation"]

    def step(self, action_dict: dict) -> dict:
        resp = self.client.post(
            f"{self.base_url}/step",
            params={"session_id": self.session_id},
            json=action_dict
        )
        resp.raise_for_status()
        return resp.json()

    def state(self) -> dict:
        resp = self.client.get(f"{self.base_url}/state", params={"session_id": self.session_id})
        resp.raise_for_status()
        return resp.json()

    def grade(self) -> dict:
        resp = self.client.get(f"{self.base_url}/grader", params={"session_id": self.session_id})
        resp.raise_for_status()
        return resp.json()

    def close(self):
        self.client.close()


# ---------- Parse Action ----------

def parse_action(response_text: str) -> dict:
    """Parse LLM JSON response into an action dict."""
    try:
        clean = response_text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        return {
            "bus_adjustments": data.get("bus_adjustments", []),
            "topology_actions": data.get("topology_actions", [])
        }
    except (json.JSONDecodeError, KeyError):
        return {"bus_adjustments": [], "topology_actions": []}


# ---------- Main ----------

def run_task(client: OpenAI, env: EnvClient, task_id: str) -> dict:
    """Run one task and return results."""
    history_msgs = []
    rewards = []
    steps_taken = 0
    score = 0.05
    success = False

    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)

    try:
        obs = env.reset(task_id)
        last_reward = 0.0

        for step_num in range(1, MAX_STEPS + 1):
            obs_json = json.dumps(obs, indent=2)
            message = get_model_message(client, step_num, obs_json, last_reward, history_msgs)
            action_dict = parse_action(message)

            result = env.step(action_dict)
            obs = result["observation"]
            reward = result.get("reward", {}).get("value", 0.0)
            done = result.get("done", False)

            rewards.append(reward)
            steps_taken = step_num
            last_reward = reward

            # Truncate action for logging
            action_summary = json.dumps(action_dict)
            if len(action_summary) > 200:
                action_summary = action_summary[:200] + "..."

            log_step(step=step_num, action=action_summary, reward=reward, done=done, error=None)

            history_msgs.append(f"Step {step_num}: action={action_summary[:80]} → reward {reward:+.2f}")

            if done:
                break

        # Get final grade from the environment
        grade_result = env.grade()
        score = clamp_score(grade_result.get("score", 0.5))
        success = score >= SUCCESS_SCORE_THRESHOLD

    except Exception as e:
        print(f"[DEBUG] Task {task_id} error: {e}", flush=True)
        score = 0.05
        success = False

    log_end(success=success, steps=steps_taken, score=score, rewards=rewards)

    return {"task": task_id, "score": score, "steps": steps_taken, "success": success}


def main():
    """Run inference on all 3 tasks."""
    if not API_KEY:
        print("[ERROR] No API key found. Set HF_TOKEN or OPENAI_API_KEY environment variable.", flush=True)
        sys.exit(1)

    print(f"[CONFIG] API_BASE_URL={API_BASE_URL}", flush=True)
    print(f"[CONFIG] MODEL_NAME={MODEL_NAME}", flush=True)
    print(f"[CONFIG] ENV_URL={ENV_URL}", flush=True)

    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)
    env = EnvClient(ENV_URL)

    all_results = []

    try:
        for task_id in TASKS:
            print(f"\n{'='*60}", flush=True)
            print(f"Running task: {task_id}", flush=True)
            print(f"{'='*60}", flush=True)

            result = run_task(client, env, task_id)
            all_results.append(result)

    finally:
        env.close()

    # Summary
    print(f"\n{'='*60}", flush=True)
    print("FINAL RESULTS", flush=True)
    print(f"{'='*60}", flush=True)
    for r in all_results:
        status = "✓ PASS" if r["success"] else "✗ FAIL"
        print(f"  {r['task']}: score={r['score']:.4f}  steps={r['steps']}  [{status}]", flush=True)

    avg_score = sum(r["score"] for r in all_results) / len(all_results) if all_results else 0
    print(f"\n  Average Score: {avg_score:.4f}", flush=True)


if __name__ == "__main__":
    main()
