"""
Tests for multi-agent POMDP features:
- Zone assignment and partitioning
- Partial observability (ZoneObservation)
- Safety layer (action validation and correction)
- Oversight agent (coordination monitoring)
- Multi-agent step (combined pipeline)
"""

import copy
import unittest

import networkx as nx
import numpy as np

from src.environment import OpenGridEnv
from src.tasks import TASKS
from src.models import GridAction, BusAdjustment, TopologyAction, ZoneObservation
from src.safety import SafetyLayer
from src.oversight import OversightAgent


def task(task_id: str):
    """Get a deep-copied task config to prevent cross-test contamination."""
    return copy.deepcopy(TASKS[task_id])


class TestZoneAssignment(unittest.TestCase):
    """Tests for multi-agent zone partitioning."""

    def test_all_buses_assigned(self):
        """Every bus should be assigned to exactly one zone."""
        for task_id, config in TASKS.items():
            zone_map = config['zone_assignments']
            for i in range(config['num_buses']):
                self.assertIn(i, zone_map, f"Bus {i} not assigned in {task_id}")

    def test_zone_count_matches(self):
        """Number of zones should match num_agents."""
        for task_id, config in TASKS.items():
            agents = set(config['zone_assignments'].values())
            self.assertEqual(len(agents), config['num_agents'],
                             f"Zone count mismatch in {task_id}")

    def test_no_empty_zones(self):
        """Each zone should have at least 1 bus."""
        for task_id, config in TASKS.items():
            for agent_id in range(config['num_agents']):
                bus_ids = config['zone_bus_ids'][agent_id]
                self.assertGreater(len(bus_ids), 0,
                                   f"Empty zone {agent_id} in {task_id}")

    def test_lines_classified(self):
        """All lines should be classified as internal or boundary."""
        for task_id, config in TASKS.items():
            all_internal = set()
            all_boundary = set()
            for agent_id in range(config['num_agents']):
                all_internal.update(config['internal_lines'].get(agent_id, []))
                all_boundary.update(config['boundary_lines'].get(agent_id, []))

            all_line_ids = {l['id'] for l in config['lines']}
            classified = all_internal | all_boundary
            self.assertEqual(all_line_ids, classified,
                             f"Unclassified lines in {task_id}")


class TestPartialObservability(unittest.TestCase):
    """Tests for POMDP zone observations."""

    def test_partial_obs_returns_zone_obs(self):
        """reset_multi should return ZoneObservation for each agent."""
        config = task("task_easy")
        env = OpenGridEnv(config)
        zone_obs = env.reset_multi()

        self.assertEqual(len(zone_obs), config["num_agents"],
                         "Should have one observation per agent")
        for agent_id, obs in zone_obs.items():
            self.assertIsInstance(obs, ZoneObservation)
            self.assertEqual(obs.agent_id, agent_id)

    def test_partial_obs_only_shows_local_buses(self):
        """Each agent should only see buses in their zone."""
        config = task("task_medium")
        env = OpenGridEnv(config)
        zone_obs = env.reset_multi()

        for agent_id, obs in zone_obs.items():
            expected_bus_ids = set(config['zone_bus_ids'][agent_id])
            actual_bus_ids = {b.id for b in obs.local_buses}
            self.assertEqual(actual_bus_ids, expected_bus_ids,
                             f"Agent {agent_id} sees wrong buses")

    def test_frequency_has_noise(self):
        """POMDP observations should have noisy frequency readings."""
        config = task("task_easy")
        env = OpenGridEnv(config)
        env.reset_multi()

        # Compare zone obs against full obs from the same reset
        full_obs = env.state()
        differences = []
        for agent_id in range(config['num_agents']):
            z_obs = env._get_zone_obs(agent_id)
            diff = abs(z_obs.grid_frequency - full_obs.grid_frequency)
            differences.append(diff)

        # At least one agent should see noisy frequency
        self.assertTrue(any(d > 0.001 for d in differences),
                        "No frequency noise detected in POMDP observations")


