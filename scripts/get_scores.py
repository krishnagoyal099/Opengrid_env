"""Evaluate heuristic baseline on all tasks and print scores."""

import copy
import json
import sys

from src.tasks import TASKS
from src.grader import RobustnessGrader
from src.baseline import heuristic_policy


def main(n_episodes: int = 10):
    all_results = {}

    for tid, cfg in TASKS.items():
        try:
            grader = RobustnessGrader(copy.deepcopy(cfg))
            result = grader.evaluate_policy(
                heuristic_policy, n_episodes=n_episodes
            )
            all_results[tid] = result

            print(f"{tid}:")
            for k, v in result.items():
                print(f"  {k}: {v}")
            print()

        except Exception as e:
            all_results[tid] = {"error": str(e)}
            print(f"{tid}: FAILED — {e}\n")

    return all_results


if __name__ == "__main__":
    episodes = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    main(n_episodes=episodes)
