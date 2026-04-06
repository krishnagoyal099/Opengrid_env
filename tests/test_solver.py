import unittest
import numpy as np
from src.physics import DCSolver, IslandedException
from src.environment import OpenGridEnv
from src.tasks import TASKS
from src.models import GridAction, BusAdjustment
from src.grader import RobustnessGrader
from src.baseline import heuristic_policy


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


class TestEnvironment(unittest.TestCase):
    def test_reset_returns_observation(self):
        """reset() should return a valid GridObservation."""
        env = OpenGridEnv(TASKS["task_easy"])
        obs = env.reset()
        self.assertEqual(obs.timestep, 0)
        self.assertGreater(len(obs.buses), 0)
        self.assertGreater(len(obs.lines), 0)

    def test_step_returns_tuple(self):
        """step() should return (obs, reward, done, info)."""
        env = OpenGridEnv(TASKS["task_easy"])
        env.reset()
        obs, reward, done, info = env.step(GridAction())
        self.assertEqual(obs.timestep, 1)
        self.assertIsInstance(reward.value, float)
        self.assertIsInstance(done, bool)

    def test_reproducibility(self):
        """Running the same task twice should produce identical initial observations."""
        env1 = OpenGridEnv(TASKS["task_easy"])
        obs1 = env1.reset()

        env2 = OpenGridEnv(TASKS["task_easy"])
        obs2 = env2.reset()

        self.assertEqual(obs1.grid_frequency, obs2.grid_frequency)
        self.assertEqual(len(obs1.buses), len(obs2.buses))

    def test_episode_terminates(self):
        """Episode should end after max_steps."""
        env = OpenGridEnv(TASKS["task_easy"])
        env.reset()
        done = False
        steps = 0
        while not done and steps < 100:
            _, _, done, _ = env.step(GridAction())
            steps += 1
        self.assertTrue(done)
        self.assertLessEqual(steps, TASKS["task_easy"]["max_steps"])

    def test_frequency_reasonable(self):
        """Frequency should stay in a reasonable range for do-nothing agent."""
        env = OpenGridEnv(TASKS["task_easy"])
        obs = env.reset()
        for _ in range(10):
            obs, _, done, _ = env.step(GridAction())
            if done:
                break
            self.assertGreater(obs.grid_frequency, 40.0)
            self.assertLess(obs.grid_frequency, 60.0)


class TestGrader(unittest.TestCase):
    def test_grader_score_range(self):
        """Grader should return score between 0.0 and 1.0."""
        grader = RobustnessGrader(TASKS["task_easy"])
        result = grader.evaluate_policy(heuristic_policy, n_episodes=1)
        self.assertGreaterEqual(result["score"], 0.0)
        self.assertLessEqual(result["score"], 1.0)

    def test_grader_all_tasks(self):
        """Grader should work on all 3 difficulty levels."""
        for task_id, config in TASKS.items():
            grader = RobustnessGrader(config)
            result = grader.evaluate_policy(heuristic_policy, n_episodes=1)
            self.assertIn("score", result)
            self.assertIn("avg_raw_reward", result)


class TestBaseline(unittest.TestCase):
    def test_heuristic_returns_valid_action(self):
        """Heuristic policy should return a valid GridAction."""
        env = OpenGridEnv(TASKS["task_easy"])
        obs = env.reset()
        action = heuristic_policy(obs)
        self.assertIsInstance(action, GridAction)


if __name__ == '__main__':
    unittest.main()