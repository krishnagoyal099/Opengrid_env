# OpenGrid — Renewable Energy Grid Load Balancing Environment

[![OpenEnv](https://img.shields.io/badge/OpenEnv-compatible-blue)](https://github.com/openenv)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 🔋 Environment Description

**OpenGrid** simulates the real-world challenge of **renewable energy grid load balancing** — a task performed daily by grid operators worldwide. As renewable penetration increases (solar, wind), grid stability becomes harder to maintain due to supply volatility and the intermittent nature of these sources.

An AI agent must act as a **grid controller**, making decisions about:
- **Generator dispatch** — ramping conventional generators up/down
- **Battery storage management** — charging/discharging to buffer supply fluctuations
- **Transmission topology switching** — opening/closing lines to manage congestion

The environment uses **DC power flow analysis** with proper physics (B-matrix formulation, slack bus balancing) and a **droop-based frequency model** that ties frequency deviation to slack bus injection.

### Why This Matters
- Grid operators handle this task 24/7 in real control rooms
- Increasing renewable mix (20% → 80%) makes the problem progressively harder
- Poor decisions cause cascading failures and blackouts — exactly what agents must learn to avoid
- This is a genuine $100B+ industry problem, not a toy

---

## 🎮 Action Space

Actions are represented as a `GridAction` Pydantic model:

```python
class GridAction(BaseModel):
    bus_adjustments: List[BusAdjustment] = []   # Power injection changes
    topology_actions: List[TopologyAction] = []  # Line switching
```

| Field | Type | Description |
|---|---|---|
| `bus_adjustments[].bus_id` | `int` | Target bus ID |
| `bus_adjustments[].delta` | `float` | MW change (positive = inject more, negative = withdraw) |
| `topology_actions[].line_id` | `str` | Target line ID (e.g., `"L_0_1"`) |
| `topology_actions[].action` | `"open" \| "close"` | Switch line state (3-step cooldown) |

**Constraints:**
- Battery buses: delta clamped by state-of-charge (0–50 MWh)
- Generator/slack buses: delta clamped by ramp rate (±20 MW/step) and min/max limits
- Load, solar, wind buses: adjustments ignored (uncontrollable)
- Topology switches have a 3-step cooldown after each toggle

---

## 👁️ Observation Space

Observations are returned as a `GridObservation` Pydantic model:

```python
class GridObservation(BaseModel):
    timestep: int                    # Current step in the episode
    grid_frequency: float            # Hz — target is 50.0
    buses: List[BusState]            # All bus states
    lines: List[LineStatus]          # All line states with loading
    cooldowns: Dict[str, int]        # Remaining cooldown per line
    is_blackout: bool                # True if grid islanded
```

| Bus State Field | Description |
|---|---|
| `type` | `"slack"`, `"generator"`, `"load"`, `"battery"`, `"solar"`, `"wind"` |
| `p_injection` | Current power injection (MW), negative for loads |
| `soc` | State-of-charge (batteries only, 0–50 MWh) |
| `ramp_rate` | Maximum MW change per step |

| Line State Field | Description |
|---|---|
| `connected` | Whether the line is active |
| `flow` | Current power flow (MW) |
| `rho` | Loading percentage (flow/capacity). >1.0 = overloaded |

---

## 📋 Task Descriptions

| Task | Difficulty | Buses | Renewable Mix | Description |
|---|---|---|---|---|
| `task_easy` | Easy | 5 | 20% | Small grid, high droop sensitivity. Frequency control is the primary challenge. |
| `task_medium` | Medium | 10 | 50% | Mid-size grid with renewable volatility. Balanced frequency + congestion management. |
| `task_hard` | Hard | 14 | 70% | Large high-renewable grid. Volatile supply, many lines, coordinated control needed. |

All tasks run for **50 timesteps** per episode. Graders score performance 0.0–1.0.

### Reward Components
| Component | Description |
|---|---|
| `survival` | +1.0 per step (or -100.0 on blackout) |
| `frequency` | Bonus for tight control (<0.1 Hz deviation), penalty for large deviations |
| `overload` | Quadratic penalty for lines with rho > 1.0, small penalty for rho > 0.8 |
| `action_cost` | -0.5 per topology switch (discourages unnecessary switching) |

---

## 🏗️ Setup Instructions

### Prerequisites
- Python 3.10+
- Docker (for containerized deployment)

### Local Development

```bash
# Clone the repository
git clone https://github.com/K446/opengrid.git
cd opengrid

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn app:app --host 0.0.0.0 --port 7860

# Run tests
python -m pytest tests/ -v
```

### Docker

```bash
# Build
docker build -t opengrid .

# Run
docker run -p 7860:7860 opengrid

# Verify
curl http://localhost:7860/
```

### Inference (LLM Agent)

```bash
# Set required environment variables
export API_BASE_URL="https://api.openai.com/v1"
export MODEL_NAME="gpt-4o"
export HF_TOKEN="your-api-key"
export ENV_URL="http://localhost:7860"

# Start the environment server first, then:
python inference.py
```

---

## 📊 Baseline Scores

Heuristic baseline (proportional frequency control, no topology switching):

| Task | Score | Avg Raw Reward | N-1 Survival | Reward Floor | Reward Ceiling |
|---|---|---|---|---|---|
| `task_easy` | 1.00 | 28.4 | 100% | -102.5 | 28.4 |
| `task_medium` | 1.00 | 49.8 | 100% | -108.5 | 49.8 |
| `task_hard` | 1.00 | 50.3 | 100% | -104.9 | 50.3 |

> **Scoring methodology:** The reward floor is estimated from an adversarial random-topology-thrashing policy. The ceiling is the heuristic policy itself. Scores are normalized to 0.0–1.0 using the shared `normalize_score()` function. Both `/grader` and `/baseline` endpoints use identical normalization.
>
> **Note:** The heuristic scores 1.0 because it *defines* the ceiling. An LLM agent that employs active topology management and predictive battery scheduling can achieve higher raw rewards. Reproduce these scores with `python get_scores.py`.

---

## 📁 Project Structure

```
opengrid/
├── app.py                 # FastAPI application with all endpoints
├── inference.py           # LLM inference script (structured logging)
├── openenv.yaml           # OpenEnv specification
├── Dockerfile             # Container configuration
├── requirements.txt       # Python dependencies
├── get_scores.py          # Baseline score reproduction script
├── src/
│   ├── __init__.py
│   ├── models.py          # Pydantic models (Action, Observation, Reward)
│   ├── environment.py     # Core environment (reset/step/state)
│   ├── physics.py         # DC power flow solver
│   ├── tasks.py           # Procedural grid generation (3 difficulties)
│   ├── grader.py          # Empirical scoring (0.0–1.0)
│   ├── baseline.py        # Heuristic + LLM policies
│   └── visualization.py   # Grid topology & frequency plots
└── tests/
    ├── __init__.py
    └── test_solver.py     # Unit tests (11 tests)
```

---

## 🔧 API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Health check |
| `/tasks` | GET | List available tasks |
| `/reset?task_id=task_easy` | POST | Start new episode |
| `/step?session_id=...` | POST | Execute action (body: GridAction JSON) |
| `/state?session_id=...` | GET | Get current state |
| `/grader?session_id=...` | GET | Get episode score (0.0–1.0) |
| `/baseline?use_llm=false` | GET | Run baseline on all tasks |
| `/visualize?session_id=...` | GET | Get grid visualization (base64 PNG) |

---

## ⚡ Technical Details

### Physics Engine
- **DC Power Flow** with B-matrix formulation (standard power systems approximation)
- **Slack bus** properly absorbs generation/load imbalance after each solve
- **Islanding detection** via NetworkX graph connectivity analysis
- **Droop frequency model** calibrated to system size: `droop = 2.5 / (total_load + total_gen)` Hz/MW

### Reproducibility
- All tasks use seeded procedural generation (`np.random.default_rng`)
- Per-episode RNG for stochastic elements (wind variability)
- Same seed → identical initial conditions and dynamics

---

## 📜 License

MIT
