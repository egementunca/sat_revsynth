"""
ECA57 Visualization Utilities

Includes:
- Circuit ASCII drawer
- Skeleton graph builder
- Topological ordering (push-left based on collisions)
- Combined circuit + skeleton visualization
- Random circuit generator
"""
from __future__ import annotations
import random
from typing import List, Tuple, Optional, Dict, Set
from dataclasses import dataclass
import networkx as nx

# Import ECA57 types
import sys
sys.path.insert(0, '/Users/egementunca/research-group/sat_revsynth/src')
from gates.eca57 import ECA57Gate, ECA57Circuit, all_eca57_gates


# =============================================================================
# COMMUTATION CHECK
# =============================================================================

def gates_collide(g1: ECA57Gate, g2: ECA57Gate) -> bool:
    """
    Check if two ECA57 gates collide (do NOT commute).
    
    Gates collide iff:
      g1.target ∈ {g2.ctrl1, g2.ctrl2}  OR  g2.target ∈ {g1.ctrl1, g1.ctrl2}
    
    This is the NEGATION of the commutation condition from the paper (Eq. 4).
    """
    g1_target_in_g2_controls = g1.target in (g2.ctrl1, g2.ctrl2)
    g2_target_in_g1_controls = g2.target in (g1.ctrl1, g1.ctrl2)
    return g1_target_in_g2_controls or g2_target_in_g1_controls


def gates_commute(g1: ECA57Gate, g2: ECA57Gate) -> bool:
    """Check if two gates commute (can be swapped without changing the circuit)."""
    return not gates_collide(g1, g2)


# =============================================================================
# SKELETON GRAPH
# =============================================================================
def build_skeleton_graph(circuit: ECA57Circuit) -> nx.DiGraph:
    """
    Build skeleton graph from circuit.
    
    Nodes: Gate indices (0, 1, 2, ...)
    Edges: Directed edge i → j if gate i collides with gate j AND i < j
    
    This captures the "must come before" relationship.
    Gates in the same topological level can be freely reordered.
    """
    G = nx.DiGraph()
    gates = circuit.gates()
    n = len(gates)

    for i, g in enumerate(gates):
        G.add_node(i, gate=g, target=g.target, ctrl1=g.ctrl1, ctrl2=g.ctrl2)

    # precompute collisions
    coll = [[False]*n for _ in range(n)]
    for i in range(n):
        for j in range(i+1, n):
            c = gates_collide(gates[i], gates[j])
            coll[i][j] = c
            coll[j][i] = c

    # add ONLY skeleton edges
    for i in range(n):
        for j in range(i+1, n):
            if not coll[i][j]:
                continue
            # exclude if exists k with i<k<j colliding with both
            if any(coll[i][k] and coll[k][j] for k in range(i+1, j)):
                continue
            G.add_edge(i, j)

    return G    


def get_topological_levels(G: nx.DiGraph) -> List[List[int]]:
    """
    Get topological levels (generations) from skeleton graph.
    
    Returns list of lists, where each inner list contains gate indices
    that can be executed in parallel (no dependencies between them).
    """
    return list(nx.topological_generations(G))


# =============================================================================
# ORDERING FUNCTIONS
# =============================================================================

def order_push_left(circuit: ECA57Circuit) -> List[int]:
    """
    Order gates by pushing them left until they collide.
    
    Returns list of gate indices in the new order.
    Gates are placed in topological levels, then sorted within each level.
    """
    G = build_skeleton_graph(circuit)
    levels = get_topological_levels(G)
    gates = circuit.gates()
    
    ordered = []
    for level in levels:
        # Within each level, sort by target wire (highest target first = top of circuit)
        level_sorted = sorted(level, key=lambda i: -gates[i].target)
        ordered.extend(level_sorted)
    
    return ordered


def reorder_circuit(circuit: ECA57Circuit, order: List[int]) -> ECA57Circuit:
    """Create new circuit with gates in specified order."""
    new_circuit = ECA57Circuit(circuit.width())
    gates = circuit.gates()
    for i in order:
        g = gates[i]
        new_circuit.add_gate(g.target, g.ctrl1, g.ctrl2)
    return new_circuit


# =============================================================================
# RANDOM CIRCUIT GENERATOR
# =============================================================================

def random_eca57_circuit(width: int, gate_count: int) -> ECA57Circuit:
    """
    Generate a random ECA57 circuit.
    
    Args:
        width: Number of wires (must be >= 3)
        gate_count: Number of gates
        
    Returns:
        Random ECA57Circuit
    """
    assert width >= 3, "ECA57 requires at least 3 wires"
    
    all_gates = all_eca57_gates(width)
    circuit = ECA57Circuit(width)
    
    for _ in range(gate_count):
        g = random.choice(all_gates)
        circuit.add_gate(g.target, g.ctrl1, g.ctrl2)
    
    return circuit


