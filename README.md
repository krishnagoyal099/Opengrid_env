---
title: OpenGrid
emoji: ⚡
colorFrom: green
colorTo: blue
sdk: docker
app_file: app.py
pinned: false
---

<p align="center">
  <img src="static/logo.png" alt="OpenGrid Logo" width="120">
</p>

<h1 align="center">OpenGrid ⚡</h1>
<p align="center"><strong>Safe Multi-Agent RL for Power Grid Operations</strong></p>

<p align="center">
  <a href="https://huggingface.co/spaces/K446/Opengrid"><img src="https://img.shields.io/badge/🤗%20Live%20Demo-HuggingFace%20Space-yellow" alt="Live Demo"></a>
  <a href="https://github.com/krishnagoyal099/Opengrid_env"><img src="https://img.shields.io/badge/GitHub-Repository-181717?logo=github" alt="GitHub"></a>
  <a href="https://github.com/openenv"><img src="https://img.shields.io/badge/OpenEnv-compatible-blue" alt="OpenEnv"></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT"></a>
</p>

---

## What is OpenGrid?

OpenGrid is a **multi-agent reinforcement learning environment** where AI agents control a power grid. Multiple agents, each managing a zone, must coordinate under **partial observability** to keep the lights on — balancing electricity supply and demand in real-time while managing renewable energy volatility.

What makes OpenGrid different:

- **Multi-Agent POMDP**: 2-3 agents, each seeing only their local zone + noisy global signals
- **Safety Layer**: Hard constraint filter blocks unsafe actions before they reach the physics engine (N-1 security, anti-islanding, ramp limits)
- **Oversight Agent**: Monitors cross-zone coordination, penalizes selfish behavior
- **Composable Rewards**: 6 independent reward functions — survival, frequency, congestion, safety compliance, coordination, efficiency
- **Real Physics**: DC power flow solver with droop frequency model

> **🔗 Try it live:** [huggingface.co/spaces/K446/Opengrid](https://huggingface.co/spaces/K446/Opengrid)

---

## How It Works

```
┌─────────────────────────────────────────────────────────┐
│                   MULTI-AGENT LOOP                      │
│                                                         │
│   Each agent observes LOCAL zone state (POMDP)          │
│              │                                          │
│              ▼                                          │
│   Each agent proposes action (adjust power, switch      │
│   lines — only within their zone)                       │
│              │                                          │
│              ▼                                          │
│   SAFETY LAYER validates all actions:                   │
│   - N-1 security check                                 │
│   - Anti-islanding                                     │
│   - Projects unsafe → nearest safe alternative          │
│              │                                          │
│              ▼                                          │
│   OVERSIGHT AGENT evaluates coordination:               │
│   - Detects conflicts between agents                   │
│   - Penalizes selfish behavior                         │
│              │                                          │
│              ▼                                          │
│   Physics engine solves DC power flow                   │
│              │                                          │
│              ▼                                          │
│   Per-agent rewards: local + global + safety + coord    │
│              │                                          │
│   Repeat for 50 steps — or until blackout!              │
└─────────────────────────────────────────────────────────┘
```

The agent interacts through a **REST API** — any language or framework that can make HTTP requests can play. Both single-agent (backward compatible) and multi-agent modes are supported.

---

## Three Difficulty Levels

| Task | Grid Size | Agents | Renewable Mix | What Makes It Hard |
|---|---|---|---|---|
| `task_easy` | 5 buses | 2 | 20% | Basic frequency control, 2-zone coordination |
| `task_medium` | 10 buses | 3 | 50% | Volatile renewables + congestion + 3-zone POMDP |
| `task_hard` | 14 buses | 3 | 70% | High volatility, tight margins, complex topology |
| `task_karnataka` | 15 buses | 4 | Real mix | Real KPTCL topology (Raichur, Ballari, Bengaluru, Mysuru) with GPS coordinates |

All tasks run for **50 timesteps**. Scores range from **0.02 to 0.98** (higher = better).

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/krishnagoyal099/Opengrid_env.git
cd Opengrid_env

pip install -r requirements.txt
```

### 2. Start the Server

```bash
uvicorn app:app --host 0.0.0.0 --port 7860
```

Then open [http://localhost:7860](http://localhost:7860) — you'll see the **interactive SCADA dashboard** with a Leaflet.js GIS map showing the Karnataka grid topology in real-time.

### 3. Run the AI Agent

```bash
# Set your LLM API credentials
export API_BASE_URL="https://api.openai.com/v1"
export MODEL_NAME="gpt-4o"
export HF_TOKEN="your-api-key"
export ENV_URL="http://localhost:7860"

# Run inference on all 3 tasks
python inference.py
```

### 4. Train with GRPO

```bash
# Test the training pipeline (no GPU needed)
python training/train_grpo.py --test-mode

# Full training with Unsloth (needs GPU)
python training/train_grpo.py --model unsloth/Qwen2.5-1.5B-Instruct-bnb-4bit --use-unsloth
```

### Docker (Alternative)

```bash
docker build -t opengrid .
docker run -p 7860:7860 opengrid
```

---

## Multi-Agent API

### Reset in Multi-Agent Mode

```bash
curl -X POST "http://localhost:7860/reset_multi?task_id=task_medium"
# Returns: {
#   "session_id": "abc-123",
#   "num_agents": 3,
#   "zone_info": {"0": {"zone_name": "Bengaluru_Region", "bus_ids": [...]}, ...},
#   "observations": {"0": {...}, "1": {...}, "2": {...}}
# }
```

### Take a Multi-Agent Step

```bash
curl -X POST "http://localhost:7860/step_multi?session_id=abc-123" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_actions": {
      "0": {"bus_adjustments": [{"bus_id": 0, "delta": 5.0}], "topology_actions": []},
      "1": {"bus_adjustments": [], "topology_actions": []},
      "2": {"bus_adjustments": [{"bus_id": 9, "delta": -3.0}], "topology_actions": []}
    }
  }'
