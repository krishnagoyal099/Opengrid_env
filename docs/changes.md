# Notebook Changes — opengrid_grpo_colab.ipynb

## Bug fixes applied (2026-04-25)

### Cell 7 — Generate Training Prompts

| # | Severity | Bug | Fix |
|---|----------|-----|-----|
| 1 | 🔴 Critical | `obs_dict = obs.model_dump()` produces dicts with integer keys; `Dataset.from_dict({"obs_context": obs_contexts})` fails with `ArrowTypeError: Expected dict key of type str or bytes, got 'int'` | Changed to `json.loads(obs.model_dump_json())` so all keys are strings; then stored as `json.dumps(obs_dict)` — a flat JSON string PyArrow handles trivially |
| 2 | 🟡 Bug | `env = OpenGridEnv(task_config)` instantiated before the loop but immediately replaced inside the loop — wasted object creation | Removed stray instantiation |
| 3 | 🟡 Bug | `import copy`, `import json` inside inner loop body — re-imported on every iteration | Moved to top of cell |
| 4 | 🟡 Bug | Slack bus included in random action choices — physics solver overwrites it, wasting action budget | Filtered to `['generator', 'battery']` only |

### Cell 8 — Reward Function

| # | Severity | Bug | Fix |
|---|----------|-----|-----|
| 5 | 🔴 Critical | `reward_fn` received `obs_context` as JSON strings from the dataset column but passed them directly to `compute_grpo_reward` which expects dicts | Added `json.loads(ctx) if isinstance(ctx, str) else ctx` deserialization before scoring |
| 6 | 🟡 Bug | No assertion to catch silent arity mismatches | Added `assert len(test_rewards) == 2` sanity check |

### Cell 9 — Training

| # | Severity | Bug | Fix |
|---|----------|-----|-----|
| 7 | 🟡 Bug | `bf16=torch.cuda.is_bf16_supported()` raises `AssertionError` when CUDA is not available (no GPU runtime) | Guarded: `_cuda_ok = torch.cuda.is_available()` then `_bf16 = _cuda_ok and ...` |

### Cell 12 — Before/After Plot

| # | Severity | Bug | Fix |
|---|----------|-----|-----|
| 8 | 🟡 Bug | Bar labels used `va='bottom'` for all bars; for negative-height bars the label renders inside/below the bar | Fixed: `va='bottom'` when `h >= 0`, `va='top'` when `h < 0`, with matching y-offset |

### Cell 13 — Summary Table

| # | Severity | Bug | Fix |
|---|----------|-----|-----|
| 9 | 🟡 Bug | `common_tasks` was set in Cell 12; if the user skips the plot cell, Cell 13 raises `NameError: common_tasks` | Rebuilt `common_tasks` defensively at the top of Cell 13 |

---

## `inference.py` — Code review fixes (2026-04-25)

### High-priority fixes

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | 🔴 Bug | `parse_action()` crashes on valid JSON that is not an object (e.g. `[]`) — `AttributeError` not caught by `except (json.JSONDecodeError, KeyError)` | Rewrote with `isinstance(data, dict)` guard, list-unwrapping, field-type validation, and broad `except Exception` |
| 2 | 🔴 Bug | `parse_action()` markdown/prose stripping is fragile — fails on `Here is the action: {...}` | Extracts first `{...}` substring via `text.find("{")` / `text.rfind("}")` |
| 3 | 🔴 Reliability | `/grader` call can exceed `httpx` 30s timeout on first use (lazy `RobustnessGrader` bound estimation) | `grade()` now uses `timeout=180.0`; base client uses `httpx.Timeout(connect=10, read=60, write=30, pool=10)` |
| 4 | 🟡 Bug | `HF_TOKEN` takes precedence over `OPENAI_API_KEY` — if both set with OpenAI endpoint, auth fails | Changed to `API_KEY or OPENAI_API_KEY or HF_TOKEN` priority order |
| 5 | 🟡 Bug | No JSON-mode enforcement for LLM — models return markdown/prose | Added `response_format={"type": "json_object"}` with fallback for unsupported endpoints |

### System prompt fixes

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 6 | 🟡 Design | Prompt says slack bus is controllable, but physics solver overwrites it | Changed to: "avoid adjusting the slack bus — physics overwrites it" |
| 7 | 🟡 Design | Single-agent mode allows topology actions without safety layer protection | Added: "Prefer NO topology actions unless absolutely necessary" |
| 8 | 🟡 Design | Multi-agent prompt says "Only for lines in your zone" but observations include boundary lines | Clarified: "Only for visible internal or boundary lines. Boundary-line switching is risky" |

