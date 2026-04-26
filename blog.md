<div align="center">

<img src="./static/logo.png" alt="OpenGrid Logo" width="160" height="160">

# OpenGrid: How I Tried to Teach an LLM to Run a Power Grid

*A long, friendly walkthrough of the project. No PhD required.*

</div>

![OpenGrid Dashboard](docs/images/dashboard.png)
*This is the dashboard. The map shows the Karnataka grid as it actually exists — Kalaburagi, Hubballi, Mysuru, Bengaluru. Each colored circle is a bus, the lines are real transmission lines, and the numbers are flowing power in megawatts. By the end of this post you'll know exactly what's going on here.*

---

## Links

- **Live demo:** [huggingface.co/spaces/K446/Opengrid](https://huggingface.co/spaces/K446/Opengrid)
- **Code:** [github.com/krishnagoyal099/Opengrid_env](https://github.com/krishnagoyal099/Opengrid_env)
- **Training notebook:** `training/opengrid_grpo_colab.ipynb` in the repo
- **API docs:** [/docs on the Space](https://k446-opengrid.hf.space/docs)

---

## The blackout that started it

July 30th, 2012. India's Northern Grid collapses. By the next day the failure has cascaded across two more grids and 600 million people are sitting in the dark — about a tenth of the human race.

Trains stop. Hospitals scramble for backup power. Traffic lights die. Coal mines flood because the pumps are off.

Now — what actually causes a blackout like that? It's not one big switch flipping off. It's a **chain of small things**.

A line gets overloaded somewhere. It trips off. The power that was flowing through it now has to go somewhere — so it pushes onto the next line, which now also overloads, and trips. The next line trips. And the next. In about 60 seconds, half a country has no electricity.

The grid runs on a knife's edge, and **someone, somewhere, has to keep balancing it every single second.** Right now that someone is a small team of human operators sitting in control rooms across India, looking at giant screens, making decisions in seconds.

This project started with a simple question: **can we teach an AI to do that job?**

Not to replace the humans. Just to help. Because we're about to make their job a lot harder.

---

## Why the job is getting harder

Here's the thing nobody tells you about renewable energy. Solar and wind are amazing for the climate. They are also a nightmare for grid operators.

A coal plant generates a steady, predictable amount of power. You tell it "give me 500 MW" and it gives you 500 MW.

A solar farm generates power based on **whether a cloud just floated past it.** A wind farm generates power based on **whether the wind is blowing this minute.** And the grid doesn't care about excuses — it needs supply to match demand exactly, all the time, or the frequency drifts and things start exploding.

In 2012, India's grid was about 2% renewables. Today it's 24%. By 2030 the target is 50%. We're tripling the unpredictability of the supply side and pretending the existing tools will keep up.

They won't. We need better tools. And one of those tools, very plausibly, is **an AI that helps the operator make decisions.**

But here's the catch — you can't just throw an LLM at a real grid and ask it to start flipping switches. If it gets things wrong, people die. So you need a place to **train it, test it, break it, fix it, and prove it's safe** before it ever touches reality.

That place is what I built. I called it **OpenGrid.**

---

## The hackathon

This project was for the OpenEnv hackathon. The format had two rounds:
- Round 1 — build something
- Round 2 — make it better

I'll walk you through both.

---

## Round 1: Get the physics right

Most "RL environment" projects you see online have one big flaw: they fake the physics.

It looks like this:
```python
def step(action):
    if action == "reduce_load":
        reward += 1
    else:
        reward -= 1
```

That's not a power grid. That's a Markov chain wearing a costume.

I wanted the **real equations**. Because if the physics is fake, the AI is learning to game a fake puzzle, not solve a real one. The whole point falls apart.

So I started here:

### What is a power grid, mathematically?

Think of the grid as a network of nodes (called **buses**) connected by wires (called **lines**). Each bus has either:
- A **generator** that pushes power in (coal, gas, solar, wind, hydro)
- A **load** that pulls power out (homes, factories)
- A **battery** that can do either, depending on its state of charge
- A **slack bus** — a special bus that absorbs whatever imbalance exists, like a shock absorber

Power flows through the lines based on the **angle differences** between connected buses. There's a clean equation for it:

```
B × θ = P
```

Where `B` is a matrix describing how the lines are connected, `θ` is the voltage angle at each bus, and `P` is the power injected at each bus. Given the injections, you solve for the angles, and from the angles you get the line flows.

This is called **DC power flow**. It's an approximation — the real version involves complex numbers and trig functions — but it's the same approximation grid operators actually use for fast planning. So that's what I built.

### Frequency

The grid has a target frequency — 50 Hz in India, 60 Hz in the US. If supply > demand, frequency rises. If demand > supply, frequency drops.

Drop too low and generators trip off to protect themselves. They tripping off makes the imbalance worse. More generators trip. **That's a blackout.**

So I modeled frequency with a droop equation:

```
f = 50.0 − (2.5 / total_capacity) × P_slack
```

`P_slack` is how much the slack bus is having to absorb. If everyone's perfectly balanced, slack absorbs 0, frequency is exactly 50 Hz. The bigger the imbalance, the further frequency drifts.

### Islanding

Sometimes if you trip a line, you don't just lose power — you split the grid into **two disconnected pieces**. One piece might have generators but no load. The other might have loads but no generators. Both pieces are doomed.

This is called **islanding**, and the safety check for it is a graph connectivity test. I used Union-Find (a classic algorithm — same one you'd use for "are these two cities connected by roads?") to detect it in O(n) time.

### What I had at the end of round 1

- A working DC power flow solver
- Real droop frequency dynamics
- Islanding detection
- A simple environment exposing it as `/reset` and `/step` over HTTP
- A heuristic baseline that scored ~0.90 on the easy task

It worked. I could send it actions, it would simulate the consequences, and tell me whether the grid was still standing.

But it had **one big problem.**

---

## The problem with one operator

Real grids aren't run by one operator looking at the whole country. They're run by **many operators**, each watching their region. Bengaluru has its own control room. So does Mysuru. So does Kalburagi.

And those operators don't see everything. They see their region in detail, and they hear about the rest of the grid through summary signals.

This is what's called a **POMDP** in RL — a Partially Observable Markov Decision Process. The "P" stands for partial. The agents are missing information, on purpose, because that's what reality is like.

A single-agent environment is a lie. It assumes one operator with a god-view. That's not how grids work, and the AI you train on it won't work in the real world.

So in round 2 I went multi-agent.

---

## Round 2: Multi-agent, safety, and an oversight agent

### Splitting the grid into zones

First problem — how do you decide which buses belong to which zone?

You could hand-draw it, but that doesn't scale. So I used **community detection** from graph theory. The idea: split the network into chunks where buses inside a chunk are well-connected to each other, but only loosely connected to other chunks. NetworkX has a function called `greedy_modularity_communities` that does exactly this.

For the Karnataka grid, I checked the partitioning against the **actual KPTCL transmission regions** — Bengaluru, Mysuru, Kalburagi, Hubballi. The algorithm found the same boundaries the humans use. Which is a nice sanity check.

### What does each agent see?

Each agent gets a **partial observation**. They see:
- Their own buses (type, output, load)
- Lines inside their zone (flows, capacity)
- Lines on the boundary with other zones
- A noisy reading of the grid frequency (sensors aren't perfect, so I add Gaussian noise)
- A summary signal from each neighboring zone (the average power injection there)
- That's it.

They don't see other zones' buses. They don't see other zones' line flows. They don't even see their own frequency cleanly — there's measurement noise on it.

This is what real operators deal with. So this is what the agents deal with too.

### The safety layer

This is the part I'm most happy with.

In normal RL, when an agent does something stupid, you just penalize it and let it learn. But you can't do that with a power grid. **Some actions can't be allowed at all.**

If an agent decides to open the only line connecting Bengaluru to the rest of the grid — that's a blackout. Game over. You can't let that happen even once.

So I built a **safety layer** that sits between the agent and the physics engine:

```
Agent's action → Safety Layer → (corrected) action → Physics Engine
```

The safety layer runs six checks:
1. **Zone boundary** — agents can't reach into other zones
2. **N-1 security** — for each line, simulate it failing. If the grid would blackout, block the action that puts us into this risky state.
3. **Anti-islanding** — if opening this line would disconnect the grid, block it.
4. **Ramp limits** — generators can't ramp instantly. A coal plant changing output by 200 MW per minute is not physically possible. Clamp it.
5. **Capacity limits** — don't push a generator past its max or below its min.
6. **Battery state of charge** — don't discharge below empty or charge above full.

But here's the clever bit. **Unsafe actions don't get rejected — they get projected.**

Say an agent wants to ramp a generator by +100 MW, but the ramp limit is +30 MW per step. A normal "constraint check" would say "denied, do nothing." That's wasteful — the agent had a useful idea! It just overshot.

Instead, the safety layer **clamps the action to the nearest safe alternative** — in this case, +30 MW. The agent's intent is preserved. The grid stays safe. And the RL training signal is much richer, because every action now has measurable consequences.

This is borrowed from a technique in safe RL called **Control Barrier Functions** (Ames et al., 2019). It's the same idea behind self-driving car safety — you don't refuse to turn the wheel, you just don't let the wheel go past where it would crash.

### The oversight agent

There's one more failure mode I needed to handle.

When you have multiple agents trying to optimize their own zone, sometimes they make decisions that are great for them and terrible for the grid as a whole. Imagine three operators, each refusing to ramp down their generators because their zone's frequency is fine — but together they're causing massive overgeneration on the national grid.

Game theorists call this the tragedy of the commons. RL researchers call it **selfish behavior** in multi-agent settings.

To handle this, I added an **oversight agent**. It's not really an "agent" in the RL sense — it's more like a referee. After every step, it looks at:
- What each agent did
- What the global grid state is
- Whether the agents' actions are pulling in the same direction or fighting each other

If two agents are working against each other (one ramping up while the other ramps down for no good reason), the oversight agent dishes out a coordination penalty. This pushes the agents to learn cooperative behavior, not just locally-optimal behavior.

### The reward function

The reward is the most important thing in any RL setup. Get this wrong and the agent learns weird, broken behavior. Get it right and the agent generalizes.

I broke the reward into **six independent pieces**:

| Piece | What it rewards |
|---|---|
| `survival` | Did the grid stay up this step? Big reward if yes, huge penalty if blackout |
| `frequency` | How close is frequency to 50 Hz? |
| `local_congestion` | Penalty for overloaded lines in your zone |
| `safety_compliance` | Small penalty if the safety layer had to fix your action |
| `coordination` | Penalty from the oversight agent for selfish moves |
| `action_cost` | Small penalty for switching topology (those things wear out) |

Each piece is independent. You can tune the weights. You can ablate individual components and see which ones matter. You can plot which agent is being penalized for what.

This kind of decomposed reward is gold for debugging.

### A real-world topology

Procedural grids are fine for unit tests, but if you really want to know whether your AI works, you have to test it on a **real grid**.

So I encoded the **15-bus Karnataka KPTCL grid**. Real bus locations (with GPS coordinates so the dashboard can show them on a Leaflet map). Real line connections. Real generator capacities, modeled after Karnataka's actual generation mix — coal at Raichur, hydro at Sharavathi, solar in Pavagada, wind in Chitradurga.

#### Why Karnataka specifically?

Two reasons.

**First, the hackathon was in Bangalore.** It felt right to build something rooted in the place I was building it. The Karnataka grid is what powers the room I was sitting in while writing the code. There's something nice about a project that's literally about the electricity flowing through the wall behind your laptop.

**Second, doing all of India would have been computationally impossible.** The Indian national grid has 5 regional grids, dozens of state utilities, and **thousands of buses** when you count them all. Solving DC power flow on a network that size, every step, for thousands of training rollouts, would have eaten weeks of GPU time and never finished inside a hackathon.

Karnataka is a **realistic-but-tractable** middle ground. 15 buses is small enough that the physics solves in milliseconds, but big enough that it has the same structural challenges as a real regional grid — 4 transmission zones, mixed generation (coal, hydro, solar, wind), real geographic distances, real load centers. You can train on it overnight on a single GPU. And anything you learn on this scale is a reasonable starting point for going bigger later.

So `task_karnataka` is the centerpiece. You're not playing with a toy — you're operating the actual Karnataka grid topology, in simulation, on hardware you can actually afford.

I also added three "stress test" variants — `karnataka_easy`, `karnataka_medium`, `karnataka_hard` — where I slowly crank up the volatility of renewables, the rate of equipment faults, and the share of inflexible generation. The hard version's heuristic baseline gets `−417` average reward. It's brutal on purpose.

---

## Training the model

Now for the part everyone wants to know about — does the AI actually learn?

### The choice of algorithm: GRPO

I used **GRPO** — Group Relative Policy Optimization. It's a recent algorithm (DeepSeek-Math 2024) that's especially good for LLM fine-tuning because it doesn't need a separate critic network. You just generate K samples for each prompt, compute their rewards, and use the relative ranking inside each group as the training signal.

For this problem it's a perfect fit. For each grid state I generate 4 candidate actions from the LLM, score each one by **actually stepping the simulator**, and let GRPO push the model toward the higher-scoring actions.

### The choice of model: Qwen2.5-1.5B-Instruct

Why this model?

- Small enough to fit on free Colab GPUs (T4)
- Apache 2.0 license — no usage restrictions
- Strong instruction-following at this size
- Fits in 12 GB of VRAM with 4-bit quantization + LoRA

I used `bitsandbytes` for the 4-bit quantization and `peft` for LoRA (rank 16, alpha 32). This combination lets you fine-tune a 1.5B parameter model on consumer-grade hardware.

### The reward function for training

Now here is a really important point. In my first attempt at training, I used a **proxy reward** — I had a Python function that scored the LLM's JSON output based on things like "does it parse correctly" and "is the magnitude reasonable." It was a rough heuristic.

It didn't work. Reward stayed flat. The model learned to produce well-formatted JSON, but the actions weren't actually any better.

The fix was obvious in retrospect: **score the actions by their actual consequences, not by how they look.**

So the training reward function I shipped does this:
1. Parse the LLM's action from its output
2. Restore the environment to the observation state we sampled from
3. Step the environment with the LLM's action — get the **real** reward
4. Roll out 2 more steps with a heuristic policy — get the **trajectory** reward
5. Combine: `total = immediate_reward + 0.5 × rollout_reward`

The rollout step matters. Without it, the model learns greedy behavior. With it, the model learns to take actions that **set up future good states** — which is what RL is actually supposed to do.

I called this the "env-grounded reward" because every training signal traces back to actual physics. No more proxies.

### The training run

After all that setup, the actual training was almost anticlimactic.

- Model: Qwen2.5-1.5B-Instruct
- Hardware: NVIDIA A10G (23.9 GB)
- Steps: 449 (across 600 prompts)
- LR: 2e-5, cosine schedule
- Batch: 4 per device × 4 grad accum × 4 generations = effective 64

And the reward curve:

| Phase | Avg reward |
|---|---|
| Steps 1–5 | **−0.23** |
| Steps 100–150 | **+0.63** |
| Last 50 steps | **+0.66** |
| Peak | **+0.69** |

The model went from being **worse than random** to being meaningfully helpful. Not "human-level grid operator" — but the trajectory is there. Reward is rising. Loss is converging. The signal is real.

If I had more compute I'd train longer, with bigger models, on more diverse scenarios. But for a hackathon? This is enough to prove the pipeline works end-to-end.

---

## Things I learned

A few things stood out from this project. If you're building anything similar, save yourself some pain.

### 1. Ground your rewards in reality

If your RL reward is a proxy that doesn't match the thing you actually care about, your agent will optimize the proxy and ignore the goal. Always trace your reward back to a measurable, real-world signal. For me that meant stepping the simulator. For you it might mean something else.

### 2. Safety layers are not optional

In any domain where bad actions have catastrophic consequences — grids, robotics, medicine, finance — you cannot rely on the agent to learn safety from rewards alone. You need a hard constraint layer that enforces safety regardless of what the agent does. The agent then learns to operate **within** the safe set.

This isn't just an engineering preference. It's mathematically the only way to bound risk during training. Pure RL has no guarantees.

### 3. Multi-agent + partial observability is where the interesting stuff lives

Single-agent fully-observable environments are easy. They're also useless. Real-world deployment scenarios are almost always multi-agent (or at least multi-stakeholder) and partially observable. If you're not training on those conditions, you're not training for reality.

### 4. Build a dashboard early

I built the dashboard maybe halfway through the hackathon. I should have built it on day one. **Being able to see what's happening visually saves you from a thousand bugs.** A reward dropped to −100 on step 17? Just look at the dashboard. Oh, line 4 tripped because frequency hit 49.0 Hz. Now I know where to look.

### 5. Fake until it isn't

Round 1's heuristic agent was so simple it was almost embarrassing. Just proportional control on frequency. But it scored 0.90 on the easy task and gave me a baseline to beat. That baseline shaped everything else — it told me which scenarios were too easy (heuristic gets 0.98) and which were genuinely hard (Karnataka hard, where heuristic gets −417).

Without that baseline I'd have been flying blind.

---

## What I'd do next

If I had another month:

- **Train a bigger model** — Qwen 7B or even 14B. Reward curves usually keep improving with scale.
- **Add weather data** — the renewable variability right now is synthetic. Plugging in real ERA5 weather data would make scenarios much more realistic.
- **More attack scenarios** — what if a substation is captured by a cyberattack? What if a transmission line is sabotaged? These are the kinds of things grid operators actually plan for.
- **Hierarchical agents** — a coordinator agent that sees the whole grid and dispatches high-level plans, plus the zone agents that execute. This is closer to how real control rooms are organized.
- **Real-time deployment** — eventually, you want to take a trained policy and deploy it as **a recommender** for human operators. Not autonomous control, just "here's what I'd do if I were you, here's why." That's the realistic path to real-world adoption.

---

## Try it

If any of this sounds interesting, here are three things you can do right now, in order of effort:

**Easy** — open the [live demo](https://huggingface.co/spaces/K446/Opengrid). Click reset, click step, watch the grid evolve. Toggle the auto-run. Watch frequency drift toward the edge of the safe band.

**Medium** — point an LLM at it. The whole grid is exposed as REST endpoints. You don't even need Python — `curl` works. See [the README](README.md) for examples.

**Hard** — train your own agent. The code is at [github.com/krishnagoyal099/Opengrid_env](https://github.com/krishnagoyal099/Opengrid_env). The Colab notebook walks through the whole thing.

---

## Closing

I started this project because I think AI assisting grid operators is going to be one of the genuinely useful applications of LLMs in the next few years. It's a domain where a small efficiency improvement (1% better forecasting, 1% better dispatch) saves millions of dollars and prevents real human suffering.

It's also a domain where **getting it wrong kills people.** So we have to do it carefully. We have to build environments that capture the real physics. We have to enforce real safety constraints. We have to train on realistic topologies, not synthetic puzzles.

OpenGrid is my small contribution to that. It's a hackathon project, so it's far from complete. But the bones are there — the physics, the multi-agent structure, the safety layer, the oversight mechanism, the trained baseline.

If you build on top of it, send me a link. I'd love to see what you make.

Power to the grid. 🔌⚡

---

## Where the math comes from

Everything in OpenGrid is built on stuff that already exists in textbooks and papers — I didn't invent any of the physics or the algorithms. I just wired them together. If you want to verify any specific claim or just dig deeper, here's the paper trail.

### Power systems & physics

The DC power flow approximation is what almost every fast grid analysis tool uses, including planning tools at real utilities. The classic reference is **Stott, Jardim & Alsaç (2009), *DC power flow revisited*** ([IEEE](https://doi.org/10.1109/TPWRS.2009.2021235)) — that's where the B-matrix formulation `B × θ = P` comes from in its modern form. For the bigger picture of grid stability and droop control, **Kundur (1994), *Power System Stability and Control*** is the standard textbook every electrical engineer reads in graduate school.

The N-1 security criterion (the rule that says "the grid must survive the loss of any single line") isn't something I made up — it's literally written into Indian regulation as part of the **Indian Electricity Grid Code (IEGC)** by the [Central Electricity Regulatory Commission](https://cercind.gov.in/). For why blackouts cascade the way they do, **Carreras et al. (2004), *Complex dynamics of blackouts in power transmission systems*** ([AIP](https://doi.org/10.1063/1.1781391)) is a fascinating read. And the actual post-mortem of the 2012 India blackout I opened with is published as a [government report](https://powermin.gov.in/) by the Ministry of Power.

### The safety layer

The "project unsafe actions to nearest safe alternative instead of rejecting them" idea isn't mine. It comes from a body of work on **Control Barrier Functions** — a formal method for guaranteeing safety in continuous-time control systems. The accessible primer is **Ames et al. (2019), *Control Barrier Functions: Theory and Applications*** ([arXiv:1903.11199](https://arxiv.org/abs/1903.11199)).

For the broader theory of "RL with hard constraints," look up **Constrained MDPs** (Altman, 1999) and the survey by **García & Fernández (2015), *A Comprehensive Survey on Safe Reinforcement Learning*** ([JMLR](https://jmlr.org/papers/v16/garcia15a.html)).

### Multi-agent RL

The formal name for "multiple agents, each seeing only part of the world, having to cooperate" is a **Dec-POMDP** (Decentralized Partially Observable Markov Decision Process). The original complexity result that says these are hard — **NEXP-hard, in fact** — is **Bernstein et al. (2002)** ([INFORMS](https://doi.org/10.1287/moor.27.4.819.297)).

If you want to actually go deeper on multi-agent RL, the new free textbook **Albrecht, Christianos & Schäfer (2024), *Multi-Agent Reinforcement Learning*** ([marl-book.com](https://marl-book.com/)) is the best resource I've found. For practical algorithms, the MADDPG paper by **Lowe et al. (2017)** ([arXiv:1706.02275](https://arxiv.org/abs/1706.02275)) is the foundation of "centralized training, decentralized execution."

### GRPO and the training stack

GRPO, the algorithm I used to train the LLM, comes from **DeepSeek's math paper — Shao et al. (2024)** ([arXiv:2402.03300](https://arxiv.org/abs/2402.03300)). It's a clever simplification of PPO ([Schulman et al., 2017](https://arxiv.org/abs/1707.06347)) for problems where you can sample multiple completions and rank them.

The actual implementation I used is from Hugging Face's [TRL library](https://github.com/huggingface/trl). The 4-bit quantization that makes a 1.5B model fit on a free Colab GPU comes from **Dettmers et al. (2023), *QLoRA*** ([arXiv:2305.14314](https://arxiv.org/abs/2305.14314)). And LoRA itself is **Hu et al. (2021)** ([arXiv:2106.09685](https://arxiv.org/abs/2106.09685)) — which I think is one of the most influential ML papers of the last few years, in terms of how many people it's let fine-tune models on consumer hardware.

### Graph theory bits

The community-detection algorithm I used to partition the grid into zones is **Clauset, Newman & Moore (2004), *Finding community structure in very large networks*** ([Phys Rev E](https://doi.org/10.1103/PhysRevE.70.066111)). It's the same algorithm NetworkX exposes as `greedy_modularity_communities`.

The Union-Find I used for islanding detection is **Tarjan (1975)** ([JACM](https://doi.org/10.1145/321879.321884)) — a classic algorithm from before I was born, still the fastest way to check connectivity in a graph that's being edited.

### The Karnataka grid itself

The topology I encoded is based on KPTCL's [official transmission system maps](https://kptcl.karnataka.gov.in/), with generation capacities cross-checked against the [Central Electricity Authority's monthly capacity reports](https://cea.nic.in/). The GPS coordinates are real. The names are real. The line connections are based on their published 220 kV / 400 kV map. I haven't tried to model every substation — that would be impossible for one person — but the major load centers and generation hubs are accurate.

### Other environments worth knowing about

**Grid2Op** ([github](https://github.com/Grid2op/grid2op)) by France's RTE is the closest cousin to OpenGrid. It's bigger, more mature, and used in research competitions, but it's mostly single-agent and full-observability. **PowerGridworld** ([arXiv:2111.05969](https://arxiv.org/abs/2111.05969)) is a multi-agent power systems environment from NREL.

OpenGrid is smaller and rougher than either of those — but the multi-agent POMDP framing + safety layer + LLM-trainable API is a combination I haven't seen elsewhere.

---

*Built for the OpenEnv hackathon. Powered by FastAPI, TRL, Hugging Face, and a lot of coffee.*
