import logging
import math
import numpy as np
from typing import Dict, Callable, List
from .environment import OpenGridEnv
from .models import GridAction, BusAdjustment, TopologyAction

logger = logging.getLogger(__name__)


def _random_thrash_policy(obs, rng: np.random.Generator) -> GridAction:
    """Deliberately bad policy: random topology switching. Used as reward floor.

    Alternates between opening and closing lines to maximize instability
    across all steps (not just step 1). Uses an explicit RNG instance
    (not global np.random) so that floor estimation is reproducible.
    """
    top_actions = []
    for line in obs.lines:
        if rng.random() > 0.7:
            action = "open" if line.connected else "close"
            top_actions.append(TopologyAction(line_id=line.id, action=action))
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
    # Scale into available headroom so top performers still differentiate
    n1_bonus = float(n1_survival_rate) * 0.1
    available = _SCORE_MAX - normalized
    if available > 0:
        n1_bonus = min(n1_bonus, available * 0.5)
    else:
        n1_bonus = 0.0
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

        n_samples=10 to reduce variance in the floor estimate.
        The floor uses mean - std to be conservatively low.
        Each episode gets its own thrash RNG derived from a master seed
        so that changing n_samples doesn't alter existing episodes.
        """
        master_rng = np.random.default_rng(seed=12345)

        floors = []
        base_seed = self.config.get('seed', 42)

        for i in range(n_samples):
            # Per-episode thrash RNG — decoupled from other episodes
            thrash_rng = np.random.default_rng(seed=int(master_rng.integers(0, 2**31)))

            # Vary environment seed so floor reflects environment stochasticity
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
        logger.debug("Floor estimate: mean=%.2f, std=%.2f, floor=%.2f",
                     np.mean(floors), np.std(floors), self.reward_floor)

        # Ceiling: analytical upper bound (not heuristic)
        max_steps = self.config.get('max_steps', 50)
        analytical_ceiling = compute_analytical_ceiling(max_steps)
        self.reward_ceiling = analytical_ceiling

        # Ensure minimum spread — expand floor downward, not ceiling upward
        if self.reward_ceiling - self.reward_floor < 10.0:
            self.reward_floor = self.reward_ceiling - max(10.0, analytical_ceiling * 0.2)
            logger.debug("Spread too small, adjusted floor to %.2f", self.reward_floor)

    def get_bounds(self) -> Dict[str, float]:
        """Return the reward floor and ceiling, computing if needed."""
        if self.reward_floor is None:
            self._estimate_bounds()
        return {"reward_floor": self.reward_floor, "reward_ceiling": self.reward_ceiling}

    def evaluate_policy(self, policy_fn: Callable, n_episodes: int = 10) -> Dict:
        """Run a policy for n_episodes and return normalized score.

        Each episode uses a different environment seed (offset by 1000 from
        floor estimation seeds) to measure policy robustness across diverse
        wind/load trajectories.
        """
        if self.reward_floor is None:
            self._estimate_bounds()

        base_seed = self.config.get('seed', 42)
        rewards = []
        n1_survivals = 0

        for ep in range(n_episodes):
            # Offset by 1000 to avoid overlap with floor estimation seeds
            config_with_seed = {**self.config, 'seed': base_seed + ep + 1000}
            env = OpenGridEnv(config_with_seed)
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
        logger.debug("Policy eval: avg=%.2f, n1_rate=%.2f, episodes=%d",
                     avg_reward, n1_rate, n_episodes)

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