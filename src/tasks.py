"""
Grid Generator & Task Definitions
===================================
Generates reproducible power grid configurations for OpenGrid RL tasks.

Procedural grids use Watts-Strogatz small-world topology with
configurable difficulty (bus count, renewable penetration).

The Karnataka task is a hand-crafted 15-bus grid based on the
actual KPTCL transmission map.
"""

import copy
import networkx as nx
import numpy as np
from typing import Dict, List, Tuple

__all__ = ['generate_procedural_grid', 'generate_karnataka_task', 'TASKS', 'get_task']


# KPTCL-inspired zone names
def _get_zone_names(num_agents: int) -> List[str]:
    """Get human-readable zone names for a given agent count."""
    base_names = [
        "Bengaluru_Region", "Mysuru_Region", "Kalburagi_Region",
        "Belagavi_Region", "Mangaluru_Region",
    ]
    if num_agents <= len(base_names):
        return base_names[:num_agents]
    return [f"Zone_{i}" for i in range(num_agents)]


def _partition_into_zones(G: nx.Graph, num_agents: int) -> Dict[int, int]:
    """Partition graph nodes into balanced, connected zones.

    Returns mapping of {bus_id: agent_id}.
    Guarantees: every bus is assigned, each zone has at least 1 node,
    and zones are roughly balanced in size.

    NOTE: Uses greedy modularity which is deterministic for a given graph
    structure but not guaranteed across NetworkX versions.
    """
    nodes = sorted(G.nodes())
    n = len(nodes)

    if n <= num_agents:
        # Trivial case: 1 bus per agent
        return {node: i for i, node in enumerate(nodes)}

    try:
        communities = nx.community.greedy_modularity_communities(G, cutoff=num_agents)
        communities = [set(c) for c in sorted(communities, key=len, reverse=True)]
    except Exception:
        # Fallback: round-robin assignment by node index
        communities = [set() for _ in range(num_agents)]
        for i, node in enumerate(nodes):
            communities[i % num_agents].add(node)

    # If we got more communities than agents, merge smallest into largest
    while len(communities) > num_agents:
        smallest = communities.pop()
        communities[0] = communities[0] | smallest

    # If we got fewer, split the largest using topology-aware bisection
    while len(communities) < num_agents:
        largest = max(communities, key=len)
        communities.remove(largest)

        # Attempt topology-aware split
        subG = G.subgraph(largest).copy()
        split_done = False
        if nx.is_connected(subG) and len(largest) >= 2:
            # Find edge whose removal creates the most balanced partition
            best_edge, best_balance = None, float('inf')
            target = len(largest) / 2
            for u, v in subG.edges():
                subG.remove_edge(u, v)
                components = list(nx.connected_components(subG))
                if len(components) == 2:
                    balance = abs(len(components[0]) - target) + abs(len(components[1]) - target)
                    if balance < best_balance:
                        best_edge = (u, v)
                        best_balance = balance
                subG.add_edge(u, v)
            if best_edge:
                subG.remove_edge(*best_edge)
                parts = list(nx.connected_components(subG))
                communities.extend(parts)
                split_done = True

        if not split_done:
            # Fallback: arbitrary split
            largest_list = sorted(largest)
            half = len(largest) // 2
            communities.append(set(largest_list[:half]))
            communities.append(set(largest_list[half:]))

    # Ensure no empty zones
    for i, comm in enumerate(communities):
        if len(comm) == 0:
            # Steal a node from the largest community
            largest = max(communities, key=len)
            stolen = next(iter(largest))
            largest.remove(stolen)
            communities[i] = {stolen}

    zone_map = {}
    for agent_id, comm in enumerate(communities):
        for node in comm:
            zone_map[node] = agent_id

    return zone_map


def _classify_lines(
    lines_config: List[Dict], zone_assignments: Dict[int, int]
) -> Tuple[Dict[int, List[str]], Dict[int, List[str]]]:
    """Classify lines as internal (both endpoints in same zone) or boundary.

    Returns:
        internal_lines: {agent_id: [line_ids within this zone]}
        boundary_lines: {agent_id: [line_ids on this zone's boundary]}
    """
    agents = set(zone_assignments.values())
    internal = {a: [] for a in agents}
    boundary = {a: [] for a in agents}

    for line in lines_config:
        from_zone = zone_assignments.get(line['from'])
        to_zone = zone_assignments.get(line['to'])

        # Skip lines with unassigned bus endpoints
        if from_zone is None or to_zone is None:
            continue

        if from_zone == to_zone:
            internal[from_zone].append(line['id'])
        else:
            boundary[from_zone].append(line['id'])
            boundary[to_zone].append(line['id'])

    return internal, boundary