class TestSafetyLayer(unittest.TestCase):
    """Tests for the safety constraint filter."""

    def setUp(self):
        self.config = task("task_medium")
        self.safety = SafetyLayer(self.config)
        self.env = OpenGridEnv(self.config)
        self.env.reset()

    def test_zone_boundary_enforcement(self):
        """Agent should not be able to adjust buses in another zone."""
        agent_0_buses = set(self.config['zone_bus_ids'][0])
        other_bus = None
        for bus_cfg in self.config['buses']:
            if bus_cfg['id'] not in agent_0_buses:
                other_bus = bus_cfg['id']
                break

        if other_bus is None:
            self.skipTest("All buses in agent 0's zone (trivial grid)")

        action = GridAction(bus_adjustments=[
            BusAdjustment(bus_id=other_bus, delta=10.0)
        ])

        corrected, report = self.safety.validate_and_correct(
            agent_id=0,
            proposed_action=action,
            current_line_state=self.env.line_state,
            current_bus_state=self.env.bus_state,
            cooldowns=self.env.cooldowns,
        )

        self.assertTrue(report.was_corrected, "Should have corrected cross-zone action")
        self.assertEqual(len(corrected.bus_adjustments), 0,
                         "Cross-zone adjustment should be removed")

    def test_safe_action_passes_through(self):
        """A valid action within the agent's zone should not be corrected."""
        agent_0_buses = self.config['zone_bus_ids'][0]
        controllable = None
        for bus_cfg in self.config['buses']:
            if bus_cfg['id'] in agent_0_buses and bus_cfg['type'] in ['generator', 'battery', 'slack']:
                controllable = bus_cfg['id']
                break

        if controllable is None:
            self.skipTest("No controllable bus in agent 0's zone")

        action = GridAction(bus_adjustments=[
            BusAdjustment(bus_id=controllable, delta=5.0)
        ])

        corrected, report = self.safety.validate_and_correct(
            agent_id=0,
            proposed_action=action,
            current_line_state=self.env.line_state,
            current_bus_state=self.env.bus_state,
            cooldowns=self.env.cooldowns,
        )

        # Should pass through (may have minor clamping)
        self.assertEqual(len(corrected.bus_adjustments), 1,
                         "Valid action should produce one adjustment")

    def test_islanding_blocked(self):
        """Opening a bridge line should be blocked by safety layer."""
        G = nx.Graph()
        for line in self.config['lines']:
            G.add_edge(line['from'], line['to'])
        bridges = list(nx.bridges(G))
        if not bridges:
            self.skipTest("No bridges in grid topology")

        bridge = bridges[0]
        line_id = next(
            l['id'] for l in self.config['lines']
            if (l['from'], l['to']) == bridge or (l['to'], l['from']) == bridge
        )

        action = GridAction(topology_actions=[
            TopologyAction(line_id=line_id, action="open")
        ])

        corrected, report = self.safety.validate_and_correct(
            agent_id=0,
            proposed_action=action,
            current_line_state=self.env.line_state,
            current_bus_state=self.env.bus_state,
            cooldowns=self.env.cooldowns,
        )

        self.assertTrue(report.was_corrected, "Bridge opening should be blocked")
        self.assertEqual(len(corrected.topology_actions), 0,
                         "Bridge opening should be removed")

    def test_duplicate_battery_adjustments_aggregated(self):
        """Multiple adjustments to the same battery should be aggregated."""
        battery = next(
            (b for b in self.config['buses'] if b['type'] == 'battery'), None
        )
        if battery is None:
            self.skipTest("No battery in task")

        bus_id = battery['id']
        agent_id = self.config['zone_assignments'].get(bus_id, 0)

        # Set SOC to a known value
        for b in self.env.bus_state:
            if b['id'] == bus_id:
                b['soc'] = 10.0

        action = GridAction(bus_adjustments=[
            BusAdjustment(bus_id=bus_id, delta=8.0),
            BusAdjustment(bus_id=bus_id, delta=8.0),
        ])

        corrected, report = self.safety.validate_and_correct(
            agent_id=agent_id,
            proposed_action=action,
            current_line_state=self.env.line_state,
            current_bus_state=self.env.bus_state,
            cooldowns=self.env.cooldowns,
        )

        total_delta = sum(a.delta for a in corrected.bus_adjustments)
        self.assertLessEqual(total_delta, 10.0,
                             "Combined discharge should not exceed SOC")


