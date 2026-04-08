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
<p align="center"><strong>Renewable Energy Grid Load-Balancing Environment for AI Agents</strong></p>

<p align="center">
  <a href="https://huggingface.co/spaces/K446/Opengrid"><img src="https://img.shields.io/badge/🤗%20Live%20Demo-HuggingFace%20Space-yellow" alt="Live Demo"></a>
  <a href="https://github.com/krishnagoyal099/Opengrid_env"><img src="https://img.shields.io/badge/GitHub-Repository-181717?logo=github" alt="GitHub"></a>
  <a href="https://github.com/openenv"><img src="https://img.shields.io/badge/OpenEnv-compatible-blue" alt="OpenEnv"></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT"></a>
</p>

---

## What is OpenGrid?

OpenGrid is a **reinforcement learning environment** where an AI agent controls a power grid. The agent's job is to keep the lights on — literally — by balancing electricity supply and demand in real-time while managing renewable energy sources like solar and wind.

This is the same problem real grid operators solve 24/7 in control rooms around the world. As countries adopt more renewable energy, this problem gets harder because solar and wind are unpredictable. OpenGrid lets AI agents learn to handle this challenge across three difficulty levels.

> **🔗 Try it live:** [huggingface.co/spaces/K446/Opengrid](https://huggingface.co/spaces/K446/Opengrid)

---

## How It Works

```
┌─────────────────────────────────────────────────────────┐
│                     GAME LOOP                           │
│                                                         │
│   Agent observes grid state (frequency, line loads)     │
│              │                                          │
│              ▼                                          │
│   Agent chooses action (adjust generators, batteries,   │
│   or switch transmission lines)                         │
│              │                                          │
│              ▼                                          │
│   Environment simulates physics (DC power flow)         │
│              │                                          │
│              ▼                                          │
│   Agent receives reward (+1 for survival, bonuses for   │
│   tight frequency control, penalties for overloads)     │
│              │                                          │
│              ▼                                          │
│   Repeat for 50 steps — or until blackout!              │
└─────────────────────────────────────────────────────────┘
```

The agent interacts with the environment through a **REST API** — send actions, receive observations. Any language or framework that can make HTTP requests can play.

---

## Three Difficulty Levels

| Task | Grid Size | Renewable Mix | What Makes It Hard |
|---|---|---|---|
| `task_easy` | 5 buses | 20% | Small grid — focus on frequency control basics |
| `task_medium` | 10 buses | 50% | Larger grid with volatile renewables + congestion |
| `task_hard` | 14 buses | 70% | Highly volatile supply, many lines, coordinated control needed |

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

Then open [http://localhost:7860](http://localhost:7860) — you'll see the interactive dashboard.

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

### Docker (Alternative)

```bash
docker build -t opengrid .
docker run -p 7860:7860 opengrid
```

---

## What the Agent Sees (Observations)

Every step, the agent receives:

| Field | Example | Meaning |
|---|---|---|
| `grid_frequency` | `49.87` | Current frequency in Hz (target: 50.0) |
| `buses[].type` | `"solar"` | Bus type: slack, generator, load, battery, solar, wind |
| `buses[].p_injection` | `35.2` | Power output in MW (negative = consuming) |
| `buses[].soc` | `18.5` | Battery charge level (0–50 MWh, batteries only) |
| `lines[].flow` | `62.4` | Power flowing through this line (MW) |
| `lines[].rho` | `0.78` | Line loading ratio (>1.0 = overloaded!) |
| `cooldowns` | `{"L_0_1": 2}` | Steps until a line can be switched again |
| `is_blackout` | `false` | Game over if `true` |

## What the Agent Can Do (Actions)

| Action | Example | What It Does |
|---|---|---|
| **Adjust bus power** | `{"bus_id": 2, "delta": 10.0}` | Ramp up generator/battery by 10 MW |
| **Adjust bus power** | `{"bus_id": 3, "delta": -5.0}` | Charge battery or reduce generator by 5 MW |
| **Switch line** | `{"line_id": "L_0_1", "action": "open"}` | Disconnect a transmission line (3-step cooldown) |
| **Switch line** | `{"line_id": "L_0_1", "action": "close"}` | Reconnect a transmission line |

> ⚠️ **Warning:** Switching lines carelessly can split the grid into islands → instant blackout!

---

## Reward System

| Component | Value | When |
|---|---|---|
| **Survival** | +1.0 / step | Grid stays connected |
| **Blackout** | −100.0 | Grid islands (game over) |
| **Frequency bonus** | +0.2 / step | Frequency within ±0.1 Hz of 50 Hz |
| **Frequency penalty** | up to −1.5 / step | Frequency drifts beyond ±0.5 Hz |
| **Overload penalty** | quadratic | Lines loaded beyond capacity |
| **Action cost** | −0.5 / switch | Each topology change costs this |

**Key design:** Even surviving with terrible frequency (50 steps × −1.5 = −75) is better than a blackout (−100). The agent should **always prioritize keeping the grid connected**.

---

## Scoring

Scores are normalized to **(0.02 – 0.98)** using:

```
score = (agent_reward − worst_case) / (best_case − worst_case) + N1_bonus
```

| Bound | How It's Computed |
|---|---|
| **Worst case (floor)** | Random agent that chaotically switches lines — causes blackouts fast |
| **Best case (ceiling)** | Theoretical perfect agent: survives every step + perfect frequency bonus |
| **N-1 bonus** | Up to +10% for completing the episode without a blackout |

### What Scores Mean

| Score Range | Interpretation |
|---|---|
| **0.85 – 0.98** | Excellent — matches or beats the heuristic baseline |
| **0.50 – 0.85** | Decent — agent learned basic grid control |
| **0.02 – 0.50** | Poor — frequent blackouts or bad frequency control |

### Baseline Scores (Heuristic Policy)

| Task | Score | Strategy |
|---|---|---|
| `task_easy` | ~0.90 | Proportional frequency control, no line switching |
| `task_medium` | ~0.98 | Same heuristic — medium grid happens to be well-balanced |
| `task_hard` | ~0.98 | Same heuristic — hard grid has more buses but similar dynamics |

> Reproduce with: `python get_scores.py`

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Interactive dashboard (web UI) |
| `/health` | GET | Health check → `{"status": "OpenGrid Running"}` |
| `/tasks` | GET | List all available tasks with schemas |
| `/reset?task_id=task_easy` | POST | Start new episode → returns session ID + initial observation |
| `/step?session_id=...` | POST | Send action (JSON body) → returns observation, reward, done |
| `/state?session_id=...` | GET | Get current grid state |
| `/grader?session_id=...` | GET | Get normalized score for this episode |
| `/baseline?use_llm=false` | GET | Run baseline policy on all tasks |
| `/visualize?session_id=...` | GET | Get grid visualization (base64 PNG) |

### Example: Play One Step

```bash
# 1. Start an episode
curl -X POST "http://localhost:7860/reset?task_id=task_easy"
# Returns: {"session_id": "abc-123", "observation": {...}}

# 2. Take an action
curl -X POST "http://localhost:7860/step?session_id=abc-123" \
  -H "Content-Type: application/json" \
  -d '{"bus_adjustments": [{"bus_id": 2, "delta": 5.0}], "topology_actions": []}'
# Returns: {"observation": {...}, "reward": {...}, "done": false, "info": {...}}

# 3. Check your score
curl "http://localhost:7860/grader?session_id=abc-123"
# Returns: {"score": 0.87, ...}
```

---

## Project Structure

```
Opengrid_env/
├── app.py                 # FastAPI server — all API endpoints
├── inference.py           # LLM agent inference script
├── openenv.yaml           # OpenEnv hackathon specification
├── Dockerfile             # Container config for deployment
├── requirements.txt       # Python dependencies
├── get_scores.py          # Reproduce baseline scores locally
│
├── src/                   # Core environment logic
│   ├── models.py          # Pydantic data models (Action, Observation, Reward)
│   ├── environment.py     # Grid simulation engine (reset / step / state)
│   ├── physics.py         # DC power flow solver (B-matrix, slack bus)
│   ├── tasks.py           # Procedural grid generation (3 difficulties)
│   ├── grader.py          # Scoring system (floor/ceiling normalization)
│   ├── baseline.py        # Heuristic + LLM baseline policies
│   └── visualization.py   # Grid topology & frequency plots
│
├── static/                # Dashboard frontend (HTML/CSS/JS)
├── server/                # Alternative entry point for multi-mode deploy
└── tests/                 # Unit tests
```

---

## Technical Details

<details>
<summary><strong>🔬 Physics Engine</strong></summary>

- **DC Power Flow** with B-matrix formulation (standard power systems approximation)
- **Slack bus** absorbs generation/load imbalance after each power flow solve
- **Islanding detection** via NetworkX graph connectivity checks
- **Droop frequency model** calibrated to system size: `f = 50.0 − (2.5 / total_capacity) × P_slack`

</details>

<details>
<summary><strong>🔒 Thread Safety</strong></summary>

- All session reads/writes are protected by a `threading.Lock`
- Grader bounds use double-checked locking to avoid duplicate rollouts
- Safe for concurrent requests from multiple agents

</details>

<details>
<summary><strong>🎲 Reproducibility</strong></summary>

| Component | Mechanism |
|---|---|
| Task grids | Seeded procedural generation (`np.random.default_rng`) |
| Wind variability | Per-episode RNG (same seed → same wind pattern) |
| Floor estimation | Seeded thrash policy + 10 diverse-seeded episodes |
| Ceiling | Analytical formula (deterministic) |
| Scoring | Shared `normalize_score()` across all endpoints |

</details>

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
