"""
Tests for core simulation components:
- DC power flow solver
- Environment lifecycle (reset, step, terminate)
- Grading system (scoring, bounds, reproducibility)
- Baseline heuristic policy
"""

import copy
import unittest

import numpy as np

from src.physics import DCSolver, IslandedException
from src.environment import OpenGridEnv
from src.tasks import TASKS
from src.models import GridAction, BusAdjustment
from src.grader import RobustnessGrader, compute_analytical_ceiling
from src.baseline import heuristic_policy


def task(task_id: str):
    """Get a deep-copied task config to prevent cross-test contamination."""
    return copy.deepcopy(TASKS[task_id])


class TestDCSolver(unittest.TestCase):
    def setUp(self):
        self.num_buses = 3
        self.lines = [
            {'id': 'L01', 'from': 0, 'to': 1, 'susceptance': 100, 'connected': True},
            {'id': 'L12', 'from': 1, 'to': 2, 'susceptance': 50, 'connected': True},
            {'id': 'L02', 'from': 0, 'to': 2, 'susceptance': 100, 'connected': True}
        ]
        self.solver = DCSolver(self.num_buses)
        self.solver.update_grid(self.lines)

    def test_power_flow_balance(self):
        """Slack bus should absorb any generation/load imbalance."""
        p_inj = np.array([0.0, 50.0, -100.0])
        theta, flows, slack_inj = self.solver.solve(p_inj)

        # Check that flows are computed
        self.assertIn('L01', flows)
        self.assertIn('L02', flows)

    def test_islanding_detection(self):
        """Disconnecting lines to island bus 2 should raise IslandedException."""
        with self.assertRaises(IslandedException):
            broken_lines = [
                {'id': 'L01', 'from': 0, 'to': 1, 'susceptance': 100, 'connected': True},
                {'id': 'L12', 'from': 1, 'to': 2, 'susceptance': 50, 'connected': False},
                {'id': 'L02', 'from': 0, 'to': 2, 'susceptance': 100, 'connected': False}
            ]
            self.solver.update_grid(broken_lines)

    def test_slack_injection_returned(self):
        """solve() should return slack bus injection as third element."""
        p_inj = np.array([0.0, 50.0, -100.0])
        result = self.solver.solve(p_inj)
        self.assertEqual(len(result), 3)
        theta, flows, slack_inj = result
        # Slack should inject ~50 MW to cover the deficit
        self.assertAlmostEqual(slack_inj, 50.0, places=0)

    def test_solve_before_update_raises(self):
        """Calling solve() on a fresh solver should raise RuntimeError."""
        fresh = DCSolver(3)
        with self.assertRaises(RuntimeError):
            fresh.solve(np.array([0.0, 10.0, -10.0]))

    def test_invalid_bus_index_raises(self):
        """Lines referencing out-of-range bus IDs should raise ValueError."""
        bad_lines = [
            {'id': 'L_bad', 'from': 0, 'to': 99, 'susceptance': 50, 'connected': True},
        ]
        solver = DCSolver(3)
        with self.assertRaises(ValueError):
            solver.update_grid(bad_lines)


class TestEnvironment(unittest.TestCase):
    def test_reset_returns_observation(self):
        """reset() should return a valid GridObservation."""
        env = OpenGridEnv(task("task_easy"))
        obs = env.reset()
        self.assertEqual(obs.timestep, 0)
        self.assertGreater(len(obs.buses), 0, "Observation should have buses")
        self.assertGreater(len(obs.lines), 0, "Observation should have lines")

    def test_step_returns_tuple(self):
        """step() should return (obs, reward, done, info)."""
        env = OpenGridEnv(task("task_easy"))
        env.reset()
        obs, reward, done, info = env.step(GridAction())
        self.assertEqual(obs.timestep, 1)
        self.assertIsInstance(reward.value, float)
        self.assertIsInstance(done, bool)

    def test_reproducibility(self):
        """Running the same task twice should produce identical initial observations."""
        env1 = OpenGridEnv(task("task_easy"))
        obs1 = env1.reset()

        env2 = OpenGridEnv(task("task_easy"))
        obs2 = env2.reset()

        self.assertEqual(obs1.grid_frequency, obs2.grid_frequency)
        self.assertEqual(len(obs1.buses), len(obs2.buses))

    def test_episode_terminates(self):
        """Episode should end after max_steps."""
        config = task("task_easy")
        env = OpenGridEnv(config)
        env.reset()
        done = False
        steps = 0
        while not done and steps < 100:
            _, _, done, _ = env.step(GridAction())
            steps += 1
        self.assertTrue(done, "Episode should terminate")
        self.assertLessEqual(steps, config["max_steps"])

    def test_frequency_reasonable(self):
        """Frequency should stay in a reasonable range for do-nothing agent."""
        env = OpenGridEnv(task("task_easy"))
        obs = env.reset()
        for _ in range(10):
            obs, _, done, _ = env.step(GridAction())
            if done:
                break
            self.assertGreater(obs.grid_frequency, 40.0,
                               "Frequency below reasonable minimum")
            self.assertLess(obs.grid_frequency, 60.0,
                            "Frequency above reasonable maximum")


class TestGrader(unittest.TestCase):
    def test_grader_score_range(self):
        """Grader should return score strictly in (0, 1) — never 0.0 or 1.0."""
        grader = RobustnessGrader(task("task_easy"))
        result = grader.evaluate_policy(heuristic_policy, n_episodes=1)
        self.assertGreater(result["score"], 0.0)
        self.assertLess(result["score"], 1.0)

    def test_grader_all_tasks(self):
        """Grader should work on all registered tasks."""
        for task_id, config in TASKS.items():
            grader = RobustnessGrader(copy.deepcopy(config))
            result = grader.evaluate_policy(heuristic_policy, n_episodes=1)
            self.assertIn("score", result, f"Missing 'score' for {task_id}")
            self.assertIn("avg_raw_reward", result,
                          f"Missing 'avg_raw_reward' for {task_id}")


class TestBaseline(unittest.TestCase):
    def test_heuristic_returns_valid_action(self):
        """Heuristic policy should return a valid GridAction."""
        env = OpenGridEnv(task("task_easy"))
        obs = env.reset()
        action = heuristic_policy(obs)
        self.assertIsInstance(action, GridAction)


class TestReproducibility(unittest.TestCase):
    def test_floor_deterministic(self):
        """Two calls to _estimate_bounds should produce identical floors (seeded RNG)."""
        grader1 = RobustnessGrader(task("task_easy"))
        grader1._estimate_bounds(n_samples=3)

        grader2 = RobustnessGrader(task("task_easy"))
        grader2._estimate_bounds(n_samples=3)

        self.assertEqual(grader1.reward_floor, grader2.reward_floor,
                         "Floor should be deterministic with same seed")

    def test_ceiling_is_analytical(self):
        """Ceiling should be max_steps * 1.2, not an empirical estimate."""
        config = task("task_easy")
        grader = RobustnessGrader(config)
        bounds = grader.get_bounds()
        expected_ceiling = compute_analytical_ceiling(config["max_steps"])
        self.assertEqual(bounds["reward_ceiling"], expected_ceiling,
                         "Ceiling should match analytical formula")

    def test_heuristic_score_below_one(self):
        """With analytical ceiling, heuristic should score < 1.0 (not degenerate)."""
        grader = RobustnessGrader(task("task_easy"))
        result = grader.evaluate_policy(heuristic_policy, n_episodes=1)
        self.assertLess(result["score"], 1.0)
        self.assertGreater(result["score"], 0.0)


if __name__ == '__main__':
    unittest.main()