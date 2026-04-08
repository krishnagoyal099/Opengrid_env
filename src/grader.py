import math
import numpy as np
from typing import Dict, Callable, List
from .environment import OpenGridEnv
from .models import GridAction, BusAdjustment, TopologyAction


def _random_thrash_policy(obs, rng: np.random.Generator) -> GridAction:
    """Deliberately bad policy: random topology switching. Used as reward floor.

    Uses an explicit RNG instance (not global np.random) so that floor
    estimation is deterministic and reproducible across process lifetimes.
    """
    top_actions = []
    for line in obs.lines:
        if line.connected and rng.random() > 0.7:
            top_actions.append(TopologyAction(line_id=line.id, action="open"))
    return GridAction(topology_actions=top_actions)


def compute_analytical_ceiling(max_steps: int) -> float:
    """Compute the theoretical maximum reward for an episode.

    Perfect agent: survives every step (+1.0 survival) and achieves
    tight frequency control bonus (+0.2) every step, with zero overload
    and zero action cost.

    ceiling = max_steps * (1.0 + 0.2) = max_steps * 1.2

    NOTE: The +0.2 frequency bonus requires freq_dev < 0.1 Hz, which needs
    |P_slack| < 0.04 * S_total (from droop model). On high-renewable tasks
    (task_hard) where slack routinely absorbs >50 MW of imbalance, this band
    may be structurally inaccessible. The effective ceiling on such tasks is
    closer to max_steps * 1.0 = 50.0. Scores remain comparable across agents
    on the same task — the ceiling just compresses the achievable range.
    """
    return max_steps * 1.2


# Validator requires scores strictly in the open interval (0, 1).
# Using wide epsilon so that even aggressive rounding (e.g. round(x, 1))
# can never produce exactly 0.0 or 1.0.
_SCORE_EPSILON = 0.02
_SCORE_MIN = _SCORE_EPSILON        # 0.02
_SCORE_MAX = 1.0 - _SCORE_EPSILON  # 0.98


def _safe_float(x: float) -> float:
    """Convert to plain Python float; replace NaN/Inf with midpoint."""
    v = float(x)
    if not math.isfinite(v):
        return 0.5  # safe fallback inside (0, 1)
    return v


def _clamp_score(score: float) -> float:
    """Clamp a score to the open interval (0, 1) using Python-native min/max.

    This avoids any numpy-scalar serialisation quirks and guarantees a plain
    Python float that JSON-encodes to a normal number.
    """
    score = _safe_float(score)
    score = max(_SCORE_MIN, min(_SCORE_MAX, score))
    # Truncate (not round) to 4 decimal places to avoid
    # round(0.98500…, 4) == 0.985 becoming 0.99 after further rounding.
    score = math.floor(score * 10000) / 10000
    # Final safety: ensure truncation didn't land on a boundary
    score = max(_SCORE_MIN, min(_SCORE_MAX, score))
    return score


def normalize_score(cumulative_reward: float, reward_floor: float, reward_ceiling: float,
                    n1_survival_rate: float = 1.0) -> float:
    """
    Shared normalization: maps raw cumulative reward to the open interval (0, 1).
    Used by both /grader endpoint and RobustnessGrader for consistency.

    - reward_floor: empirical worst-case (random thrashing policy, seeded RNG)
    - reward_ceiling: analytical upper bound (perfect survival + perfect frequency bonus)
    - n1_survival_rate: fraction of episodes without blackout (adds up to 10% bonus)

    Scores are clamped to [0.02, 0.98] so they are never exactly 0.0 or 1.0,
    and cannot round to those values, satisfying the OpenEnv Phase-2 validator.
    """
    raw_range = _safe_float(reward_ceiling) - _safe_float(reward_floor)
    if raw_range < 1.0:
        raw_range = 1.0  # Prevent division by near-zero

    cumulative_reward = _safe_float(cumulative_reward)
    normalized = (cumulative_reward - _safe_float(reward_floor)) / raw_range

    # N-1 bonus: up to 10% boost for surviving without blackout
    n1_bonus = float(n1_survival_rate) * 0.1
    score = normalized + n1_bonus

    return _clamp_score(score)


class RobustnessGrader:
    """
    Evaluates a policy's performance on an OpenGrid task.

    Scoring:
    - Floor: empirical estimate from adversarial random topology thrashing
      (seeded RNG for reproducibility, n_samples=10 for stability)
    - Ceiling: analytical upper bound = max_steps * 1.2
      (perfect survival + perfect frequency bonus every step)
    - Normalizes cumulative reward to 0.0–1.0
    - Adds N-1 survival bonus (max 10%)

    The heuristic baseline scores ~0.75–0.90, leaving headroom for
    agents that employ active topology management and predictive scheduling.
    """

    def __init__(self, config: Dict):
        self.config = config
        self.reward_floor = None
        self.reward_ceiling = None

    def _estimate_bounds(self, n_samples: int = 10):
        """Estimate reward bounds.

        Floor: adversarial random thrashing policy (empirical, seeded).
        Ceiling: analytical upper bound (deterministic).

        n_samples=10 (up from 3) to reduce variance in the floor estimate.
        The floor uses mean - std to be conservatively low.

        The thrash policy RNG is seeded per-call so that bounds are
        identical across different process lifetimes.
        """
        from .baseline import heuristic_policy  # Lazy import to avoid circular

        # Seeded RNG for the thrash policy — reproducible floor estimation
        thrash_rng = np.random.default_rng(seed=12345)

        floors = []
        base_seed = self.config.get('seed', 42)

        for i in range(n_samples):
            # Floor: adversarial random topology thrashing (worst reasonable behavior)
            # Vary the environment seed across episodes so the floor reflects both
            # policy stochasticity AND environment stochasticity (different wind/load
            # trajectories), not just 10 thrash patterns on one fixed trajectory.
            config_with_seed = {**self.config, 'seed': base_seed + i}
            env = OpenGridEnv(config_with_seed)
            obs = env.reset()
            done = False
            ep_reward = 0
            while not done:
                action = _random_thrash_policy(obs, rng=thrash_rng)
                obs, reward, done, info = env.step(action)
                ep_reward += reward.value
            floors.append(ep_reward)

        self.reward_floor = float(np.mean(floors) - np.std(floors))

        # Ceiling: analytical upper bound (not heuristic)
        max_steps = self.config.get('max_steps', 50)
        self.reward_ceiling = compute_analytical_ceiling(max_steps)

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