### Multi-agent robustness fixes

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 9 | 🟡 Bug | Agent iteration uses `range(num_agents)` — assumes contiguous integer IDs | Changed to `sorted(observations.keys())` |
| 10 | 🟡 Bug | `safety_reports` assumed to be list, but API returns dict keyed by agent ID | Added `isinstance` check to handle both list and dict formats |
| 11 | 🟡 Design | Safety correction feedback not fed back to LLM — model repeats same invalid actions | Appended `[SAFETY] {reason}` to agent history when corrections occur |

### Other fixes

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 12 | 🟡 Bug | `MAX_STEPS = 50` hardcoded — may truncate future tasks | Changed to `MAX_STEPS = 100` as safety cap; `done` flag is the true terminator |
| 13 | 🟡 Bug | Default task list excludes `task_karnataka` despite KPTCL multi-agent framing | Added `task_karnataka` to `TASKS` list |
| 14 | 🟡 Bug | Module docstring says all 3 env vars are required; only API key is | Fixed docstring to document defaults and actual requirements |
| 15 | 🟡 Bug | `[END]` log prints score at `.2f` but summary prints `.4f` — precision loss | Changed `log_end` to use `:.4f` |
| 16 | 🟡 Reliability | `OpenAI()` client has no timeout or retry config | Added `timeout=30.0, max_retries=2` |
| 17 | 🟢 Feature | No `list_tasks()` method on `EnvClient` | Added `list_tasks()` for future task validation |

---

## GRPO Training — Environment-Grounded Rewards (2026-04-25)

### Root Cause: Proxy Reward Disconnect

The original `compute_grpo_reward` was a **heuristic proxy scorer** that evaluated JSON format, direction, and proportionality without ever stepping the environment. The model optimized this proxy, which did not correlate with actual grid physics rewards. Result: zero improvement over baseline.

### Changes Made

#### `src/environment.py`

| # | Change | Purpose |
|---|--------|---------|
| 1 | Added `_set_state(obs_dict)` method to `OpenGridEnv` | Enables restoring environment to any observed state for reward computation. Rebuilds bus/line state, frequency, and slack injection from observation dicts. |

#### `training/train_grpo.py`

| # | Severity | Change | Details |
|---|----------|--------|---------|
| 2 | 🔴 Critical | Replaced `compute_grpo_reward` with `compute_grpo_reward_env` | New reward function **actually steps the physics simulation**: restores env state → steps with LLM action → measures real reward → runs mini-rollout with heuristic continuation for trajectory awareness |
| 3 | 🔴 Critical | Added mini-rollout scoring (horizon=3) | After the LLM's action, runs 2 more steps with heuristic policy to capture trajectory-level impact. Combines: `immediate_reward + 0.5 * rollout_reward` |
| 4 | 🟡 Medium | Increased `num_generations` from 4 → 8 | Wider GRPO group = more reward variance = stronger ranking signal. Prevents the advantage calculation from collapsing to zero. |
| 5 | 🟡 Medium | Increased random perturbation range from ±15 → ±30 MW | Creates more diverse/stressed grid states during training data generation. Model sees near-blackout and overload scenarios. |
| 6 | 🟡 Medium | Added adversarial battery drain (every 5th episode) | Forces model to learn actions when batteries are near-empty — a critical edge case the original data lacked. |
| 7 | 🟡 Medium | Multi-bus perturbations (1-2 buses per step) | Was single-bus. More diverse action patterns create richer state transitions. |
| 8 | 🟡 Medium | Increased learning rate from 5e-6 → 1e-5 | Slightly more aggressive to capitalize on the now-meaningful reward signal. |
| 9 | 🟡 Medium | Increased gradient accumulation (effective batch 16) | Smoother gradients for more stable training. |
| 10 | 🟡 Medium | Steps per episode increased from 10 → 15 | More temporal diversity in observations. |
| 11 | 🟢 Minor | obs_context stored as JSON string | Fixes Arrow serialization (PyArrow can't handle dicts with int keys). |
| 12 | 🟢 Minor | Kept legacy `compute_grpo_reward` for test-mode compat | Backward compatibility with `--test-mode` pipeline verification. |

