import numpy as np
import networkx as nx
from typing import List, Dict, Tuple

class IslandedException(Exception):
    pass

class DCSolver:
    def __init__(self, num_buses: int):
        self.num_buses = num_buses
        self.B = np.zeros((num_buses, num_buses))
        self.line_map = {}

    def update_grid(self, lines: List[Dict]):
        self.B = np.zeros((self.num_buses, self.num_buses))
        self.line_map = {}

        # Build connectivity graph for proper islanding detection
        G = nx.Graph()
        G.add_nodes_from(range(self.num_buses))

        for line in lines:
            if line['connected']:
                i, j = line['from'], line['to']
                b = line['susceptance']

                self.B[i, j] -= b
                self.B[j, i] -= b
                self.B[i, i] += b
                self.B[j, j] += b

                self.line_map[line['id']] = (i, j, b)
                G.add_edge(i, j)

        # Graph-based islanding detection (correct, not condition-number hack)
        if not nx.is_connected(G):
            raise IslandedException("Grid is islanded (disconnected graph)")

    def solve(self, p_inj: np.ndarray) -> Tuple[np.ndarray, Dict[str, float]]:
        """
        DC Power Flow: B_red * theta_red = p_red
        Bus 0 is the slack (reference angle = 0).
        Returns (theta, line_flows).
        """
        B_red = self.B[1:, 1:]
        p_red = p_inj[1:]

        try:
            theta_red = np.linalg.solve(B_red, p_red)
        except np.linalg.LinAlgError:
            raise IslandedException("Grid is islanded (singular B matrix)")

        theta = np.insert(theta_red, 0, 0.0)

        flows = {}
        for line_id, (i, j, b) in self.line_map.items():
            flows[line_id] = (theta[i] - theta[j]) * b

        # Compute slack bus injection (what the slack actually had to produce)
        slack_injection = sum(
            flows[lid] for lid, (i, j, b) in self.line_map.items() if i == 0
        ) - sum(
            flows[lid] for lid, (i, j, b) in self.line_map.items() if j == 0
        )

        return theta, flows, slack_injection