import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for server use
import matplotlib.pyplot as plt
import networkx as nx
import io, base64


def _parse_line_endpoints(line_id: str):
    """Safely parse line ID format 'L_u_v' into endpoint bus IDs.

    Returns (u, v) on success, None on parse failure.
    This guard prevents silent failures if the line ID format ever changes.
    """
    try:
        parts = line_id.split('_')
        if len(parts) >= 3:
            return int(parts[1]), int(parts[2])
    except (ValueError, IndexError):
        pass
    return None


def generate_dashboard(history: list, current_obs):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    # Plot 1: Grid Topology
    G = nx.Graph()

    # Use a dict keyed by bus.id for correct color mapping,
    # even if bus IDs are non-contiguous or unordered.
    color_map = {}
    for bus in current_obs.buses:
        G.add_node(bus.id)
        if bus.type in ['generator', 'slack']:
            color_map[bus.id] = 'green'
        elif bus.type == 'load':
            color_map[bus.id] = 'red'
        elif bus.type == 'battery':
            color_map[bus.id] = 'blue'
        else:
            color_map[bus.id] = 'yellow'

    edge_colors = []
    for line in current_obs.lines:
        if line.connected:
            endpoints = _parse_line_endpoints(line.id)
            if endpoints is None:
                continue  # Skip lines with unparseable IDs
            u, v = endpoints
            G.add_edge(u, v)

            rho = abs(line.rho)
            if rho > 0.9:
                edge_colors.append('red')
            elif rho > 0.7:
                edge_colors.append('orange')
            else:
                edge_colors.append('green')

    # Build node color list in the same order as G.nodes()
    node_colors = [color_map.get(n, 'gray') for n in G.nodes()]

    pos = nx.spring_layout(G, seed=42)
    nx.draw(G, pos, ax=ax1, node_color=node_colors, edge_color=edge_colors, with_labels=True, width=2)
    ax1.set_title("Grid Topology & Loading")

    # Plot 2: Frequency Trace
    timesteps = [h.timestep for h in history]
    freqs = [h.grid_frequency for h in history]

    ax2.plot(timesteps, freqs, label='Frequency (Hz)')
    ax2.axhline(y=50.0, color='k', linestyle='--')
    ax2.fill_between(timesteps, 49.5, 50.5, color='green', alpha=0.1)

    ax2.set_title("Frequency Stability")
    ax2.set_xlabel("Timestep")
    ax2.set_ylabel("Hz")
    ax2.legend()

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    plt.close()
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')