# Returns: per-agent observations, per-agent rewards, safety reports, oversight report
```

### Single-Agent API (Backward Compatible)

The original single-agent API (`/reset`, `/step`, `/state`, `/grader`) is fully preserved.

---

## What Each Agent Sees (POMDP Observation)

Each agent receives a **partial** observation of their zone:

| Field | Example | Meaning |
|---|---|---|
| `grid_frequency` | `49.87` | **Noisy** frequency reading (Gaussian noise added) |
| `local_buses[].type` | `"solar"` | Bus type (only buses in agent's zone) |
| `local_buses[].p_injection` | `35.2` | Power output in MW |
| `boundary_lines[].rho` | `0.78` | Lines connecting to other zones |
| `internal_lines[].flow` | `62.4` | Lines within agent's zone |
| `neighbor_signals` | `{1: 12.5}` | Average injection of neighboring zones |
| `zone_load_mw` | `85.3` | Total load in this zone |
| `zone_gen_mw` | `42.1` | Total generation in this zone |

Agents do **NOT** see buses or lines in other zones — they must coordinate through limited neighbor signals and the shared (but noisy) frequency reading.

---

## Safety Layer

The safety layer validates every action BEFORE it reaches the physics engine:

| Check | What It Does | If Violated |
|---|---|---|
| **Zone Boundary** | Agent can only adjust buses in their zone | Action removed |
| **N-1 Security** | Grid must survive loss of any single line | Action blocked |
| **Anti-Islanding** | Opening a line must not disconnect the grid | Switch blocked |
| **Ramp Limits** | Power changes within physical ramp rates | Delta clamped |
| **Capacity Limits** | Generation within min/max bounds | Output clamped |
| **Battery SoC** | Can't discharge below 0 or charge above capacity | Delta clamped |

Critically, unsafe actions are **projected to the nearest safe alternative** rather than simply rejected. This preserves the agent's intent while enforcing safety, and provides a richer training signal.

---

## Reward System

Six composable, independent reward functions:

| Component | Range | When |
|---|---|---|
| **survival** | +1.0 / -100.0 | Grid stays connected / blackout |
| **frequency** | -1.5 to +0.2 | Based on deviation from 50 Hz |
| **local_congestion** | ≤ 0 | Line overloads in agent's zone |
| **safety_compliance** | -0.3 to +0.1 | Penalty if safety layer corrected action |
| **coordination** | ≤ 0 | Penalty for selfish/conflicting actions |
| **action_cost** | -0.5 / switch | Topology change cost |

---

## Scoring

Scores are normalized to **(0.02 – 0.98)** using:

```
score = (agent_reward - worst_case) / (best_case - worst_case) + N1_bonus
```

| Bound | How It's Computed |
|---|---|
| **Worst case (floor)** | Random agent that chaotically switches lines — causes blackouts fast |
| **Best case (ceiling)** | Theoretical perfect agent: survives every step + perfect frequency bonus |
| **N-1 bonus** | Up to +10% for completing the episode without a blackout |

### Baseline Scores (Heuristic Policy)

| Task | Score | Strategy |
|---|---|---|
| `task_easy` | ~0.90 | Proportional frequency control, no line switching |
| `task_medium` | ~0.98 | Same heuristic — medium grid happens to be well-balanced |
| `task_hard` | ~0.98 | Same heuristic — hard grid has more buses but similar dynamics |
| `task_karnataka` | ~0.98 | 15-bus real topology, 4 zones, generators warm-started |

> Reproduce with: `python get_scores.py`

---

## Project Structure

```
OpenGrid/
├── app.py                      # FastAPI server (single + multi-agent endpoints)
├── inference.py                # LLM inference script
├── get_scores.py               # Reproduce baseline scores
├── openenv.yaml                # OpenEnv manifest
├── Dockerfile                  # Container config
├── requirements.txt            # Python dependencies
│
├── src/                        # Core environment
│   ├── models.py               # Pydantic models (single + multi-agent)
│   ├── environment.py          # Grid simulation (POMDP + backward-compatible)
│   ├── physics.py              # DC power flow solver
│   ├── tasks.py                # Procedural grid generation with zone assignment
│   ├── grader.py               # Scoring (floor/ceiling normalization)
│   ├── baseline.py             # Heuristic + LLM policies
│   ├── safety.py               # Safety layer (N-1, anti-islanding, projection)
│   ├── oversight.py            # Oversight agent (coordination monitoring)
│   └── visualization.py        # Grid topology & frequency plots
│
├── training/                   # RL training pipeline
│   ├── train_grpo.py           # TRL GRPO training script
│   └── opengrid_grpo_colab.ipynb  # Google Colab notebook for GPU training
│
├── tests/                      # Test suite (28 tests)
│   ├── test_solver.py          # Physics, environment, grader tests
│   └── test_multi_agent.py     # Multi-agent, safety, oversight tests
│
├── static/                     # Dashboard frontend
│   ├── index.html
│   ├── style.css
│   └── app.js
│
└── server/                     # Alternative entry point
    └── app.py