class TestOversightAgent(unittest.TestCase):
    """Tests for the coordination oversight agent."""

    def test_no_conflict_scores_high(self):
        """Cooperative actions should score high coordination."""
        config = task("task_easy")
        oversight = OversightAgent(config)

        # Both agents inject (cooperative)
        agent_actions = {
            0: GridAction(bus_adjustments=[BusAdjustment(bus_id=0, delta=5.0)]),
            1: GridAction(bus_adjustments=[BusAdjustment(bus_id=1, delta=3.0)]),
        }

        report = oversight.evaluate(
            agent_actions=agent_actions,
            safety_reports={},
            pre_frequency=49.8,
            post_frequency=49.9,
            pre_bus_state=[],
            post_bus_state=[],
        )

        self.assertGreater(report.coordination_score, 0.5,
                           "Cooperative actions should score > 0.5")

    def test_reset_clears_history(self):
        """Resetting oversight should clear intervention history."""
        config = task("task_easy")
        oversight = OversightAgent(config)
        oversight.intervention_history[0] = 5
        oversight.reset()
        self.assertEqual(oversight.intervention_history[0], 0)


class TestMultiAgentStep(unittest.TestCase):
    """Integration tests for the full multi-agent pipeline."""

    def test_multi_agent_step_returns_result(self):
        """step_multi should return a complete MultiAgentStepResult."""
        config = task("task_easy")
        env = OpenGridEnv(config)
        env.reset_multi()

        # No-op actions for all agents
        actions = {i: GridAction() for i in range(config['num_agents'])}
        result = env.step_multi(actions)

        self.assertEqual(len(result.observations), config['num_agents'])
        self.assertEqual(len(result.rewards), config['num_agents'])
        self.assertIsInstance(result.team_reward, float)
        self.assertIsInstance(result.done, bool)
        self.assertEqual(len(result.safety_reports), config['num_agents'])

    def test_safety_reports_match_agent_ids(self):
        """Safety reports should contain all expected agent IDs."""
        config = task("task_easy")
        env = OpenGridEnv(config)
        env.reset_multi()

        result = env.step_multi({
            i: GridAction() for i in range(config['num_agents'])
        })

        report_ids = set(result.safety_reports.keys())
        expected_ids = set(range(config['num_agents']))
        self.assertEqual(report_ids, expected_ids,
                         "Safety report agent IDs should match expected agents")

    def test_multi_agent_episode_completes(self):
        """A full multi-agent episode should complete without errors."""
        config = task("task_easy")
        env = OpenGridEnv(config)
        env.reset_multi()

        done = False
        steps = 0
        while not done and steps < config['max_steps'] + 5:
            actions = {i: GridAction() for i in range(config['num_agents'])}
            result = env.step_multi(actions)
            done = result.done
            steps += 1

        self.assertTrue(done, "Episode should terminate")
        self.assertLessEqual(steps, config['max_steps'] + 1)

    def test_backward_compatibility(self):
        """Single-agent reset/step should still work after multi-agent changes."""
        for task_id in TASKS:
            config = task(task_id)
            env = OpenGridEnv(config)
            obs = env.reset()
            self.assertGreater(len(obs.buses), 0,
                               f"No buses in {task_id}")

            obs, reward, done, info = env.step(GridAction())
            self.assertEqual(obs.timestep, 1)
            self.assertIsInstance(reward.value, float)


if __name__ == '__main__':
    unittest.main()
