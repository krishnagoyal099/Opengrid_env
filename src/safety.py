"""
Safety Layer — Hard Constraint Filter for OpenGrid
===================================================
Validates agent actions BEFORE they are applied to the environment.
If constraints are violated, actions are projected to the nearest safe alternative.

This is the core safety innovation: constraint violations should NEVER
reach the physics engine. The safety layer catches them first.

Checks:
1. Anti-Islanding: topology actions that would disconnect the grid are blocked
2. N-1 Security: for each critical line, simulate failure → check grid survives
3. Generation Limits: bus adjustments respect ramp rates and capacity
4. Zone Boundary: agents can only adjust buses in their assigned zone

References:
- KPTCL N-1 security criterion (Indian Grid Code, IEGC)
- Control Barrier Functions for safe RL (Ames et al., 2019)
"""

import logging
import networkx as nx
import numpy as np
from typing import List, Dict, Tuple
from .models import GridAction, BusAdjustment, TopologyAction, SafetyReport

logger = logging.getLogger(__name__)


class SafetyLayer:
    """Hard constraint filter that validates and corrects agent actions.

    The safety layer sits between agents and the environment:
        Agent proposes action → SafetyLayer validates → corrected action → Environment

    If an action would cause a constraint violation, it is PROJECTED to the
    nearest safe alternative (not just rejected). This preserves the agent's
    intent while enforcing safety, and provides a richer training signal
    than binary accept/reject.
    """

    def __init__(self, config: Dict):
        self.config = config
        self.num_buses = config['num_buses']
        self.lines_config = config['lines']
        self.buses_config = config['buses']
        self.zone_assignments = config.get('zone_assignments', {})
        self.zone_enforcement = bool(self.zone_assignments)

        # Build config index for O(1) lookups
        self._bus_cfg_by_id = {b['id']: b for b in self.buses_config}

    def validate_and_correct(
        self,
        agent_id: int,
        proposed_action: GridAction,
        current_line_state: List[Dict],
        current_bus_state: List[Dict],
        cooldowns: Dict[str, int],
    ) -> Tuple[GridAction, SafetyReport]:
        """Full validation pipeline for one agent's proposed action.

        Returns:
            corrected_action: Safe version of the proposed action
            report: Details of what was checked and corrected
        """
        corrections = []
        n1_violations = 0

        # Track original action stats
        original_delta = sum(abs(a.delta) for a in proposed_action.bus_adjustments)
        proposed_topo_count = len(proposed_action.topology_actions)
        blocked_topo_count = 0

        # Build bus state index for O(1) lookups
        bus_dyn_by_id = {b['id']: b for b in current_bus_state}

        # --- 1. Zone boundary enforcement ---
        safe_bus_adj = []
        for adj in proposed_action.bus_adjustments:
            bus_zone = self.zone_assignments.get(adj.bus_id, -1)
            if not self.zone_enforcement or bus_zone == agent_id:
                # Agent owns this bus, or single-agent mode
                safe_bus_adj.append(adj)
            else:
                corrections.append(
                    f"Blocked bus {adj.bus_id} adjustment: "
                    f"belongs to zone {bus_zone}, not agent {agent_id}"
                )

        # --- 2. Generation limit enforcement ---
        # Aggregate adjustments per bus to prevent double-spending
        bus_deltas: Dict[int, float] = {}
        for adj in safe_bus_adj:
            bus_deltas[adj.bus_id] = bus_deltas.get(adj.bus_id, 0.0) + adj.delta

        clamped_bus_adj = []
        for bus_id, total_delta in bus_deltas.items():
            bus_cfg = self._bus_cfg_by_id.get(bus_id)
            bus_dyn = bus_dyn_by_id.get(bus_id)
            if bus_cfg is None or bus_dyn is None:
                corrections.append(f"Blocked bus {bus_id}: not found")
                continue

            delta = total_delta
            bus_type = bus_cfg['type']

            # Loads and renewables can't be directly adjusted
            if bus_type in ['load', 'solar', 'wind']:
                corrections.append(
                    f"Blocked bus {bus_id}: type '{bus_type}' is not controllable"
                )
                continue

            # Enforce ramp rate
            max_ramp = bus_cfg.get('ramp_rate', 20.0)
            if abs(delta) > max_ramp:
                delta = np.clip(delta, -max_ramp, max_ramp)
                corrections.append(
                    f"Clamped bus {bus_id} delta to ramp rate ±{max_ramp}"
                )

            # Enforce battery SoC limits
            if bus_type == 'battery':
                soc = bus_dyn.get('soc', 0.0)
                capacity = bus_cfg.get('capacity', 50.0)
                if delta > 0 and delta > soc:
                    delta = soc
                    corrections.append(
                        f"Clamped bus {bus_id} discharge to SoC={soc:.1f}"
                    )
                elif delta < 0 and abs(delta) > (capacity - soc):
                    delta = -(capacity - soc)
                    corrections.append(
                        f"Clamped bus {bus_id} charge to remaining capacity"
                    )

            # Enforce generator limits
            # NOTE: This is a best-effort projection based on pre-step state.
            # If multiple agents adjust the same bus via different zones,
            # the environment provides a secondary clamp.
            if bus_type in ['slack', 'generator']:
                current_p = bus_dyn.get('p', 0.0)
                new_p = current_p + delta
                min_p = bus_cfg.get('min_p', -50)
                max_p = bus_cfg.get('max_p', 100)
                if new_p < min_p or new_p > max_p:
                    new_p = np.clip(new_p, min_p, max_p)
                    delta = new_p - current_p
                    corrections.append(
                        f"Clamped bus {bus_id} to generation limits "
                        f"[{min_p}, {max_p}]"
                    )

            clamped_bus_adj.append(BusAdjustment(bus_id=bus_id, delta=delta))

        # --- 3. Topology safety (anti-islanding + N-1) ---
        # Build base graph once for all topology checks
        base_graph = self._build_connectivity_graph(current_line_state)

        safe_topo = []
        approved_opens: set = set()  # Track approved opens for cumulative check
        for t_act in proposed_action.topology_actions:
            line_id = t_act.line_id

            # Check cooldown
            if cooldowns.get(line_id, 0) > 0:
                corrections.append(
                    f"Blocked {line_id} switch: cooldown active "
                    f"({cooldowns[line_id]} steps)"
                )
                blocked_topo_count += 1
                continue

            # Check if opening this line would island the grid
            # (cumulative: checks against already-approved opens)
            if t_act.action == "open":
                if self._would_island(
                    line_id, base_graph, additional_opens=approved_opens
                ):
                    corrections.append(
                        f"Blocked opening {line_id}: would island the grid"
                    )
                    blocked_topo_count += 1
                    n1_violations += 1
                    continue
                approved_opens.add(line_id)

            safe_topo.append(t_act)

        # --- 4. N-1 check on final combined action ---
        if safe_topo:
            n1_fails = self._check_n1_post_action(safe_topo, current_line_state)
            if n1_fails > 0:
                n1_violations += n1_fails
                corrections.append(
                    f"N-1 warning: {n1_fails} lines would leave grid "
                    f"vulnerable after action"
                )

        corrected_action = GridAction(
            bus_adjustments=clamped_bus_adj,
            topology_actions=safe_topo
        )

        corrected_delta = sum(abs(a.delta) for a in clamped_bus_adj)

        was_corrected = len(corrections) > 0
        report = SafetyReport(
            agent_id=agent_id,
            was_corrected=was_corrected,
            correction_reason="; ".join(corrections) if corrections else "",
            n1_violations_detected=n1_violations,
            proposed_topology_actions=proposed_topo_count,
            blocked_topology_actions=blocked_topo_count,
            original_total_delta_mw=round(original_delta, 4),
            corrected_total_delta_mw=round(corrected_delta, 4),
        )

        return corrected_action, report

    def _build_connectivity_graph(
        self, current_line_state: List[Dict]
    ) -> nx.Graph:
        """Build the connectivity graph from current line state (once)."""
        G = nx.Graph()
        G.add_nodes_from(range(self.num_buses))

        line_dyn_by_id = {l['id']: l for l in current_line_state}
        for l_cfg in self.lines_config:
            l_dyn = line_dyn_by_id.get(l_cfg['id'])
            if l_dyn is not None and l_dyn.get('connected', True):
                G.add_edge(l_cfg['from'], l_cfg['to'])

        return G

    def _would_island(
        self,
        line_id: str,
        base_graph: nx.Graph,
        additional_opens: set = None,
    ) -> bool:
        """Check if opening a line would disconnect the grid.

        Takes cumulative approved opens into account so that
        multiple simultaneous opens are correctly checked.
        """
        additional_opens = additional_opens or set()

        # Find the edge for this line
        line_cfg = next(
            (l for l in self.lines_config if l['id'] == line_id), None
        )
        if line_cfg is None:
            return False

        # Build a test graph with all proposed removals
        G = base_graph.copy()
        # Remove previously approved opens
        for open_id in additional_opens:
            open_cfg = next(
                (l for l in self.lines_config if l['id'] == open_id), None
            )
            if open_cfg and G.has_edge(open_cfg['from'], open_cfg['to']):
                G.remove_edge(open_cfg['from'], open_cfg['to'])

        # Remove the line under test
        if G.has_edge(line_cfg['from'], line_cfg['to']):
            G.remove_edge(line_cfg['from'], line_cfg['to'])

        return not nx.is_connected(G)

    def _check_n1_post_action(
        self,
        topo_actions: List[TopologyAction],
        current_line_state: List[Dict],
    ) -> int:
        """Check N-1 security after applying proposed topology actions.

        For each remaining connected line, simulate its loss and check
        connectivity. Uses edge removal/restoration instead of rebuilding
        the full graph for each contingency.

        Returns the number of single-line contingencies that would island.
        """
        # Build the post-action line state
        post_state = {}
        for l_dyn in current_line_state:
            post_state[l_dyn['id']] = l_dyn.get('connected', True)
        for t_act in topo_actions:
            post_state[t_act.line_id] = (t_act.action == "close")

        # Build post-action graph once
        G = nx.Graph()
        G.add_nodes_from(range(self.num_buses))

        edge_to_line = {}
        for l_cfg in self.lines_config:
            if post_state.get(l_cfg['id'], True):
                u, v = l_cfg['from'], l_cfg['to']
                G.add_edge(u, v)
                edge_to_line[(u, v)] = l_cfg['id']

        # Test each contingency via edge removal/restoration
        n1_failures = 0
        for (u, v), line_id in edge_to_line.items():
            G.remove_edge(u, v)
            if not nx.is_connected(G):
                n1_failures += 1
            G.add_edge(u, v)  # restore

        return n1_failures

    def reset(self):
        """Reset any per-episode state (future-proofing)."""
        pass