```

---

## Training Results (GRPO)

We trained **Qwen 2.5 1.5B** using GRPO (Group Relative Policy Optimization) on the Karnataka grid topology.

### Training Loss

The loss converges from ~0.09 to near 0 by step ~400, confirming end-to-end training pipeline functionality.

### Before vs After (Average Episode Reward)

| Task | Heuristic Baseline | GRPO Trained |
|---|---|---|
| `task_easy` | 27.6 | 27.6 |
| `task_medium` | 48.7 | 48.7 |
| `task_karnataka` | 19.6 | -316.9 |

**Key Finding**: Naive LLM training on simplified proxy rewards does not transfer to real-world grid topologies — Karnataka collapses to -316.9. This validates our architectural decision to pair RL agents with a **safety layer + oversight agent**. The heuristic baseline with safety corrections (19.6 reward, zero blackouts) outperforms pure RL, proving that critical infrastructure needs guardrails, not just learned policies.

> **Reproduce training**: Open `training/opengrid_grpo_colab.ipynb` in Google Colab (T4 GPU)

---

## Technical Details

<details>
<summary><strong>Physics Engine</strong></summary>

- **DC Power Flow** with B-matrix formulation (standard power systems approximation)
- **Slack bus** absorbs generation/load imbalance after each power flow solve
- **Islanding detection** via NetworkX graph connectivity checks
- **Droop frequency model** calibrated to system size: `f = 50.0 - (2.5 / total_capacity) * P_slack`

</details>

<details>
<summary><strong>Multi-Agent Design</strong></summary>

- Buses partitioned into zones using **greedy modularity community detection** (NetworkX)
- Each zone maps to a KPTCL transmission region (Bengaluru, Mysuru, Kalburagi)
- **Partial observability**: agents see only local buses, boundary lines, noisy frequency
- **Neighbor signals**: each agent receives average injection of adjacent zones
- **Safety-first**: all actions validated by constraint filter before physics engine

</details>

<details>
<summary><strong>Thread Safety</strong></summary>

- All session reads/writes are protected by a `threading.Lock`
- Grader bounds use double-checked locking to avoid duplicate rollouts
- Safe for concurrent requests from multiple agents

</details>

<details>
<summary><strong>Reproducibility</strong></summary>

| Component | Mechanism |
|---|---|
| Task grids | Seeded procedural generation (`np.random.default_rng`) |
| Zone partitioning | Deterministic community detection with seed |
| Wind variability | Per-episode RNG (same seed → same wind pattern) |
| Floor estimation | Seeded thrash policy + 10 diverse-seeded episodes |
| Ceiling | Analytical formula (deterministic) |
| Scoring | Shared `normalize_score()` across all endpoints |

</details>

---

## Related Work

- **Massgen**: When Multiple LLMs Think Together (Gradient Network, 2025)
- **Symphony**: Multi-Agent Intelligence in a Collective Fabric (Gradient Network, 2025)
- **Grid2Op**: Power grid RL environment (RTE, 2020)
- **OpenEnv**: Standardized agentic execution environments (Scalar/HuggingFace/Meta, 2026)

---

## Links

| Resource | URL |
|---|---|
| **Live Demo** | [huggingface.co/spaces/K446/Opengrid](https://huggingface.co/spaces/K446/Opengrid) |
| **GitHub Repo** | [github.com/krishnagoyal099/Opengrid_env](https://github.com/krishnagoyal099/Opengrid_env) |
| **API Docs (Swagger)** | [huggingface.co/spaces/K446/Opengrid/docs](https://k446-opengrid.hf.space/docs) |

---

## License

MIT — see [LICENSE](LICENSE) for details.
