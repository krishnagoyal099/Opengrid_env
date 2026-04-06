import matplotlib.pyplot as plt
import networkx as nx
import io, base64

def generate_dashboard(history: list, current_obs):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    # Plot 1: Grid Topology
    G = nx.Graph()
    
    colors = []
    for bus in current_obs.buses:
        G.add_node(bus.id)
        if bus.type in ['generator', 'slack']: colors.append('green')
        elif bus.type == 'load': colors.append('red')
        elif bus.type == 'battery': colors.append('blue')
        else: colors.append('yellow')
            
    edge_colors = []
    for line in current_obs.lines:
        if line.connected:
            # Parse IDs "L_u_v"
            parts = line.id.split('_')
            u, v = int(parts[1]), int(parts[2])
            G.add_edge(u, v)
            
            rho = abs(line.rho)
            if rho > 0.9: edge_colors.append('red')
            elif rho > 0.7: edge_colors.append('orange')
            else: edge_colors.append('green')
    
    pos = nx.spring_layout(G, seed=42)
    nx.draw(G, pos, ax=ax1, node_color=colors, edge_color=edge_colors, with_labels=True, width=2)
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