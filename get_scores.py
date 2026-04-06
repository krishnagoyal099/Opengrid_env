from src.tasks import TASKS
from src.grader import RobustnessGrader
from src.baseline import heuristic_policy

for tid, cfg in TASKS.items():
    grader = RobustnessGrader(cfg)
    result = grader.evaluate_policy(heuristic_policy, n_episodes=3)
    print(f"{tid}:")
    for k, v in result.items():
        print(f"  {k}: {v}")
    print()
