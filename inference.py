"""
OpenGrid Inference Script
=========================
Runs an LLM agent against all OpenGrid tasks via the OpenAI-compatible API.
Supports both single-agent and multi-agent POMDP modes.

Optional environment variables:
  API_BASE_URL   -- defaults to https://api.openai.com/v1
  MODEL_NAME     -- defaults to gpt-4o
Required (one of):
  OPENAI_API_KEY or HF_TOKEN

Emits structured [START], [STEP], [END] logs to stdout.

Usage:
  # Single-agent mode (backward compatible)
  python inference.py

  # Multi-agent mode (uses safety layer + oversight)
  python inference.py --multi
"""

import os
import sys
import json
import math
import argparse
import httpx

from openai import OpenAI

# ---------- Configuration ----------

API_BASE_URL = os.environ.get("API_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.environ.get("MODEL_NAME", "gpt-4o")

# Prefer OPENAI_API_KEY when using OpenAI endpoint; otherwise try HF_TOKEN
API_KEY = (
    os.environ.get("API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or os.environ.get("HF_TOKEN")
    or ""
)

ENV_URL = os.environ.get("ENV_URL", "http://localhost:7860")
BENCHMARK = "OpenGrid"
# Safety cap — the environment's 'done' flag is the true terminator
MAX_STEPS = 100
SUCCESS_SCORE_THRESHOLD = 0.5

TASKS = ["task_easy", "task_medium", "task_hard", "task_karnataka"]

SYSTEM_PROMPT_SINGLE = """You are a Power Grid Controller AI. Your goal is to maintain grid stability.

Key objectives:
1. Keep grid frequency close to 50.0 Hz (acceptable: 49.5-50.5 Hz)
2. Prevent transmission line overloads (rho < 1.0)
3. Avoid grid islanding (blackout)

Available actions:
1. bus_adjustments: List of {"bus_id": int, "delta": float}
   - Positive delta = increase power injection (discharge battery / ramp up generator)
   - Negative delta = decrease power injection (charge battery / ramp down generator)
   - Only works on battery and generator buses (avoid adjusting the slack bus — physics overwrites it)
2. topology_actions: List of {"line_id": str, "action": "open" | "close"}
   - Opening a line removes it; closing reconnects. 3-step cooldown.
   - WARNING: Opening lines can cause islanding -> blackout
   - Prefer NO topology actions unless absolutely necessary. Always return "topology_actions": []

Strategy:
- If frequency < 50 Hz -> discharge batteries, ramp up generators
- If frequency > 50 Hz -> charge batteries, ramp down generators
- If a line rho > 0.9 -> reduce generation near that line, do NOT open it
- Prefer minimal actions over aggressive switching

Respond with ONLY a valid JSON object. Example:
{"bus_adjustments": [{"bus_id": 2, "delta": 5.0}], "topology_actions": []}
"""

SYSTEM_PROMPT_MULTI = """You are a KPTCL Zone Controller AI managing one zone of the Karnataka power grid.
You can only see and control buses in YOUR zone. Other zones are managed by other agents.

Key objectives:
1. Keep grid frequency close to 50.0 Hz (you see a noisy reading)
2. Prevent line overloads in your zone (rho < 1.0)
3. Coordinate with other zones (don't fight against them)
4. Avoid actions that would trigger the safety layer

Available actions:
1. bus_adjustments: List of {"bus_id": int, "delta": float}
   - ONLY adjust battery and generator buses in YOUR zone (avoid slack — physics overwrites it)
   - Positive delta = increase power injection
   - Negative delta = decrease power injection
2. topology_actions: List of {"line_id": str, "action": "open" | "close"}
   - Only for visible internal or boundary lines. Safety layer will block dangerous switches.
   - Boundary-line switching is risky; avoid unless necessary.

Strategy:
- If frequency < 50 Hz -> increase generation/discharge in your zone
- If frequency > 50 Hz -> decrease generation/charge in your zone
- Check neighbor signals to understand if other zones are compensating
- Prefer small corrections over large swings

Respond with ONLY a valid JSON object. Example:
{"bus_adjustments": [{"bus_id": 2, "delta": 5.0}], "topology_actions": []}
"""


# ---------- Structured Logging ----------

def log_start(task: str, env: str, model: str, mode: str = "single"):
    print(f"[START] task={task} env={env} model={model} mode={mode}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error=None, agent_id=None):
    done_val = str(done).lower()
    error_val = str(error) if error else "null"
    agent_str = f" agent={agent_id}" if agent_id is not None else ""
    print(
        f"[STEP] step={step}{agent_str} action={action} reward={reward:.2f} done={done_val} error={error_val}",
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


def log_end(success: bool, steps: int, score: float, rewards: list, mode: str = "single"):
    clamped = clamp_score(score)
    success_val = str(success).lower()
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={success_val} steps={steps} score={clamped:.4f} rewards={rewards_str} mode={mode}",
        flush=True,
    )


# ---------- LLM Call ----------

def get_model_message(client: OpenAI, step: int, obs_json: str, last_reward: float,
                      history: list, system_prompt: str, zone_name: str = None) -> str:
    """Ask the LLM what action to take given the current observation."""
    context = ""
    if zone_name:
        context += f"[Zone: {zone_name}] "
    context += f"Step {step} | Last reward: {last_reward:+.2f}\n"
    if history:
        context += "Recent history (last 3):\n" + "\n".join(history[-3:]) + "\n\n"
    context += f"Current Grid State:\n{obs_json}"

    try:
        kwargs = dict(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            temperature=0.0,
            max_tokens=300,
        )
        # Use JSON mode if the endpoint supports it (OpenAI-compatible)
        try:
            kwargs["response_format"] = {"type": "json_object"}
            response = client.chat.completions.create(**kwargs)
        except Exception:
            # Fallback: endpoint may not support response_format
            kwargs.pop("response_format", None)
            response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content.strip()
    except Exception as exc:
        print(f"[DEBUG] Model request failed: {exc}", flush=True)
        return '{"bus_adjustments": [], "topology_actions": []}'


# ---------- Environment Client ----------

class EnvClient:
    """HTTP client for the OpenGrid FastAPI environment."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            timeout=httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)
        )
        self.session_id = None

    # --- Single-Agent ---

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

    # --- Multi-Agent ---

    def reset_multi(self, task_id: str) -> dict:
        resp = self.client.post(f"{self.base_url}/reset_multi", params={"task_id": task_id})
        resp.raise_for_status()
        data = resp.json()
        self.session_id = data["session_id"]
        return data

    def step_multi(self, agent_actions: dict) -> dict:
        resp = self.client.post(
            f"{self.base_url}/step_multi",
            params={"session_id": self.session_id},
            json={"agent_actions": agent_actions}
        )
        resp.raise_for_status()
        return resp.json()

    # --- Shared ---

    def state(self) -> dict:
        resp = self.client.get(f"{self.base_url}/state", params={"session_id": self.session_id})
        resp.raise_for_status()
        return resp.json()

    def grade(self) -> dict:
        # Grading can trigger lazy bound estimation (multiple rollouts) — use long timeout
        resp = self.client.get(
            f"{self.base_url}/grader",
            params={"session_id": self.session_id},
            timeout=180.0,
        )
        resp.raise_for_status()
        return resp.json()

    def list_tasks(self) -> list:
        """Fetch available tasks from the server."""
        resp = self.client.get(f"{self.base_url}/tasks")
        resp.raise_for_status()
        return resp.json()

    def close(self):
        self.client.close()


# ---------- Parse Action ----------

NOOP_ACTION = {"bus_adjustments": [], "topology_actions": []}


def parse_action(response_text: str) -> dict:
    """Parse LLM JSON response into an action dict.

    Handles markdown fences, prose preambles, JSON lists, and malformed output.
    """
    try:
        text = str(response_text).strip()

        # Strip markdown code fences
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # Extract first JSON object from any surrounding prose
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return dict(NOOP_ACTION)

        data = json.loads(text[start:end + 1])

        # Handle list wrapping (e.g. [{...}])
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            return dict(NOOP_ACTION)

        bus_adjustments = data.get("bus_adjustments", [])
        topology_actions = data.get("topology_actions", [])

        if not isinstance(bus_adjustments, list):
            bus_adjustments = []
        if not isinstance(topology_actions, list):
            topology_actions = []

        return {
            "bus_adjustments": bus_adjustments,
            "topology_actions": topology_actions,
        }
    except Exception:
        return dict(NOOP_ACTION)


# ---------- Single-Agent Runner ----------

def run_task_single(client: OpenAI, env: EnvClient, task_id: str) -> dict:
    """Run one task in single-agent mode and return results."""
    history_msgs = []
    rewards = []
    steps_taken = 0
    score = 0.05
    success = False

    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME, mode="single")

    try:
        obs = env.reset(task_id)
        last_reward = 0.0

        for step_num in range(1, MAX_STEPS + 1):
            obs_json = json.dumps(obs, indent=2)
            message = get_model_message(client, step_num, obs_json, last_reward,
                                         history_msgs, SYSTEM_PROMPT_SINGLE)
            action_dict = parse_action(message)

            result = env.step(action_dict)
            obs = result["observation"]
            reward = result.get("reward", {}).get("value", 0.0)
            done = result.get("done", False)

            rewards.append(reward)
            steps_taken = step_num
            last_reward = reward

            action_summary = json.dumps(action_dict)
            if len(action_summary) > 200:
                action_summary = action_summary[:200] + "..."

            log_step(step=step_num, action=action_summary, reward=reward, done=done)

            history_msgs.append(f"Step {step_num}: action={action_summary[:80]} -> reward {reward:+.2f}")

            if done:
                break

        grade_result = env.grade()
        score = clamp_score(grade_result.get("score", 0.5))
        success = score >= SUCCESS_SCORE_THRESHOLD

    except Exception as e:
        print(f"[DEBUG] Task {task_id} error: {e}", flush=True)
        score = 0.05
        success = False

    log_end(success=success, steps=steps_taken, score=score, rewards=rewards, mode="single")

    return {"task": task_id, "score": score, "steps": steps_taken, "success": success}


# ---------- Multi-Agent Runner ----------

def run_task_multi(client: OpenAI, env: EnvClient, task_id: str) -> dict:
    """Run one task in multi-agent mode and return results."""
    rewards = []
    steps_taken = 0
    score = 0.05
    success = False
    total_safety_interventions = 0

    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME, mode="multi")

    try:
        reset_data = env.reset_multi(task_id)
        num_agents = reset_data["num_agents"]
        zone_info = reset_data["zone_info"]
        observations = reset_data["observations"]

        # Per-agent history
        agent_histories = {str(i): [] for i in range(num_agents)}
        last_rewards = {str(i): 0.0 for i in range(num_agents)}

        print(f"[INFO] Multi-agent mode: {num_agents} agents", flush=True)
        for aid, zi in zone_info.items():
            print(f"  Agent {aid}: {zi['zone_name']} ({len(zi['bus_ids'])} buses)", flush=True)

        for step_num in range(1, MAX_STEPS + 1):
            agent_actions = {}

            # Each agent generates its own action based on partial observation
            for agent_id_str in sorted(observations.keys()):
                obs = observations.get(agent_id_str, {})
                zone_name = zone_info.get(agent_id_str, {}).get("zone_name", f"Zone_{agent_id_str}")

                obs_json = json.dumps(obs, indent=2)
                message = get_model_message(
                    client, step_num, obs_json,
                    last_rewards[agent_id_str],
                    agent_histories[agent_id_str],
                    SYSTEM_PROMPT_MULTI,
                    zone_name=zone_name
                )
                action_dict = parse_action(message)
                agent_actions[agent_id_str] = action_dict

            # Submit all actions together
            result = env.step_multi(agent_actions)
            observations = result["observations"]
            team_reward = result.get("team_reward", 0.0)
            done = result.get("done", False)

            # Track safety interventions
            safety_reports = result.get("safety_reports", {})
            if isinstance(safety_reports, list):
                # Handle list format from older API
                step_interventions = sum(1 for sr in safety_reports if sr.get("was_corrected", False))
            else:
                step_interventions = sum(
                    1 for sr in safety_reports.values() if sr.get("was_corrected", False)
                )
            total_safety_interventions += step_interventions

            # Feed safety correction feedback into agent histories
            if isinstance(safety_reports, dict):
                for aid_str, sr in safety_reports.items():
                    if sr.get("was_corrected") and aid_str in agent_histories:
                        reason = sr.get("correction_reason", "action corrected")[:120]
                        agent_histories[aid_str].append(f"[SAFETY] {reason}")

            # Log per-agent rewards
            per_agent_rewards = result.get("rewards", {})
            for agent_id_str in sorted(observations.keys()):
                agent_reward = per_agent_rewards.get(agent_id_str, {}).get("value", 0.0)
                last_rewards[agent_id_str] = agent_reward
                action_summary = json.dumps(agent_actions.get(agent_id_str, {}))
                if len(action_summary) > 100:
                    action_summary = action_summary[:100] + "..."
                agent_histories[agent_id_str].append(
                    f"Step {step_num}: action={action_summary[:60]} -> reward {agent_reward:+.2f}"
                )

            rewards.append(team_reward)
            steps_taken = step_num

            # Log team-level step
            oversight = result.get("oversight_report", {})
            coord_score = oversight.get("coordination_score", 1.0)
            safety_str = f" safety_corrections={step_interventions}" if step_interventions > 0 else ""
            log_step(step=step_num, action=f"team_reward={team_reward:.2f} coord={coord_score:.2f}{safety_str}",
                     reward=team_reward, done=done)

            if done:
                break

        grade_result = env.grade()
        score = clamp_score(grade_result.get("score", 0.5))
        success = score >= SUCCESS_SCORE_THRESHOLD

    except Exception as e:
        print(f"[DEBUG] Task {task_id} multi-agent error: {e}", flush=True)
        score = 0.05
        success = False

    print(f"[INFO] Total safety interventions: {total_safety_interventions}", flush=True)
    log_end(success=success, steps=steps_taken, score=score, rewards=rewards, mode="multi")

    return {
        "task": task_id, "score": score, "steps": steps_taken,
        "success": success, "safety_interventions": total_safety_interventions
    }


# ---------- Main ----------

def main():
    """Run inference on all tasks."""
    parser = argparse.ArgumentParser(description="OpenGrid LLM Inference")
    parser.add_argument("--multi", action="store_true",
                        help="Use multi-agent POMDP mode (default: single-agent)")
    parser.add_argument("--tasks", nargs="+", default=TASKS,
                        help="Which tasks to run (default: all)")
    args = parser.parse_args()

    if not API_KEY:
        print("[ERROR] No API key found. Set OPENAI_API_KEY or HF_TOKEN environment variable.", flush=True)
        sys.exit(1)

    mode = "multi-agent" if args.multi else "single-agent"
    print(f"[CONFIG] API_BASE_URL={API_BASE_URL}", flush=True)
    print(f"[CONFIG] MODEL_NAME={MODEL_NAME}", flush=True)
    print(f"[CONFIG] ENV_URL={ENV_URL}", flush=True)
    print(f"[CONFIG] MODE={mode}", flush=True)

    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY, timeout=30.0, max_retries=2)
    env = EnvClient(ENV_URL)

    all_results = []
    runner = run_task_multi if args.multi else run_task_single

    try:
        for task_id in args.tasks:
            print(f"\n{'='*60}", flush=True)
            print(f"Running task: {task_id} ({mode})", flush=True)
            print(f"{'='*60}", flush=True)

            result = runner(client, env, task_id)
            all_results.append(result)

    finally:
        env.close()

    # Summary
    print(f"\n{'='*60}", flush=True)
    print(f"FINAL RESULTS ({mode})", flush=True)
    print(f"{'='*60}", flush=True)
    for r in all_results:
        status = "PASS" if r["success"] else "FAIL"
        extra = ""
        if "safety_interventions" in r:
            extra = f"  safety={r['safety_interventions']}"
        print(f"  {r['task']}: score={r['score']:.4f}  steps={r['steps']}  [{status}]{extra}", flush=True)

    avg_score = sum(r["score"] for r in all_results) / len(all_results) if all_results else 0
    print(f"\n  Average Score: {avg_score:.4f}", flush=True)


if __name__ == "__main__":
    main()
