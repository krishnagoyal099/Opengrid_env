"""
Comprehensive training pipeline verification.
Tests: scenarios, reward functions, policies, GRPO integration, safety.
"""
import json
import copy
import sys
sys.path.insert(0, ".")

from src.tasks import TASKS, get_task
from src.environment import OpenGridEnv
from src.models import GridAction, GridObservation
from src.grader import RobustnessGrader
from src.baseline import heuristic_policy
from src.safety import SafetyLayer

print("=" * 60)
print("  COMPREHENSIVE TRAINING PIPELINE VERIFICATION")
print("=" * 60)

errors = []

# --- 1. Scenario loading ---
print("\n[1/7] Scenario Loading...")
expected_tasks = ["task_easy", "task_medium", "task_hard",
                  "task_karnataka", "karnataka_easy", "karnataka_medium", "karnataka_hard"]
for tid in expected_tasks:
    if tid not in TASKS:
        errors.append(f"Missing task: {tid}")
        print(f"  FAIL: {tid} not in TASKS")
    else:
        cfg = TASKS[tid]
        print(f"  OK: {tid} - {cfg['num_buses']}b/{cfg['num_agents']}a zones={cfg['zone_names']}")

# --- 2. Environment step for each scenario ---
print("\n[2/7] Environment Step Test...")
for tid in expected_tasks:
    try:
        cfg = get_task(tid)
        env = OpenGridEnv(cfg)
        obs = env.reset()
        action = GridAction.model_validate_json(
            json.dumps({"bus_adjustments": [], "topology_actions": []})
        )
        obs2, reward, done, info = env.step(action)
        freq = obs2.grid_frequency
        r = reward.value
        print(f"  OK: {tid} - freq={freq:.2f}Hz reward={r:.2f}")
    except Exception as e:
        errors.append(f"Env step failed for {tid}: {e}")
        print(f"  FAIL: {tid} - {e}")

# --- 3. Reward function (GRPO) test ---
print("\n[3/7] GRPO Reward Function Test...")
from training.train_grpo import compute_grpo_reward_env
test_completions = [
    '{"bus_adjustments": [{"bus_id": 0, "delta": 5.0}], "topology_actions": []}',
    '{"bus_adjustments": [], "topology_actions": []}',
    'not valid json',
]
test_observations = [
    {"grid_frequency": 49.5, "buses": [], "lines": []},
    {"grid_frequency": 50.0, "buses": [], "lines": []},
    {"grid_frequency": 48.0, "buses": [], "lines": []},
]
try:
    cfg = get_task("karnataka_easy")
    rewards = compute_grpo_reward_env(test_completions, test_observations, cfg, horizon=1)
    for i, r in enumerate(rewards):
        print(f"  Completion {i}: reward={r:.3f}")
    print(f"  OK: GRPO rewards computed for {len(rewards)} completions")
except Exception as e:
    errors.append(f"GRPO reward failed: {e}")
    print(f"  FAIL: {e}")

# --- 4. Karnataka Difficulty Gradient Test ---
print("\n[4/7] Karnataka Difficulty Gradient Test...")
ka_rewards = {}
for tid in ["karnataka_easy", "karnataka_medium", "karnataka_hard"]:
    try:
        cfg = get_task(tid)
        env = OpenGridEnv(cfg)
        obs = env.reset()
        total_r = 0
        for step_i in range(5):
            action = GridAction.model_validate_json(
                json.dumps({"bus_adjustments": [], "topology_actions": []})
            )
            obs, reward, done, info = env.step(action)
            total_r += reward.value
            if done:
                break
        ka_rewards[tid] = total_r
        print(f"  {tid}: 5-step reward={total_r:.2f}")
    except Exception as e:
        errors.append(f"Ka difficulty test failed for {tid}: {e}")
        print(f"  FAIL: {tid} - {e}")

if len(ka_rewards) == 3:
    # Easy should generally give higher or equal rewards than hard
    if ka_rewards["karnataka_easy"] >= ka_rewards["karnataka_hard"]:
        print(f"  OK: Difficulty gradient correct (easy >= hard)")
    else:
        print(f"  WARN: easy ({ka_rewards['karnataka_easy']:.2f}) < hard ({ka_rewards['karnataka_hard']:.2f}) - may vary by seed")

# --- 5. Heuristic policy test ---
print("\n[5/7] Heuristic Policy Test...")
for tid in ["task_easy", "karnataka_easy", "task_karnataka"]:
    try:
        cfg = get_task(tid)
        env = OpenGridEnv(cfg)
        obs = env.reset()
        total_r = 0
        for step_i in range(10):
            action = heuristic_policy(obs)
            obs, reward, done, info = env.step(action)
            total_r += reward.value
            if done:
                break
        print(f"  OK: {tid} - 10-step heuristic reward={total_r:.2f}")
    except Exception as e:
        errors.append(f"Heuristic policy failed for {tid}: {e}")
        print(f"  FAIL: {tid} - {e}")

# --- 6. Safety layer test ---
print("\n[6/7] Safety Layer Test...")
for tid in ["task_easy", "karnataka_easy", "karnataka_hard"]:
    try:
        cfg = get_task(tid)
        layer = SafetyLayer(cfg)
        action = GridAction.model_validate_json(
            json.dumps({"bus_adjustments": [{"bus_id": 0, "delta": 100.0}], "topology_actions": []})
        )
        bus_state = [{"id": b["id"], "p": b.get("base_p", 0), "soc": b.get("init_soc", 0)} for b in cfg["buses"]]
        line_state = [{"id": l["id"], "connected": True, "flow": 0} for l in cfg["lines"]]
        safe_action, report = layer.validate_and_correct(0, action, line_state, bus_state, {})
        print(f"  OK: {tid} - corrected={report.was_corrected}, n1_violations={report.n1_violations_detected}")
    except Exception as e:
        errors.append(f"Safety layer failed for {tid}: {e}")
        print(f"  FAIL: {tid} - {e}")

# --- 7. Curriculum order test ---
print("\n[7/7] Curriculum Order Test...")
from training.train_grpo import CURRICULUM_ORDER
for tid in CURRICULUM_ORDER:
    if tid in TASKS:
        print(f"  OK: {tid} available")
    else:
        errors.append(f"Curriculum task missing: {tid}")
        print(f"  FAIL: {tid} not in TASKS")

# --- Summary ---
print("\n" + "=" * 60)
if errors:
    print(f"  FAILED: {len(errors)} errors")
    for e in errors:
        print(f"    - {e}")
    sys.exit(1)
else:
    print("  ALL CHECKS PASSED - Training pipeline ready")
print("=" * 60)
