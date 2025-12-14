"""Generate ASCII art for small identity circuits (Verification)."""
import sys
sys.path.insert(0, "src")

from truth_table.truth_table import TruthTable
from sat.solver import Solver
from synthesizers.circuit_synthesizer import CircuitSynthesizer
from database.equivalence import canonical_repr

def draw_circuit_ascii(width, gates):
    """Draw a simple ASCII representation of the circuit."""
    # Build grid: wires x (gates * 2 + 1)
    grid = [['-' for _ in range(len(gates) * 2 + 1)] for _ in range(width)]
    
    for i, (controls, target) in enumerate(gates):
        col = i * 2 + 1
        
        # Draw control connections
        if not controls:
            # X gate (no controls)
            grid[target][col] = 'X'
        else:
            # MCT gate
            min_wire = min(controls + [target])
            max_wire = max(controls + [target])
            
            # Draw vertical line
            for w in range(min_wire, max_wire + 1):
                grid[w][col] = '|'
                
            for c in controls:
                grid[c][col] = '●'
            grid[target][col] = '⊕'
            
    # Convert to string
    lines = []
    for i in range(width):
        lines.append(f"q{i}: " + "".join(grid[i]))
    return "\n".join(lines)


def run_demo(width=2, gates=2, filename="small_circuits.txt"):
    tt = TruthTable(width)
    solver = Solver("cadical153")
    synth = CircuitSynthesizer(tt, gates, solver)
    synth.disable_empty_lines() # Optional
    
    unique_circuits = {}
    
    print(f"Synthesizing Width={width}, Gates={gates}...")
    
    while True:
        circuit = synth.solve()
        if circuit is None:
            break
            
        gate_list = [(list(c), t) for c, t in circuit.gates()]
        canon = canonical_repr(circuit)
        
        if canon not in unique_circuits:
            unique_circuits[canon] = gate_list
            
        synth.exclude_solution(circuit)
    
    # Write to file
    with open(filename, "w") as f:
        f.write(f"Identity Templates (Width={width}, Gates={gates})\n")
        f.write("========================================\n\n")
        
        for i, (canon, gates_data) in enumerate(unique_circuits.items(), 1):
            f.write(f"Template #{i}\n")
            f.write(f"Canonical Hash: {hash(canon)}\n")
            f.write(draw_circuit_ascii(width, gates_data))
            f.write("\n\n" + "-"*40 + "\n\n")
            
    print(f"Found {len(unique_circuits)} unique templates.")
    print(f"Drawings saved to: {filename}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Visualize identity templates")
    parser.add_argument("--width", type=int, default=2, help="Circuit width")
    parser.add_argument("--gates", type=int, default=2, help="Number of gates")
    parser.add_argument("--output", type=str, default="circuits.txt", help="Output file")
    args = parser.parse_args()
    
    run_demo(args.width, args.gates, args.output)
