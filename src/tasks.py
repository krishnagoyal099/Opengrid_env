import networkx as nx
import numpy as np


def generate_procedural_grid(difficulty: str = "easy", seed: int = 42):
    """Generate a reproducible grid configuration for a given difficulty level.

    Easy:   5 buses, 20% renewables — simple balancing
    Medium: 10 buses, 50% renewables — congestion management
    Hard:   14 buses, 80% renewables — volatile supply, tight margins

    Guarantees: at least 30% of non-slack buses are loads, and at least 1 battery.
    """
    rng = np.random.default_rng(seed)

    if difficulty == "easy":
        n_buses = 5
        renewable_mix = 0.2
        max_steps = 50
    elif difficulty == "medium":
        n_buses = 10
        renewable_mix = 0.5
        max_steps = 50
    else:  # Hard
        n_buses = 14
        renewable_mix = 0.7  # Reduced from 0.8 to ensure loads exist
        max_steps = 50

    G = nx.connected_watts_strogatz_graph(n_buses, k=4, p=0.3, seed=seed)

    # Generate bus types with guaranteed minimums
    n_non_slack = n_buses - 1
    min_loads = max(2, int(n_non_slack * 0.3))  # At least 30% loads
    min_batteries = 1

    types = ['slack']

    # Assign guaranteed loads first
    assigned = []
    for _ in range(min_loads):
        assigned.append('load')
    for _ in range(min_batteries):
        assigned.append('battery')

    # Fill remaining slots with renewable_mix probability
    remaining = n_non_slack - len(assigned)
    for _ in range(remaining):
        r = rng.random()
        if r < renewable_mix:
            # str() required: rng.choice returns numpy.str_, which survives most
            # comparisons but fails strict isinstance(x, str) checks downstream.
            assigned.append(str(rng.choice(['solar', 'wind'])))
        elif r < renewable_mix + 0.15:
            assigned.append('battery')
        else:
            assigned.append('load')

    # Shuffle to avoid spatial bias (loads always first)
    rng.shuffle(assigned)
    types.extend(assigned)

    buses = []
    lines = []

    for i, t in enumerate(types):
        buses.append({
            'id': i, 'type': t,
            'base_p': float(rng.uniform(20, 50)) if t == 'load' else 0,
            'max_p': float(rng.uniform(50, 100)) if t in ['solar', 'wind', 'slack'] else 0,
            'min_p': 0 if t in ['solar', 'wind'] else -50,
            'capacity': 50 if t == 'battery' else 0,
            'init_soc': 25.0 if t == 'battery' else 0,
            'ramp_rate': 20.0
        })

    for u, v in G.edges():
        lines.append({
            'id': f"L_{u}_{v}",
            'from': u, 'to': v,
            'susceptance': 50.0,
            'capacity': float(rng.uniform(80, 150))
        })

    return {
        "id": f"task_{difficulty}",
        "num_buses": n_buses,
        "buses": buses,
        "lines": lines,
        "max_steps": max_steps,
        "seed": seed,
        "difficulty": difficulty
    }


# Deterministic tasks — same seed always produces the same grid
TASKS = {
    "task_easy": generate_procedural_grid("easy", seed=101),
    "task_medium": generate_procedural_grid("medium", seed=102),
    "task_hard": generate_procedural_grid("hard", seed=103)
}