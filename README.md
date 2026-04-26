---
title: OpenGrid
emoji: ⚡
colorFrom: green
colorTo: blue
sdk: docker
app_file: app.py
pinned: false
---

<div align="center">

<img src="./static/logo.png" alt="OpenGrid Logo" width="160" height="160">

# OpenGrid ⚡

**A power grid you can train an AI to operate.**

[![Live Demo](https://img.shields.io/badge/🤗%20Live%20Demo-HuggingFace%20Space-yellow)](https://huggingface.co/spaces/K446/Opengrid)
[![GitHub](https://img.shields.io/badge/GitHub-Repository-181717?logo=github)](https://github.com/krishnagoyal099/Opengrid_env)
[![Blog](https://img.shields.io/badge/📖-Read%20the%20story-blue)](https://huggingface.co/spaces/K446/Opengrid/blob/main/blog.md)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

---

## In one line

OpenGrid is a **simulated power grid** with real physics. AI agents log in, see what's happening on their patch of the grid, and try to keep the lights on without causing a blackout.

> **Try it live:** [huggingface.co/spaces/K446/Opengrid](https://huggingface.co/spaces/K446/Opengrid)
> **Read the full story:** [blog.md](https://huggingface.co/spaces/K446/Opengrid/blob/main/blog.md)

![OpenGrid Dashboard — multi-agent control room running on the Karnataka topology](docs/images/dashboard.png)
*The live dashboard during a Karnataka episode: 4 zones, real GPS coordinates, frequency gauge, generation mix, reward history. Agent 0 (Kalaburagi) is highlighted in the side panel.*

---

## What's inside

- **A real physics engine** — DC power flow, frequency dynamics, line overloads, blackouts. Same equations grid operators use.
- **A real grid topology** — the 15-bus Karnataka KPTCL grid (Raichur, Ballari, Bengaluru, Mysuru) with actual GPS coordinates.
- **Multiple AI agents** — each agent only sees their own zone. Just like real control rooms, they have to coordinate without a god-view.
- **A safety layer** — before any action touches the grid, it gets checked for things like "will this cause a blackout?" Unsafe actions get fixed automatically.
- **An oversight agent** — watches the agents, notices when they're working against each other, and penalizes selfish moves.
- **A live dashboard** — Leaflet map, frequency gauge, generation mix donut, reward charts. Looks like a SCADA control room because that's the point.
- **A trained model** — we fine-tuned Qwen2.5-1.5B with GRPO. Reward went from −0.23 → +0.66 over 449 training steps.
- **Two training pipelines** — both a standard `transformers + bitsandbytes + peft` stack and an [Unsloth](https://unsloth.ai/)-accelerated stack (~2× faster). Same env-grounded GRPO reward, same `summary.json` schema. Pick whichever fits your GPU.

---

## Why this matters

Power grids run on a knife's edge. Frequency must stay near 50 Hz. A few seconds of imbalance and you get cascading failures — the kind that took out half of Spain in April 2025, or 600 million Indians in 2012.

We're putting more solar, more wind, more EVs, more batteries on the grid every year. The job is getting harder. People are starting to ask: **can AI help control this?**

OpenGrid is a sandbox for that question. You can train an LLM, an RL policy, or just write a heuristic in 20 lines of Python — point it at the API and see how it does.

---

## How it works (the 30-second version)

```
1. The grid runs a tick. Frequency is 50.02 Hz, one line is at 95% capacity.
2. Each agent sees its own zone — local buses, line flows, a noisy global frequency reading.
3. Each agent picks an action — bump up a generator by +5 MW, switch a line off, or do nothing.
4. The safety layer checks every action. Anything dangerous gets corrected.
5. The oversight agent checks coordination. Are the agents fighting each other?
6. Physics solves the new state. Frequency updates. Line flows update.
7. Each agent gets a reward — based on grid stability + their own safety + their teamwork.
8. Repeat for 50 steps. Or until blackout, whichever comes first.
```

Agents talk to the grid over HTTP. Any language, any framework — it's just `POST /reset_multi` and `POST /step_multi`.

---

## The scenarios

Seven scenarios in total — four base grids and three difficulty variants of the Karnataka topology used for curriculum learning.

**Base grids**

| Task | Buses | Agents | Renewables | What's hard about it |
|---|---|---|---|---|
| `task_easy` | 5 | 2 | 20% | Just frequency control. A warmup. |
| `task_medium` | 10 | 3 | 50% | Volatile renewables + congested lines + 3 zones. |
| `task_hard` | 14 | 3 | 70% | Tight margins. Small mistakes blow up. |
| `task_karnataka` | 15 | 4 | Real mix | The actual KPTCL grid with GPS coordinates. |

**Karnataka stress-test variants** — same 15-bus topology, different operating conditions:

| Task | Renewables | Load | Line capacity |
|---|---|---|---|
| `karnataka_easy` | 0.3× | 0.6× | 1.5× |
| `karnataka_medium` | 0.7× | 1.0× | 1.0× |
| `karnataka_hard` | 1.3× | 1.4× | 0.75× |

Episodes run for 50 steps. Scores land between **0.02 and 0.98** (higher = better).

---

## Quick start

### Just want to play with it?

Open [the live demo](https://huggingface.co/spaces/K446/Opengrid) — no install needed.

### Run it locally

```bash
git clone https://github.com/krishnagoyal099/Opengrid_env.git
cd Opengrid_env
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 7860
```

Open [http://localhost:7860](http://localhost:7860). You'll see the dashboard.

### Run an LLM agent against it

```bash
export API_BASE_URL="https://api.openai.com/v1"
export MODEL_NAME="gpt-4o"
export HF_TOKEN="your-api-key"
export ENV_URL="http://localhost:7860"

python inference.py
```

### Train your own agent

We ship **two equivalent training paths** — pick whichever fits your environment.

**Standard stack** (`transformers + bitsandbytes + peft`) — used for the shipped run:

```bash
pip install -r requirements-training.txt
python training/train_grpo.py --test-mode   # smoke test (no GPU)
python run_training.py                       # full run (A10G/T4)
```

**Unsloth-accelerated stack** — ~2× faster, lower VRAM, same outcome:

```bash
pip install -r requirements-training-unsloth.txt
python run_training_unsloth.py
```

Or open one of the Colab notebooks in Google Colab (free T4 works for both):

| Notebook | Stack |
|---|---|
| `training/opengrid_grpo_colab.ipynb` | Standard (`transformers + bnb + peft`) |
| `training/opengrid_grpo_colab_unsloth.ipynb` | Unsloth |

Both notebooks produce the same `training/outputs/summary.json` schema, with a `framework` field identifying which path was used.

### Docker / Hugging Face Space — server vs training mode

The same image powers both the live control room and the GRPO training run.
The behaviour is selected by a single environment variable, **`OPENGRID_MODE`**:

| `OPENGRID_MODE` | What runs |
|---|---|
| *unset* (default) — or `server` | Boots `uvicorn app:app` on port 7860 — the live control-room dashboard. **This is what the public HF Space serves.** |
| `training`               | Starts the UI server in the background (so the HF health-check passes), then runs `python run_training.py` in the foreground. When training finishes, plots and `summary.json` are written to `training/outputs/` and the already-running UI keeps serving them. |

So, locally:

```bash
docker build -t opengrid .

docker run -p 7860:7860 opengrid                              # server mode (default)
docker run -p 7860:7860 -e OPENGRID_MODE=training opengrid    # train, then serve results
```

On Hugging Face Spaces, the variable is set under
*Settings → Variables and secrets* — flip it to `training` to retrain on a GPU
Space, flip it back to `server` (or remove it) to go back to live demo mode.
The shipped `summary.json` and plots in this repo were produced exactly that
way: a one-off `OPENGRID_MODE=training` run on an A10G Space, after which the
variable was reset so the Space serves the trained results.

---

## The API in 30 seconds

```bash
curl -X POST "http://localhost:7860/reset_multi?task_id=task_karnataka"
```

Returns a session ID and the initial observation each agent sees.

```bash
curl -X POST "http://localhost:7860/step_multi?session_id=YOUR-ID" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_actions": {
      "0": {"bus_adjustments": [{"bus_id": 0, "delta": 5.0}], "topology_actions": []},
      "1": {"bus_adjustments": [], "topology_actions": []}
    }
  }'
```

Returns per-agent observations, per-agent rewards, the safety layer's report, and the oversight agent's verdict.

> **Single-agent mode** (`/reset` and `/step`) is also supported for backward compatibility.
> **Full Swagger docs:** [/docs](https://k446-opengrid.hf.space/docs)

---

## What does an agent see?

Each agent gets a **partial observation** of their zone — never the full grid:

| Field | Example | What it means |
|---|---|---|
| `grid_frequency` | `49.87` | Frequency reading (with noise — sensors aren't perfect) |
| `local_buses` | `[{"type": "solar", "p_injection": 35.2}, ...]` | Buses in this zone |
| `boundary_lines` | `[{"rho": 0.78}, ...]` | Lines connecting to other zones |
| `internal_lines` | `[{"flow": 62.4}, ...]` | Lines inside this zone |
| `neighbor_signals` | `{"1": 12.5}` | Average injection of adjacent zones |
| `zone_load_mw` | `85.3` | Total demand in this zone |
| `zone_gen_mw` | `42.1` | Total generation in this zone |

That's it. No god-view. To coordinate, the agents have to read each other through neighbor signals and a noisy shared frequency reading.

---

## The safety layer

Every action gets validated **before** it touches the physics engine:

| Check | What it stops |
|---|---|
| **Zone boundary** | Agents can't reach into other zones |
| **N-1 security** | Grid must survive losing any single line |
| **Anti-islanding** | Don't disconnect chunks of the grid |
| **Ramp limits** | Generators can only change so fast |
| **Capacity limits** | Don't push a generator past its max |
| **Battery SoC** | Don't discharge below empty or charge above full |

Unsafe actions don't just get rejected — they get **projected to the nearest safe alternative**. The agent's intent is preserved, but the grid stays safe. This gives the RL agent a much richer training signal.

---

## The reward

The reward is a sum of six independent pieces:

| Piece | Range | Why |
|---|---|---|
| `survival` | +1.0 / −100.0 | Did the grid stay up this step? |
| `frequency` | −1.5 to +0.2 | Bonus for being near 50 Hz, penalty for drifting |
| `local_congestion` | ≤ 0 | Penalty for overloaded lines in your zone |
| `safety_compliance` | −0.3 to +0.1 | Penalty if the safety layer had to fix your action |
| `coordination` | ≤ 0 | Penalty for conflicting with other agents |
| `action_cost` | −0.5 / switch | Topology changes are expensive |

Mix these in different weights and you get different "personalities" — a survival-first agent, a coordination-first agent, etc.

---

## Scoring

Raw rewards aren't comparable across tasks. So we normalize:

```
score = (your_reward − worst_case) / (best_case − worst_case) + N1_bonus
```

| Bound | How it's computed |
|---|---|
| **Worst case** | A chaotic random agent that flips lines and crashes the grid |
| **Best case** | An analytical upper bound: survives every step + perfect frequency |
| **N-1 bonus** | Up to +10% for finishing without a blackout |

Final score lands between **0.02 and 0.98**.

### Heuristic baseline scores

| Task | Score | Strategy |
|---|---|---|
| `task_easy` | ~0.90 | Proportional frequency control |
| `task_medium` | ~0.98 | Same heuristic, balanced grid |
| `task_hard` | ~0.98 | Same heuristic, more buses |
| `task_karnataka` | ~0.98 | 15-bus real grid, 4 zones |

> Reproduce: `python scripts/get_scores.py`

---

## Training results (GRPO)

We fine-tuned **Qwen/Qwen2.5-1.5B-Instruct** on `task_karnataka` using GRPO (Group Relative Policy Optimization).

### Setup

| Thing | Value |
|---|---|
| Model | Qwen/Qwen2.5-1.5B-Instruct |
| Framework | TRL `GRPOTrainer` + bitsandbytes 4-bit + PEFT LoRA |
| LoRA | rank=16, alpha=32, dropout=0.05 |
| Hardware | NVIDIA A10G (23.9 GB) |
| Steps | 449 across 600 prompts |
| Optimizer | paged_adamw_8bit, lr=2e-5, cosine |

### What happened

Reward went from **−0.23 → +0.66** (peak +0.69) over 449 training steps. The model learned to take grid actions that actually improve grid stability — not just produce well-formatted JSON.

| Phase | Avg reward |
|---|---|
| Steps 1–5 | −0.23 |
| Steps 100–150 | +0.63 |
| Last 50 steps | +0.66 |
| Peak | +0.69 |

![Training Reward Curve](training/outputs/training_reward_curve.png)

![Training Loss](training/outputs/training_loss.png)

### Baseline reward by task

| Task | Avg episode reward | Std |
|---|---|---|
| `task_easy` | 31.99 | 0.00 |
| `task_medium` | 46.69 | 0.36 |
| `task_karnataka` | 49.43 | 0.21 |
| `karnataka_easy` | 56.33 | 0.25 |
| `karnataka_medium` | 49.57 | 0.21 |
| `karnataka_hard` | −417.15 | 63.02 |

`karnataka_hard` is brutal on purpose — it stress-tests the system. The negative reward is the whole point: it shows the failure modes that the safety layer + oversight agent are designed to prevent.

> **Reproduce:** open `training/opengrid_grpo_colab.ipynb` in Colab (T4 works)
> **Live summary:** the deployed Space exposes everything at `/training-results`

---

## Project layout

```
OpenGrid/
├── app.py                       # FastAPI server
├── inference.py                 # LLM agent runner
├── run_training.py              # GRPO training — standard stack (bnb + peft)
├── run_training_unsloth.py      # GRPO training — Unsloth-accelerated path
├── generate_plots.py            # Rebuild plots from training logs
├── requirements.txt             # Runtime deps
├── requirements-training.txt    # Training deps (standard)
├── requirements-training-unsloth.txt  # Training deps (Unsloth)
├── openenv.yaml                 # OpenEnv manifest
├── Dockerfile                   # Container config
├── blog.md                      # The story behind the project
│
├── src/                         # Core environment
│   ├── environment.py           # Grid simulation
│   ├── physics.py               # DC power flow solver
│   ├── tasks.py                 # Procedural + Karnataka grids
│   ├── grader.py                # Scoring
│   ├── baseline.py              # Heuristic + LLM policies
│   ├── safety.py                # Safety layer
│   ├── oversight.py             # Oversight agent
│   └── visualization.py         # Plot helpers
│
├── training/                    # GRPO training
│   ├── train_grpo.py
│   ├── opengrid_grpo_colab.ipynb         # Colab — standard stack
│   └── opengrid_grpo_colab_unsloth.ipynb # Colab — Unsloth stack
│
├── tests/                       # 28 tests
├── scripts/                     # get_scores.py, verify_training.py
├── static/                      # Dashboard (HTML + JS + CSS)
└── server/                      # Alternate entry point
```

---

## Technical details

<details>
<summary><strong>Physics engine</strong></summary>

- DC power flow with B-matrix formulation
- Slack bus absorbs imbalance, voltage angle fixed at 0
- Islanding detection via Union-Find connectivity check
- Droop frequency model calibrated to system size: `f = 50.0 − (2.5 / total_capacity) × P_slack`

</details>

<details>
<summary><strong>Multi-agent design</strong></summary>

- Buses partitioned into zones using greedy modularity community detection
- Each zone maps to a KPTCL transmission region (Bengaluru, Mysuru, Kalburagi, Hubballi)
- Partial observability: agents see local buses, boundary lines, noisy frequency
- Neighbor signals: average injection of adjacent zones
- All actions go through the safety layer first

</details>

<details>
<summary><strong>Thread safety</strong></summary>

- Per-session locks serialize env operations
- Grader bounds use double-checked locking (no duplicate rollouts)
- Concurrent requests across sessions are fine

</details>

<details>
<summary><strong>Reproducibility</strong></summary>

| Thing | How |
|---|---|
| Task grids | Seeded `np.random.default_rng` |
| Zone partitioning | Deterministic community detection |
| Wind variability | Per-episode RNG |
| Floor estimation | Seeded thrash policy + 10 episodes |
| Ceiling | Closed-form analytical |
| Scoring | One shared `normalize_score()` |

</details>

---

## References & academic grounding

Every design decision in OpenGrid traces back to established power systems engineering, control theory, or RL research. If you want to verify the math or dig deeper:

### Power systems & physics

- **DC power flow / B-matrix formulation** — Stott, B., Jardim, J., & Alsaç, O. (2009). *DC power flow revisited.* IEEE Transactions on Power Systems, 24(3), 1290–1300. [DOI:10.1109/TPWRS.2009.2021235](https://doi.org/10.1109/TPWRS.2009.2021235)
- **Power system stability & droop control** — Kundur, P. (1994). *Power System Stability and Control.* McGraw-Hill. (The standard reference textbook)
- **N-1 security criterion** — *Indian Electricity Grid Code (IEGC), 2010 (as amended).* Central Electricity Regulatory Commission, Government of India. [cercind.gov.in](https://cercind.gov.in/)
- **Cascading failure dynamics** — Carreras, B. A., et al. (2004). *Complex dynamics of blackouts in power transmission systems.* Chaos, 14(3), 643–652. [DOI:10.1063/1.1781391](https://doi.org/10.1063/1.1781391)
- **2012 India blackout post-mortem** — *Report of the Enquiry Committee on Grid Disturbance in Northern Region on 30th July 2012.* Government of India, Ministry of Power. [powermin.gov.in](https://powermin.gov.in/)

### Safe reinforcement learning

- **Control Barrier Functions (action projection)** — Ames, A. D., et al. (2019). *Control Barrier Functions: Theory and Applications.* European Control Conference. [arXiv:1903.11199](https://arxiv.org/abs/1903.11199)
- **Constrained MDPs** — Altman, E. (1999). *Constrained Markov Decision Processes.* Chapman & Hall/CRC.
- **Safe RL survey** — García, J., & Fernández, F. (2015). *A Comprehensive Survey on Safe Reinforcement Learning.* JMLR, 16, 1437–1480. [JMLR](https://jmlr.org/papers/v16/garcia15a.html)

### Multi-agent RL & POMDPs

- **Decentralized POMDPs (Dec-POMDP)** — Bernstein, D. S., et al. (2002). *The Complexity of Decentralized Control of Markov Decision Processes.* Mathematics of Operations Research, 27(4), 819–840. [DOI:10.1287/moor.27.4.819.297](https://doi.org/10.1287/moor.27.4.819.297)
- **Multi-agent RL textbook** — Albrecht, S. V., Christianos, F., & Schäfer, L. (2024). *Multi-Agent Reinforcement Learning: Foundations and Modern Approaches.* MIT Press. [marl-book.com](https://marl-book.com/)
- **Centralized critic, decentralized actor** — Lowe, R., et al. (2017). *Multi-Agent Actor-Critic for Mixed Cooperative-Competitive Environments (MADDPG).* NeurIPS. [arXiv:1706.02275](https://arxiv.org/abs/1706.02275)

### LLM training (GRPO)

- **GRPO algorithm** — Shao, Z., et al. (2024). *DeepSeekMath: Pushing the Limits of Mathematical Reasoning in Open Language Models.* [arXiv:2402.03300](https://arxiv.org/abs/2402.03300)
- **PPO (the predecessor)** — Schulman, J., et al. (2017). *Proximal Policy Optimization Algorithms.* [arXiv:1707.06347](https://arxiv.org/abs/1707.06347)
- **TRL library** — von Werra, L., et al. (2020). *TRL: Transformer Reinforcement Learning.* [github.com/huggingface/trl](https://github.com/huggingface/trl)
- **LoRA** — Hu, E. J., et al. (2021). *LoRA: Low-Rank Adaptation of Large Language Models.* [arXiv:2106.09685](https://arxiv.org/abs/2106.09685)
- **bitsandbytes 4-bit (NF4) quantization** — Dettmers, T., et al. (2023). *QLoRA: Efficient Finetuning of Quantized LLMs.* NeurIPS. [arXiv:2305.14314](https://arxiv.org/abs/2305.14314)

### Graph theory (zone partitioning, islanding)

- **Modularity-based community detection** — Clauset, A., Newman, M. E. J., & Moore, C. (2004). *Finding community structure in very large networks.* Physical Review E, 70(6), 066111. [DOI:10.1103/PhysRevE.70.066111](https://doi.org/10.1103/PhysRevE.70.066111)
- **Union-Find with path compression** — Tarjan, R. E. (1975). *Efficiency of a Good But Not Linear Set Union Algorithm.* Journal of the ACM, 22(2), 215–225. [DOI:10.1145/321879.321884](https://doi.org/10.1145/321879.321884)

### Karnataka grid topology

- **KPTCL official transmission system map** — Karnataka Power Transmission Corporation Limited. [kptcl.karnataka.gov.in](https://kptcl.karnataka.gov.in/)
- **Karnataka generation mix** — Central Electricity Authority, *Monthly Installed Capacity Reports.* [cea.nic.in](https://cea.nic.in/)

### Comparable environments & projects

- **Grid2Op** — Donnot, B., et al. (2020). *Grid2Op: A testbed platform to model sequential decision making in power systems.* RTE-France. [github.com/Grid2op/grid2op](https://github.com/Grid2op/grid2op)
- **PowerGridworld** — Biagioni, D., et al. (2022). *PowerGridworld: A Framework for Multi-Agent Reinforcement Learning in Power Systems.* ACM e-Energy. [arXiv:2111.05969](https://arxiv.org/abs/2111.05969)
- **OpenEnv** — Scalar / Hugging Face / Meta (2026). *Standardized agentic execution environments.* [github.com/openenv](https://github.com/openenv)

---

## Links

| Resource | URL |
|---|---|
| Live demo | [huggingface.co/spaces/K446/Opengrid](https://huggingface.co/spaces/K446/Opengrid) |
| GitHub | [github.com/krishnagoyal099/Opengrid_env](https://github.com/krishnagoyal099/Opengrid_env) |
| Swagger | [/docs on the Space](https://k446-opengrid.hf.space/docs) |
| Story | [blog.md](https://huggingface.co/spaces/K446/Opengrid/blob/main/blog.md) |

---

## License

MIT — see [LICENSE](LICENSE).