def random_eca57_identity(width: int, gate_count: int) -> ECA57Circuit:
    """
    Generate a random identity circuit by pairing gates with their inverses.
    
    Since ECA57 gates are self-inverse, this creates pairs G, G.
    Then shuffles them while maintaining identity property.
    """
    assert gate_count % 2 == 0, "gate_count must be even for identity"
    assert width >= 3, "ECA57 requires at least 3 wires"
    
    all_gates = all_eca57_gates(width)
    circuit = ECA57Circuit(width)
    
    # Create pairs of identical gates (G, G)
    pairs = []
    for _ in range(gate_count // 2):
        g = random.choice(all_gates)
        pairs.append((g, g))
    
    # Flatten and add to circuit
    for g1, g2 in pairs:
        circuit.add_gate(g1.target, g1.ctrl1, g1.ctrl2)
        circuit.add_gate(g2.target, g2.ctrl1, g2.ctrl2)
    
    return circuit


# =============================================================================
# ASCII CIRCUIT DRAWER
# =============================================================================

def draw_circuit_ascii(circuit: ECA57Circuit, show_indices: bool = True) -> str:
    """
    Draw ECA57 circuit in ASCII art.
    
    ECA57 gate representation:
    - Target: ⊕ (XOR)
    - ctrl1 (active-high): ● (filled dot)
    - ctrl2 (active-low/inverted): ○ (empty dot)
    - Vertical connections: │
    
    Example for gate (target=1, ctrl1=0, ctrl2=2):
    
      0 ─●─
        │
      1 ─⊕─
        │
      2 ─○─
    """
    gates = circuit.gates()
    width = circuit.width()
    n_gates = len(gates)
    
    if n_gates == 0:
        return "Empty circuit"
    
    # Build the grid
    # Each gate takes 3 columns: pre-wire, symbol, post-wire
    lines = []
    
    for wire in range(width):
        line = f"{wire:2d} ─"
        
        for g_idx, g in enumerate(gates):
            # Determine what symbol goes on this wire for this gate
            if wire == g.target:
                symbol = "⊕"
            elif wire == g.ctrl1:
                symbol = "●"  # active-high control
            elif wire == g.ctrl2:
                symbol = "○"  # active-low control (inverted)
            else:
                # Check if we need a vertical line (between gate wires)
                min_wire = min(g.target, g.ctrl1, g.ctrl2)
                max_wire = max(g.target, g.ctrl1, g.ctrl2)
                if min_wire < wire < max_wire:
                    symbol = "│"
                else:
                    symbol = "─"
            
            line += symbol + "─"
        
        lines.append(line)
    
    # Add gate indices below
    if show_indices:
        idx_line = "    "
        for i in range(n_gates):
            idx_line += f"{i} "
        lines.append(idx_line)
    
    return "\n".join(lines)


# =============================================================================
# MATPLOTLIB VISUALIZATION
# =============================================================================

def visualize_circuit_and_skeleton(
    circuit: ECA57Circuit,
    title: str = "ECA57 Circuit",
    figsize: Tuple[int, int] = (14, 6),
    save_path: Optional[str] = None
):
    """
    Create a dual figure showing:
    - Left: Circuit diagram with gates colored by topological level
    - Right: Skeleton graph with same coloring
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.colors import to_rgba
    
    # Build skeleton graph and get levels
    G = build_skeleton_graph(circuit)
    levels = get_topological_levels(G)
    gates = circuit.gates()
    width = circuit.width()
    n_gates = len(gates)
    
    # Assign colors to levels
    cmap = plt.cm.Set3
    level_colors = {}
    node_colors = []
    for level_idx, level in enumerate(levels):
        color = cmap(level_idx / max(len(levels), 1))
        for node in level:
            level_colors[node] = color
            node_colors.append(color)
    
    # Create figure
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)
    
    # === LEFT: Circuit diagram ===
    ax1.set_title("Circuit Diagram")
    ax1.set_xlim(-0.5, n_gates + 0.5)
    ax1.set_ylim(-0.5, width - 0.5)
    ax1.invert_yaxis()  # Wire 0 at top
    
    # Draw wires
    for wire in range(width):
        ax1.plot([-0.3, n_gates + 0.3], [wire, wire], 'k-', linewidth=1, zorder=1)
        ax1.text(-0.5, wire, f"w{wire}", ha='right', va='center', fontsize=10)
    
    # Draw gates
    for g_idx, g in enumerate(gates):
        color = level_colors[g_idx]
        
        # Draw vertical line connecting gate wires
        min_wire = min(g.target, g.ctrl1, g.ctrl2)
        max_wire = max(g.target, g.ctrl1, g.ctrl2)
        ax1.plot([g_idx, g_idx], [min_wire, max_wire], 'k-', linewidth=2, zorder=2)
        
        # Draw target (XOR symbol - circle with plus)
        circle = plt.Circle((g_idx, g.target), 0.15, color=color, ec='black', linewidth=2, zorder=3)
        ax1.add_patch(circle)
        ax1.plot([g_idx - 0.1, g_idx + 0.1], [g.target, g.target], 'k-', linewidth=1.5, zorder=4)
        ax1.plot([g_idx, g_idx], [g.target - 0.1, g.target + 0.1], 'k-', linewidth=1.5, zorder=4)
        
        # Draw ctrl1 (filled dot - active high)
        ax1.plot(g_idx, g.ctrl1, 'ko', markersize=10, zorder=3)
        
        # Draw ctrl2 (empty dot - active low/inverted)
        circle2 = plt.Circle((g_idx, g.ctrl2), 0.08, color='white', ec='black', linewidth=2, zorder=3)
        ax1.add_patch(circle2)
        
        # Gate index label
        ax1.text(g_idx, width + 0.3, str(g_idx), ha='center', va='top', fontsize=8)
    
    ax1.set_xticks([])
    ax1.set_yticks([])
    ax1.set_aspect('equal')
    
    # === RIGHT: Skeleton graph ===
    ax2.set_title("Skeleton Graph (collisions)")
    
    # Position nodes by level
    pos = {}
    for level_idx, level in enumerate(levels):
        for i, node in enumerate(sorted(level)):
            x = level_idx
            y = i - len(level) / 2
            pos[node] = (x, y)
    
    # Draw edges
    nx.draw_networkx_edges(G, pos, ax=ax2, edge_color='gray', 
                           arrows=True, arrowsize=15, 
                           connectionstyle="arc3,rad=0.1")
    
    # Draw nodes
    nx.draw_networkx_nodes(G, pos, ax=ax2, node_color=[level_colors[n] for n in G.nodes()],
                           node_size=500, edgecolors='black', linewidths=2)
    
    # Node labels (gate index and target)
    labels = {i: f"{i}\n(t{gates[i].target})" for i in range(n_gates)}
    nx.draw_networkx_labels(G, pos, labels, ax=ax2, font_size=8)
    
    ax2.set_aspect('equal')
    ax2.axis('off')
    
    # Legend for levels
    patches = [mpatches.Patch(color=cmap(i / max(len(levels), 1)), 
                              label=f"Level {i}") for i in range(len(levels))]
    ax2.legend(handles=patches, loc='upper right', fontsize=8)
    
    plt.suptitle(title, fontsize=14, fontweight='bold')
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved to {save_path}")
    
    plt.show()
    return fig


# =============================================================================
# DEMO
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("ECA57 VISUALIZATION UTILITIES DEMO")
    print("=" * 70)
    
    # Generate random circuit
    print("\n1. Random circuit (W=5, G=6):")
    circuit = random_eca57_circuit(5, 6)
    print(draw_circuit_ascii(circuit))
    
    # Build skeleton graph
    print("\n2. Skeleton graph:")
    G = build_skeleton_graph(circuit)
    print(f"   Nodes: {list(G.nodes())}")
    print(f"   Edges (collisions): {list(G.edges())}")
    
    # Topological levels
    print("\n3. Topological levels:")
    levels = get_topological_levels(G)
    for i, level in enumerate(levels):
        gates_in_level = [circuit.gates()[j] for j in level]
        print(f"   Level {i}: gates {level} -> {[g.to_tuple() for g in gates_in_level]}")
    
    # Reorder
    print("\n4. Reordered circuit (push-left):")
    order = order_push_left(circuit)
    print(f"   New order: {order}")
    reordered = reorder_circuit(circuit, order)
    print(draw_circuit_ascii(reordered))
    
    # Verify same function
    print("\n5. Verify reordering preserves function:")
    # Compare truth tables
    original_tt = circuit.compute_truth_table()
    reordered_tt = reordered.compute_truth_table()
    same = original_tt == reordered_tt
    print(f"   Same truth table: {same}")
    
    print("\n6. Generating visualization...")
    visualize_circuit_and_skeleton(circuit, title="Random ECA57 Circuit (W=5, G=6)")
