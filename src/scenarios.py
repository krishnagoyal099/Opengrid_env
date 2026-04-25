"""
Karnataka Grid Scenarios
========================
Generates difficulty variants of the Karnataka 15-bus grid.
Same topology (KPTCL transmission map), different operating conditions.

Scenarios vary:
- Renewable penetration (solar/wind max_p)
- Load magnitude (base_p multiplier)
- Line capacity (tighter or relaxed limits)
- Battery capacity
"""

import copy
from typing import Dict

from src.tasks import generate_karnataka_task

__all__ = ['generate_karnataka_scenario', 'KARNATAKA_SCENARIOS']


# Difficulty profiles: multipliers applied to the base Karnataka grid
_DIFFICULTY_PROFILES = {
    "easy": {
        "description": "Low renewables, light load, relaxed lines",
        "renewable_multiplier": 0.3,      # Solar/wind max_p scaled down
        "load_multiplier": 0.6,           # Loads are lighter
        "line_capacity_multiplier": 1.5,  # Lines can carry more
        "battery_capacity_multiplier": 1.5,  # More storage headroom
        "max_steps": 50,
    },
    "medium": {
        "description": "Moderate renewables, normal load, standard lines",
        "renewable_multiplier": 0.7,
        "load_multiplier": 1.0,
        "line_capacity_multiplier": 1.0,
        "battery_capacity_multiplier": 1.0,
        "max_steps": 50,
    },
    "hard": {
        "description": "High renewables, peak demand, tight lines",
        "renewable_multiplier": 1.3,      # More volatile supply
        "load_multiplier": 1.4,           # Peak demand
        "line_capacity_multiplier": 0.75, # Congested corridors
        "battery_capacity_multiplier": 0.7,  # Less storage
        "max_steps": 50,
    },
}


def generate_karnataka_scenario(difficulty: str, seed: int = 808) -> Dict:
    """Generate a Karnataka grid scenario at a given difficulty level.

    The base topology (15 buses, 18 lines, 4 zones) is identical across
    all difficulties. Only the operating conditions change:
    - Renewable generation capacity (solar/wind max_p)
    - Load demand (base_p on load buses)
    - Transmission line capacity
    - Battery storage capacity

    This enables curriculum learning on a consistent grid structure.
    """
    if difficulty not in _DIFFICULTY_PROFILES:
        raise ValueError(
            f"Unknown difficulty '{difficulty}'. "
            f"Available: {list(_DIFFICULTY_PROFILES.keys())}"
        )

    profile = _DIFFICULTY_PROFILES[difficulty]
    base = generate_karnataka_task(seed=seed)

    # Apply multipliers to buses
    for bus in base["buses"]:
        bus_type = bus["type"]

        if bus_type in ("solar", "wind"):
            bus["max_p"] = round(bus["max_p"] * profile["renewable_multiplier"], 1)

        elif bus_type == "load":
            bus["base_p"] = round(bus["base_p"] * profile["load_multiplier"], 1)

        elif bus_type == "battery":
            bus["max_p"] = round(bus["max_p"] * profile["battery_capacity_multiplier"], 1)
            bus["capacity"] = round(bus["capacity"] * profile["battery_capacity_multiplier"], 1)
            bus["init_soc"] = round(bus["capacity"] * 0.5, 1)

        elif bus_type == "slack":
            # Scale slack to cover the adjusted load
            total_load = sum(
                b["base_p"] * (profile["load_multiplier"] if b["type"] == "load" else 1.0)
                for b in base["buses"] if b["type"] == "load"
            )
            bus["max_p"] = max(200, round(total_load * 0.8, 1))
            bus["min_p"] = -bus["max_p"]

    # Apply line capacity multiplier
    for line in base["lines"]:
        line["capacity"] = round(line["capacity"] * profile["line_capacity_multiplier"], 1)

    # Update metadata
    base["id"] = f"karnataka_{difficulty}"
    base["difficulty"] = f"karnataka_{difficulty}"
    base["max_steps"] = profile["max_steps"]
    base["scenario_description"] = profile["description"]

    return base


# Pre-built scenario configs
KARNATAKA_SCENARIOS = {
    f"karnataka_{diff}": generate_karnataka_scenario(diff)
    for diff in _DIFFICULTY_PROFILES
}
