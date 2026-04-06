"""
DC Power Flow Solver
====================
Implements the standard DC approximation: B * θ = P

Assumptions:
- Flat voltage profile (|V| ≈ 1.0 p.u.)
- Small angle differences (sin(θ) ≈ θ)
- Negligible resistance (R ≈ 0, only susceptance used)

Flow sign convention:
    flow = b * (θ_from - θ_to)
    Positive flow = power flowing from 'from' bus to 'to' bus.
"""

import logging
import warnings
import numpy as np
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)


class IslandedException(Exception):
    pass


class DCSolver:
    """DC power flow solver with graph-based islanding detection.

    The slack bus absorbs any power imbalance and has its voltage angle
    fixed to 0 (reference). By default this is bus 0, but can be
    configured via the slack_bus parameter.
    """

    def __init__(self, num_buses: int, slack_bus: int = 0):
        self.num_buses = num_buses
        self.slack_bus = slack_bus
        self.B = np.zeros((num_buses, num_buses))
        self.line_map = {}
        self._grid_loaded = False

    def update_grid(self, lines: List[Dict]):
        """Rebuild the B matrix and check connectivity.

        Skips zero-susceptance lines (no electrical contribution).
        Validates bus indices to prevent silent corruption.
        """
        self.B = np.zeros((self.num_buses, self.num_buses))
        self.line_map = {}

        # Union-Find for O(n) connectivity check (replaces NetworkX)
        parent = list(range(self.num_buses))
        rank = [0] * self.num_buses

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]  # path compression
                x = parent[x]
            return x

        def union(x, y):
            rx, ry = find(x), find(y)
            if rx == ry:
                return
            if rank[rx] < rank[ry]:
                rx, ry = ry, rx
            parent[ry] = rx
            if rank[rx] == rank[ry]:
                rank[rx] += 1

        for line in lines:
            if line['connected']:
                i, j = line['from'], line['to']
                b = line['susceptance']

                # Validate bus indices
                if not (0 <= i < self.num_buses and 0 <= j < self.num_buses):
                    raise ValueError(
                        f"Line {line['id']}: bus indices ({i}, {j}) out of range "
                        f"for {self.num_buses} buses"
                    )

                # Skip zero-susceptance lines (no electrical contribution)
                if abs(b) < 1e-12:
                    continue

                self.B[i, j] -= b
                self.B[j, i] -= b
                self.B[i, i] += b
                self.B[j, j] += b

                self.line_map[line['id']] = (i, j, b)
                union(i, j)

        # Connectivity check via union-find
        root = find(0)
        if not all(find(i) == root for i in range(self.num_buses)):
            # Build component info for diagnostics
            components = {}
            for i in range(self.num_buses):
                r = find(i)
                components.setdefault(r, []).append(i)
            comp_sizes = [len(c) for c in components.values()]
            raise IslandedException(
                f"Grid is islanded: {len(components)} components, "
                f"sizes={comp_sizes}"
            )

        self._grid_loaded = True

    def solve(self, p_inj: np.ndarray) -> Tuple[np.ndarray, Dict[str, float], float]:
        """Solve DC power flow: B_red * θ_red = P_red.

        Args:
            p_inj: Real power injection at each bus (MW). Shape must be (num_buses,).

        Returns:
            (theta, line_flows, slack_injection) tuple.
            theta: voltage angles (radians). Slack bus angle = 0.
            line_flows: {line_id: flow_MW}. Positive = from→to direction.
            slack_injection: MW absorbed/injected by the slack bus.
        """
        if not self._grid_loaded:
            raise RuntimeError("DCSolver.solve() called before update_grid()")

        # Validate input
        p_inj = np.asarray(p_inj).ravel()
        if len(p_inj) != self.num_buses:
            raise ValueError(
                f"p_inj length {len(p_inj)} != num_buses {self.num_buses}"
            )

        # Remove slack bus row/column
        mask = np.arange(self.num_buses) != self.slack_bus
        B_red = self.B[np.ix_(mask, mask)]
        p_red = p_inj[mask]

        try:
            theta_red = np.linalg.solve(B_red, p_red)
        except np.linalg.LinAlgError:
            raise IslandedException("Grid is islanded (singular B matrix)")

        # Check conditioning
        cond = np.linalg.cond(B_red)
        if cond > 1e12:
            warnings.warn(
                f"DCSolver: B_red is ill-conditioned (cond={cond:.2e}). "
                f"Results may be numerically unreliable.",
                RuntimeWarning,
                stacklevel=2,
            )

        # Insert slack bus angle (= 0)
        theta = np.zeros(self.num_buses)
        theta[mask] = theta_red

        # Compute line flows
        flows = {}
        for line_id, (i, j, b) in self.line_map.items():
            flows[line_id] = (theta[i] - theta[j]) * b

        # Slack injection from power balance (more robust than summing flows)
        slack_injection = -float(p_inj[mask].sum())

        return theta, flows, slack_injection

    def __repr__(self):
        return (
            f"DCSolver(num_buses={self.num_buses}, slack={self.slack_bus}, "
            f"lines={len(self.line_map)}, loaded={self._grid_loaded})"
        )