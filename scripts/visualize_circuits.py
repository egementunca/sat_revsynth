"""Generate ASCII art for small identity circuits (Verification)."""
import sys
sys.path.insert(0, "src")

from truth_table.truth_table import TruthTable
from sat.solver import Solver
from synthesizers.circuit_synthesizer import CircuitSynthesizer
from synthesizers.eca57_synthesizer import ECA57Synthesizer
from database.equivalence import canonical_repr
import argparse

def draw_mct_circuit(width, gates):
    """Draw ASCII for MCT circuit."""
    grid = [['-' for _ in range(len(gates) * 2 + 1)] for _ in range(width)]
    for i, (controls, target) in enumerate(gates):
        col = i * 2 + 1
        if not controls:
            grid[target][col] = 'X'
        else:
            min_wire = min(controls + [target])
            max_wire = max(controls + [target])
            for w in range(min_wire, max_wire + 1):
                grid[w][col] = '|'
            for c in controls:
                grid[c][col] = '●'
            grid[target][col] = '⊕'
    return "\n".join([f"q{i}: " + "".join(grid[i]) for i in range(width)])

def draw_eca57_circuit(width, gates):
    """Draw ASCII for ECA57 circuit: target ^= (c1 OR !c2)."""
    grid = [['-' for _ in range(len(gates) * 2 + 1)] for _ in range(width)]
    for i, (target, c1, c2) in enumerate(gates):
        col = i * 2 + 1
        # Draw vertical backbone
        min_wire = min(target, c1, c2)
        max_wire = max(target, c1, c2)
        for w in range(min_wire, max_wire + 1):
            grid[w][col] = '|'
            
        # Draw connections
        grid[target][col] = '⊕'
        grid[c1][col] = '●' # Active High
        grid[c2][col] = '○' # Active Low
        
    return "\n".join([f"q{i}: " + "".join(grid[i]) for i in range(width)])

def run_demo(width=2, gates=2, output_file="circuits.txt", gate_set="mct"):
    tt = TruthTable(width)
    solver = Solver("cadical153")
    
    unique_circuits = {}
    
    print(f"Synthesizing {gate_set.upper()} Width={width}, Gates={gates}...")
    
    if gate_set == "mct":
        synth = CircuitSynthesizer(tt, gates, solver)
        synth.disable_empty_lines()
        
        while True:
            circuit = synth.solve()
            if circuit is None:
                break
            gate_list = [(list(c), t) for c, t in circuit.gates()]
            canon = canonical_repr(circuit)
            if canon not in unique_circuits:
                unique_circuits[canon] = gate_list
            synth.exclude_solution(circuit)
            
    elif gate_set == "eca57":
        synth = ECA57Synthesizer(tt, gates, solver)
        # Note: canonical_repr for ECA57 not implemented, filtering by exact tuple sequence
        # hash(tuple(gates))
        
        while True:
            circuit = synth.solve()
            if circuit is None:
                break
            
            # Convert gate objects to tuples
            gate_list = [g.to_tuple() for g in circuit.gates()]
            # Simple dedup for verification (no canonicalization)
            canon = str(gate_list) 
            
            if canon not in unique_circuits:
                unique_circuits[canon] = gate_list
            
            synth.exclude_solution(circuit)

    with open(output_file, "w") as f:
        f.write(f"Identity Templates ({gate_set.upper()}, Width={width}, Gates={gates})\n")
        f.write("========================================\n\n")
        for i, (canon, gates_data) in enumerate(unique_circuits.items(), 1):
            f.write(f"Template #{i}\n")
            if gate_set == "mct":
                f.write(draw_mct_circuit(width, gates_data))
            else:
                f.write(draw_eca57_circuit(width, gates_data))
            f.write("\n\n" + "-"*40 + "\n\n")
            
    print(f"Found {len(unique_circuits)} unique templates.")
    print(f"Drawings saved to: {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Visualize identity templates")
    parser.add_argument("--width", type=int, default=2, help="Circuit width")
    parser.add_argument("--gates", type=int, default=2, help="Number of gates")
    parser.add_argument("--output", type=str, default="circuits.txt", help="Output file")
    parser.add_argument("--gate-set", type=str, default="mct", choices=["mct", "eca57"], help="Gate set")
    args = parser.parse_args()
    
    run_demo(args.width, args.gates, args.output, args.gate_set)