def generate_procedural_grid(difficulty: str = "easy", seed: int = 42):
    """Generate a reproducible grid configuration for a given difficulty level.

    Easy:   5 buses, 20% renewables — simple balancing
    Medium: 10 buses, 50% renewables — congestion management
    Hard:   14 buses, 70% renewables — volatile supply, tight margins

    Guarantees: at least 30% of non-slack buses are loads, and at least 1 battery.
    Includes multi-agent zone assignments for POMDP mode.
    """
    rng = np.random.default_rng(seed)

    if difficulty == "easy":
        n_buses = 5
        renewable_mix = 0.2
        max_steps = 50
        num_agents = 2  # Small grid: 2 agents
    elif difficulty == "medium":
        n_buses = 10
        renewable_mix = 0.5
        max_steps = 50
        num_agents = 3
    else:  # Hard
        n_buses = 14
        renewable_mix = 0.7
        max_steps = 50
        num_agents = 3

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
            assigned.append(str(rng.choice(['solar', 'wind'])))
        elif r < renewable_mix + 0.15:
            assigned.append('battery')
        else:
            assigned.append('load')

    # Shuffle to avoid spatial bias (loads always first)
    rng.shuffle(assigned)
    types.extend(assigned)

    # Estimate total load for slack bus sizing
    load_estimates = []
    buses = []
    lines = []

    for i, t in enumerate(types):
        base_p = float(rng.uniform(20, 50)) if t == 'load' else 0
        if t == 'load':
            load_estimates.append(base_p)

        # Set max_p based on bus type
        if t == 'battery':
            max_p = float(rng.uniform(30, 60))  # batteries can discharge
        elif t in ['solar', 'wind', 'generator']:
            max_p = float(rng.uniform(50, 100))
        elif t == 'slack':
            # Slack max_p sized to cover expected imbalance
            max_p = 0  # placeholder, set below
        else:
            max_p = 0

        buses.append({
            'id': i, 'type': t,
            'base_p': base_p,
            'max_p': max_p,
            'min_p': 0 if t in ['solar', 'wind', 'generator'] else -50,
            'capacity': 50 if t == 'battery' else 0,
            'init_soc': 25.0 if t == 'battery' else 0,
            'ramp_rate': 20.0 if t not in ['load', 'solar', 'wind'] else 0.0,
        })

    # Size slack bus to cover expected imbalance
    total_load_est = sum(load_estimates) if load_estimates else 100
    slack_max_p = max(100, total_load_est * 0.6)
    for b in buses:
        if b['type'] == 'slack':
            b['max_p'] = slack_max_p
            b['min_p'] = -slack_max_p

    for idx, (u, v) in enumerate(G.edges()):
        lines.append({
            'id': f"L_{idx}",
            'from': u, 'to': v,
            'susceptance': 50.0,
            'capacity': float(rng.uniform(80, 150))
        })

    # Multi-agent zone assignment
    zone_assignments = _partition_into_zones(G, num_agents)
    internal_lines, boundary_lines = _classify_lines(lines, zone_assignments)

    zone_names = _get_zone_names(num_agents)

    # Build per-zone bus lists
    zone_bus_ids = {a: [] for a in range(num_agents)}
    for bus_id, agent_id in zone_assignments.items():
        zone_bus_ids[agent_id].append(bus_id)

    return {
        "id": f"task_{difficulty}",
        "num_buses": n_buses,
        "buses": buses,
        "lines": lines,
        "max_steps": max_steps,
        "seed": seed,
        "difficulty": difficulty,
        # Multi-agent fields
        "num_agents": num_agents,
        "zone_assignments": zone_assignments,  # {bus_id: agent_id}
        "zone_names": zone_names,
        "zone_bus_ids": zone_bus_ids,  # {agent_id: [bus_ids]}
        "internal_lines": internal_lines,  # {agent_id: [line_ids]}
        "boundary_lines": boundary_lines,  # {agent_id: [line_ids]}
    }


