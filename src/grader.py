import numpy as np
from typing import Dict, Callable, List
from .environment import OpenGridEnv
from .models import GridAction, BusAdjustment, TopologyAction


def _random_thrash_policy(obs) -> GridAction:
    """Deliberately bad policy: random topology switching. Used as reward floor."""
    top_actions = []
    for line in obs.lines:
        if line.connected and np.random.random() > 0.7:
            top_actions.append(TopologyAction(line_id=line.id, action="open"))
    return GridAction(topology_actions=top_actions)


def normalize_score(cumulative_reward: float, reward_floor: float, reward_ceiling: float,
                    n1_survival_rate: float = 1.0) -> float:
    """
    Shared normalization: maps raw cumulative reward to 0.0–1.0.
    Used by both /grader endpoint and RobustnessGrader for consistency.
    
    - reward_floor: empirical worst-case (random thrashing policy)
    - reward_ceiling: empirical best-case (heuristic policy)
    - n1_survival_rate: fraction of episodes without blackout (adds up to 10% bonus)
    """
    raw_range = reward_ceiling - reward_floor
    if raw_range < 1.0:
        raw_range = 1.0  # Prevent division by near-zero

    normalized = (cumulative_reward - reward_floor) / raw_range
    score = float(np.clip(normalized, 0.0, 1.0))

    # N-1 bonus: up to 10% boost for surviving without blackout
    n1_bonus = n1_survival_rate * 0.1
    score = min(1.0, score + n1_bonus)

    return round(score, 4)


class RobustnessGrader:
    """
    Evaluates a policy's performance on an OpenGrid task.
    
    Scoring:
    - Estimates reward bounds empirically:
      - Floor: random topology thrashing policy (adversarial worst-case)
      - Ceiling: do-nothing + heuristic policies (reasonable upper bound)
    - Normalizes cumulative reward to 0.0–1.0
    - Adds N-1 survival bonus (max 10%)
    """

    def __init__(self, config: Dict):
        self.config = config
        self.reward_floor = None
        self.reward_ceiling = None

    def _estimate_bounds(self, n_samples: int = 3):
        """Estimate reward bounds from adversarial (floor) and heuristic (ceiling) policies."""
        from .baseline import heuristic_policy  # Lazy import to avoid circular

        floors = []
        ceilings = []

        for _ in range(n_samples):
            # Floor: adversarial random topology thrashing (worst reasonable behavior)
            env = OpenGridEnv(self.config)
            obs = env.reset()
            done = False
            ep_reward = 0
            while not done:
                action = _random_thrash_policy(obs)
                obs, reward, done, info = env.step(action)
                ep_reward += reward.value
            floors.append(ep_reward)

            # Ceiling: heuristic policy (best available non-oracle behavior)
            env2 = OpenGridEnv(self.config)
            obs2 = env2.reset()
            done2 = False
            ep_reward2 = 0
            while not done2:
                action2 = heuristic_policy(obs2)
                obs2, reward2, done2, info2 = env2.step(action2)
                ep_reward2 += reward2.value
            ceilings.append(ep_reward2)

        self.reward_floor = float(np.mean(floors) - np.std(floors))
        self.reward_ceiling = float(np.mean(ceilings) + np.std(ceilings))

        # Ensure minimum spread so normalization is meaningful
        if self.reward_ceiling - self.reward_floor < 10.0:
            self.reward_ceiling = self.reward_floor + 50.0

    def get_bounds(self) -> Dict[str, float]:
        """Return the reward floor and ceiling, computing if needed."""
        if self.reward_floor is None:
            self._estimate_bounds()
        return {"reward_floor": self.reward_floor, "reward_ceiling": self.reward_ceiling}

    def evaluate_policy(self, policy_fn: Callable, n_episodes: int = 3) -> Dict:
        """Run a policy for n_episodes and return normalized score."""
        if self.reward_floor is None:
            self._estimate_bounds()

        rewards = []
        n1_survivals = 0

        for ep in range(n_episodes):
            env = OpenGridEnv(self.config)
            obs = env.reset()
            done = False
            ep_reward = 0

            while not done:
                action = policy_fn(obs)
                obs, reward, done, info = env.step(action)
                ep_reward += reward.value

            rewards.append(ep_reward)
            if not info.is_blackout:
                n1_survivals += 1

        avg_reward = float(np.mean(rewards))
        n1_rate = n1_survivals / n_episodes

        final_score = normalize_score(
            cumulative_reward=avg_reward,
            reward_floor=self.reward_floor,
            reward_ceiling=self.reward_ceiling,
            n1_survival_rate=n1_rate
        )

        return {
            "avg_raw_reward": round(avg_reward, 4),
            "n1_survival_rate": round(n1_rate, 4),
            "reward_floor": round(self.reward_floor, 4),
            "reward_ceiling": round(self.reward_ceiling, 4),
            "score": final_score
        }