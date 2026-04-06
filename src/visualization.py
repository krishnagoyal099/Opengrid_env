"""
Grid Visualization — Dashboard Generator
==========================================
Generates a base64-encoded PNG dashboard with two panels:
1. Grid topology with bus-type coloring and line-loading heat map
2. Frequency stability trace over time

Supports both GridObservation (single-agent) and ZoneObservation (multi-agent).
"""

import io
import base64
import logging
from typing import List, Optional, Sequence, Dict, Tuple

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for server use
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import networkx as nx

from .models import GridObservation

logger = logging.getLogger(__name__)


def _parse_line_endpoints(line_id: str) -> Optional[Tuple[int, int]]:
    """Parse line ID format 'L_<from>_<to>' into endpoint bus IDs.

    Returns (from, to) on success, None on parse failure.
    Requires exactly the format L_<int>_<int>.
    """
    try:
        parts = line_id.split('_')
        if len(parts) == 3 and parts[0] == "L":
            return int(parts[1]), int(parts[2])
    except (ValueError, IndexError):
        pass
    return None


def generate_dashboard(
    history: Sequence,
    current_obs,
    config: Optional[Dict] = None,
) -> str:
    """Generate a base64-encoded PNG dashboard image.

    Args:
        history: Sequence of observation objects for frequency trace.
        current_obs: Current GridObservation or ZoneObservation for topology.
        config: Optional grid config dict. When provided, line endpoints
                are read from config (robust) instead of parsed from IDs.

    Returns:
        Base64-encoded PNG image string (without data URI prefix).
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    try:
        # Support both GridObservation and ZoneObservation
        buses = getattr(current_obs, "buses",
                        getattr(current_obs, "local_buses", []))
        lines = getattr(current_obs, "lines", None)
        if lines is None:
            internal = getattr(current_obs, "internal_lines", [])
            boundary = getattr(current_obs, "boundary_lines", [])
            lines = list(internal) + list(boundary)

        # Build line endpoint lookup from config if available
        line_endpoints: Dict[str, Tuple[int, int]] = {}
        if config:
            for l_cfg in config.get("lines", []):
                line_endpoints[l_cfg["id"]] = (l_cfg["from"], l_cfg["to"])

        # --- Plot 1: Grid Topology ---
        G = nx.Graph()

        color_map = {}
        for bus in buses:
            G.add_node(bus.id)
            if bus.type in ['generator', 'slack']:
                color_map[bus.id] = '#2ecc71'  # green
            elif bus.type == 'load':
                color_map[bus.id] = '#e74c3c'  # red
            elif bus.type == 'battery':
                color_map[bus.id] = '#3498db'  # blue
            else:
                color_map[bus.id] = '#f1c40f'  # yellow (renewables)

        # Build graph with line data as edge attributes
        for line in lines:
            # Get endpoints from config (preferred) or parse from ID
            if line.id in line_endpoints:
                u, v = line_endpoints[line.id]
            else:
                parsed = _parse_line_endpoints(line.id)
                if parsed is None:
                    continue
                u, v = parsed

            G.add_edge(u, v, line_id=line.id, rho=line.rho,
                       connected=line.connected)

        # Build edge colors in G.edges() order (correct alignment)
        edge_colors = []
        edge_styles = []
        for u, v, data in G.edges(data=True):
            connected = data.get('connected', True)
            rho = abs(data.get('rho', 0.0))

            if not connected:
                edge_colors.append('lightgray')
                edge_styles.append('dashed')
            elif rho > 0.9:
                edge_colors.append('#e74c3c')  # red
                edge_styles.append('solid')
            elif rho > 0.7:
                edge_colors.append('#e67e22')  # orange
                edge_styles.append('solid')
            else:
                edge_colors.append('#2ecc71')  # green
                edge_styles.append('solid')

        node_colors = [color_map.get(n, 'gray') for n in G.nodes()]

        # Use config coordinates if available (stable layout)
        pos = None
        if config:
            bus_coords = {}
            for b_cfg in config.get("buses", []):
                if "lon" in b_cfg and "lat" in b_cfg:
                    bus_coords[b_cfg["id"]] = (b_cfg["lon"], b_cfg["lat"])
            if len(bus_coords) == G.number_of_nodes():
                pos = bus_coords

        if pos is None and G.number_of_nodes() > 0:
            pos = nx.spring_layout(G, seed=42)

        if G.number_of_nodes() > 0 and pos:
            # Draw solid edges
            solid_edges = [
                (u, v) for (u, v, _), s in zip(G.edges(data=True), edge_styles)
                if s == 'solid'
            ]
            solid_colors = [
                c for c, s in zip(edge_colors, edge_styles) if s == 'solid'
            ]
            dashed_edges = [
                (u, v) for (u, v, _), s in zip(G.edges(data=True), edge_styles)
                if s == 'dashed'
            ]
            dashed_colors = [
                c for c, s in zip(edge_colors, edge_styles) if s == 'dashed'
            ]

            nx.draw_networkx_nodes(
                G, pos, ax=ax1, node_color=node_colors, node_size=300
            )
            nx.draw_networkx_labels(G, pos, ax=ax1, font_size=8)

            if solid_edges:
                nx.draw_networkx_edges(
                    G, pos, ax=ax1, edgelist=solid_edges,
                    edge_color=solid_colors, width=2, style='solid'
                )
            if dashed_edges:
                nx.draw_networkx_edges(
                    G, pos, ax=ax1, edgelist=dashed_edges,
                    edge_color=dashed_colors, width=1, style='dashed'
                )

            # Legend
            legend_elements = [
                Line2D([0], [0], marker='o', color='w',
                       markerfacecolor='#2ecc71', markersize=10,
                       label='Generator/Slack'),
                Line2D([0], [0], marker='o', color='w',
                       markerfacecolor='#e74c3c', markersize=10,
                       label='Load'),
                Line2D([0], [0], marker='o', color='w',
                       markerfacecolor='#3498db', markersize=10,
                       label='Battery'),
                Line2D([0], [0], marker='o', color='w',
                       markerfacecolor='#f1c40f', markersize=10,
                       label='Renewable'),
            ]
            ax1.legend(handles=legend_elements, loc='upper left', fontsize=7)
        else:
            ax1.text(0.5, 0.5, "No buses in observation",
                     ha='center', va='center', transform=ax1.transAxes)

        ax1.set_title("Grid Topology & Loading")

        # --- Plot 2: Frequency Trace ---
        if history:
            history_sorted = sorted(history, key=lambda h: h.timestep)
            timesteps = [h.timestep for h in history_sorted]
            freqs = [h.grid_frequency for h in history_sorted]

            ax2.plot(timesteps, freqs, label='Frequency (Hz)',
                     color='#2980b9', linewidth=1.5)
            ax2.axhline(y=50.0, color='k', linestyle='--', linewidth=0.8)
            ax2.fill_between(timesteps, 49.5, 50.5,
                             color='green', alpha=0.1, label='Normal band')
            ax2.legend(fontsize=8)
        else:
            ax2.text(0.5, 0.5, "No frequency history",
                     ha='center', va='center', transform=ax2.transAxes)

        ax2.set_title("Frequency Stability")
        ax2.set_xlabel("Timestep")
        ax2.set_ylabel("Hz")
        ax2.set_ylim(48.5, 51.5)

        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        return base64.b64encode(buf.read()).decode('utf-8')

    finally:
        plt.close(fig)