def generate_karnataka_task(seed: int = 808) -> Dict:
    """
    A highly realistic 15-bus grid topology based on the actual Karnataka
    KPTCL transmission map. Nodes have real GPS coordinates for GIS rendering.
    """
    nodes = [
        {"id": 0, "name": "Raichur_TPS", "type": "slack", "lat": 16.20, "lon": 77.36, "max_p": 200, "base_p": 0},
        {"id": 1, "name": "Kalaburagi", "type": "load", "lat": 17.33, "lon": 76.83, "max_p": 0, "base_p": 40},
        {"id": 2, "name": "Belagavi", "type": "load", "lat": 15.85, "lon": 74.50, "max_p": 0, "base_p": 35},
        {"id": 3, "name": "Hubballi", "type": "load", "lat": 15.36, "lon": 75.13, "max_p": 0, "base_p": 45},
        {"id": 4, "name": "Ballari_TPS", "type": "generator", "lat": 15.14, "lon": 76.92, "max_p": 150, "base_p": 0},
        {"id": 5, "name": "Chitradurga_Wind", "type": "wind", "lat": 14.23, "lon": 76.40, "max_p": 80, "base_p": 0},
        {"id": 6, "name": "Pavagada_Solar", "type": "solar", "lat": 14.10, "lon": 77.27, "max_p": 120, "base_p": 0},
        {"id": 7, "name": "Sharavathi_Hydro", "type": "generator", "lat": 14.18, "lon": 74.83, "max_p": 100, "base_p": 0},
        {"id": 8, "name": "Shivamogga", "type": "load", "lat": 13.93, "lon": 75.57, "max_p": 0, "base_p": 30},
        {"id": 9, "name": "Mangaluru", "type": "load", "lat": 12.87, "lon": 74.88, "max_p": 0, "base_p": 50},
        {"id": 10, "name": "Hassan_BESS", "type": "battery", "lat": 13.01, "lon": 76.10, "max_p": 50, "base_p": 0},
        {"id": 11, "name": "Mysuru", "type": "load", "lat": 12.30, "lon": 76.64, "max_p": 0, "base_p": 40},
        {"id": 12, "name": "Nelamangala", "type": "battery", "lat": 13.10, "lon": 77.39, "max_p": 50, "base_p": 0},
        {"id": 13, "name": "Bengaluru_City", "type": "load", "lat": 12.97, "lon": 77.59, "max_p": 0, "base_p": 120},
        {"id": 14, "name": "Kolar_Solar", "type": "solar", "lat": 13.13, "lon": 78.13, "max_p": 60, "base_p": 0},
    ]

    edges = [
        (0,1), (0,4), (4,5), (4,6), (5,3), (3,2), (3,7),
        (7,8), (8,9), (8,10), (9,10),  # (9,10) added: connects Mangaluru within zone 2
        (10,11), (10,12), (5,12),
        (6,12), (12,13), (13,14), (11,13)
    ]

    buses = []
    for n in nodes:
        buses.append({
            'id': n['id'], 'name': n['name'], 'type': n['type'],
            'lat': n['lat'], 'lon': n['lon'],
            'base_p': n['base_p'], 'max_p': n['max_p'],
            'min_p': 0 if n['type'] in ['solar', 'wind', 'generator'] else -50,
            'capacity': 100 if n['type'] == 'battery' else 0,
            'init_soc': 50.0 if n['type'] == 'battery' else 0,
            'ramp_rate': 40.0 if n['type'] not in ['load', 'solar', 'wind'] else 0.0,
        })

    lines = []
    for idx, (u, v) in enumerate(edges):
        lines.append({
            'id': f"L_{u}_{v}", 'from': u, 'to': v,
            'susceptance': 80.0, 'capacity': 150.0
        })

    # Realistic agents based on regional discoms/SLDC zones
    zone_assignments = {
        0: 0, 1: 0, 4: 0,             # North Zone (Raichur/Bellary)
        2: 1, 3: 1, 5: 1, 7: 1, 8: 1, # Hubli/Central Zone
        9: 2, 10: 2, 11: 2,           # Mysuru/Coast Zone
        6: 3, 12: 3, 13: 3, 14: 3     # Bengaluru Zone
    }

    internal_lines, boundary_lines = _classify_lines(lines, zone_assignments)

    zone_bus_ids = {a: [] for a in range(4)}
    for b_id, a_id in zone_assignments.items():
        zone_bus_ids[a_id].append(b_id)

    return {
        "id": "task_karnataka",
        "num_buses": len(buses),
        "buses": buses,
        "lines": lines,
        "max_steps": 50,
        "seed": seed,
        "difficulty": "karnataka",
        "num_agents": 4,
        "zone_assignments": zone_assignments,
        "zone_names": ["Kalaburagi_Region", "Hubballi_Region", "Mysuru_Region", "Bengaluru_Region"],
        "zone_bus_ids": zone_bus_ids,
        "internal_lines": internal_lines,
        "boundary_lines": boundary_lines,
    }


def get_task(task_id: str) -> Dict:
    """Get a deep-copied task config by ID."""
    if task_id not in _TASK_GENERATORS:
        raise ValueError(
            f"Unknown task: {task_id}. "
            f"Available: {list(_TASK_GENERATORS.keys())}"
        )
    return copy.deepcopy(_TASK_GENERATORS[task_id]())


_TASK_GENERATORS = {
    "task_easy": lambda: generate_procedural_grid("easy", seed=101),
    "task_medium": lambda: generate_procedural_grid("medium", seed=102),
    "task_hard": lambda: generate_procedural_grid("hard", seed=103),
    "task_karnataka": lambda: generate_karnataka_task(),
}

# Deterministic tasks — same seed always produces the same grid
# NOTE: These are shared instances. Use get_task() for a mutable copy.
TASKS = {
    "task_easy": generate_procedural_grid("easy", seed=101),
    "task_medium": generate_procedural_grid("medium", seed=102),
    "task_hard": generate_procedural_grid("hard", seed=103),
    "task_karnataka": generate_karnataka_task()
}