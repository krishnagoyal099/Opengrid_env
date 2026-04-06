"""
Oversight Agent — Multi-Agent Coordination Monitor
===================================================
A rule-based meta-agent that monitors coordination quality across zones.

Responsibilities:
1. Detect conflicting actions (agents pulling frequency opposite ways)
2. Detect selfish behavior (local improvement at global cost)
3. Assign coordination penalties to agents
4. Track safety layer intervention frequency

This is NOT a trained agent — it's a deterministic rule engine that
provides additional reward signal to guide multi-agent learning.

References:
- Symphony: Multi-Agent Intelligence in a Collective Fabric (Gradient, 2025)
- Massgen: When Multiple LLMs Think Together (Gradient, 2025)
"""

import logging
import math
from typing import Dict, List
from .models import GridAction, SafetyReport, OversightReport

logger = logging.getLogger(__name__)


class OversightAgent:
    """Rule-based oversight agent for multi-agent coordination.

    Sits above zone agents and evaluates whether their combined actions
    are globally beneficial or harmful. Produces an OversightReport
    with coordination scores and penalties.
    """

    def __init__(self, config: Dict):
        self.config = config
        self.zone_assignments = config.get('zone_assignments', {})
        self.num_agents = config.get('num_agents', 1)
        self.intervention_history: Dict[int, int] = {
            i: 0 for i in range(self.num_agents)
        }

    def evaluate(
        self,
        agent_actions: Dict[int, GridAction],
        safety_reports: Dict[int, SafetyReport],
        pre_frequency: float,
        post_frequency: float,
        pre_bus_state: List[Dict],
        post_bus_state: List[Dict],
    ) -> OversightReport:
        """Evaluate multi-agent coordination quality.

        Args:
            agent_actions: {agent_id: GridAction} — proposed actions
            safety_reports: {agent_id: SafetyReport} — per-agent safety results
            pre_frequency: Grid frequency before this step
            post_frequency: Grid frequency after this step
            pre_bus_state: Bus states before actions
            post_bus_state: Bus states after actions

        Returns:
            OversightReport with scores, penalties, and notes
        """
        notes = []
        penalties: Dict[int, float] = {i: 0.0 for i in range(self.num_agents)}
        conflicts = 0
        selfish_count = 0

        # --- 1. Track safety interventions ---
        for agent_id, report in safety_reports.items():
            # Validate agent_id is within expected range
            if agent_id not in self.intervention_history:
                notes.append(f"WARNING: unknown agent_id {agent_id} in safety report")
                continue
            if report.was_corrected:
                self.intervention_history[agent_id] += 1
                # Penalty scales with repeated violations
                repeat_count = self.intervention_history[agent_id]
                penalties[agent_id] += 0.1 * min(repeat_count, 5)
                notes.append(
                    f"Agent {agent_id}: safety correction #{repeat_count}"
                )

        # --- 2. Detect conflicting frequency actions ---
        # If agents are pushing frequency in opposite directions, that's waste
        net_deltas = {}
        for agent_id, action in agent_actions.items():
            total_delta = sum(a.delta for a in action.bus_adjustments)
            n_topo = len(action.topology_actions)
            if n_topo > 0:
                notes.append(
                    f"Agent {agent_id}: {n_topo} topology action(s) "
                    f"not included in conflict analysis"
                )
            net_deltas[agent_id] = total_delta

        if len(net_deltas) >= 2:
            deltas = list(net_deltas.values())
            # Check if some agents inject and others withdraw significantly
            injectors = [d for d in deltas if d > 2.0]
            withdrawers = [d for d in deltas if d < -2.0]
            if injectors and withdrawers:
                conflicts += 1
                notes.append(
                    "Conflicting actions: some agents inject while others withdraw"
                )
                # Penalize the agent pushing AGAINST the needed direction
                freq_error = 50.0 - pre_frequency

                if abs(freq_error) > 0.1:
                    # Clear direction needed — penalize the opposing side
                    for agent_id, delta in net_deltas.items():
                        # If freq < 50 (need more injection) but agent withdraws
                        if freq_error > 0.1 and delta < -2.0:
                            penalties[agent_id] += 0.2
                            selfish_count += 1
                            notes.append(
                                f"Agent {agent_id}: withdrew {delta:.1f} MW "
                                f"when grid needed injection"
                            )
                        # If freq > 50 (need less injection) but agent injects
                        elif freq_error < -0.1 and delta > 2.0:
                            penalties[agent_id] += 0.2
                            selfish_count += 1
                            notes.append(
                                f"Agent {agent_id}: injected {delta:.1f} MW "
                                f"when grid had excess"
                            )
                else:
                    # Near-nominal: penalize all significant participants equally
                    for agent_id, delta in net_deltas.items():
                        if abs(delta) > 2.0:
                            penalties[agent_id] += 0.1
                            notes.append(
                                f"Agent {agent_id}: conflicting injection "
                                f"({delta:+.1f} MW) with no clear grid need"
                            )

        # --- 3. Evaluate frequency impact per agent ---
        freq_contribution: Dict[int, float] = {}
        freq_dev_before = abs(pre_frequency - 50.0)
        freq_dev_after = abs(post_frequency - 50.0)
        freq_improved = freq_dev_after < freq_dev_before

        for agent_id in range(self.num_agents):
            # Net MW delta (not frequency impact — would need droop constant)
            total_delta = net_deltas.get(agent_id, 0.0)
            freq_contribution[agent_id] = round(total_delta, 4)

        # --- 4. Compute coordination score ---
        # Sub-linear scaling: diminishing penalty per additional incident
        # prevents score from collapsing to 0.0 for mildly bad teams
        safety_corrections = sum(
            1 for r in safety_reports.values() if r.was_corrected
        )

        conflict_penalty = 1.0 - math.exp(-conflicts * 0.3)
        selfish_penalty = 1.0 - math.exp(-selfish_count * 0.2)
        safety_penalty = 1.0 - math.exp(-safety_corrections * 0.2)

        base_score = (1.0
                      - 0.4 * conflict_penalty
                      - 0.3 * selfish_penalty
                      - 0.3 * safety_penalty)

        # Frequency improvement bonus / degradation penalty
        if freq_improved:
            base_score += 0.1
        else:
            degradation = freq_dev_after - freq_dev_before
            base_score -= min(degradation * 0.5, 0.2)

        coordination_score = max(0.0, min(1.0, base_score))

        return OversightReport(
            coordination_score=round(coordination_score, 4),
            conflicting_actions_detected=conflicts,
            selfish_actions_detected=selfish_count,
            coordination_penalties=penalties,
            global_frequency_contribution=freq_contribution,
            notes=notes,
        )

    def reset(self):
        """Reset intervention history for a new episode."""
        self.intervention_history = {
            i: 0 for i in range(self.num_agents)
        }
