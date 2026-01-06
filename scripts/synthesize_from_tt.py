
import sys
import json
import time
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from truth_table.truth_table import TruthTable
from synthesizers.eca57_synthesizer import ECA57Synthesizer
from sat.solver import Solver

def main():
    try:
        # Read JSON from stdin
        input_data = json.load(sys.stdin)
        
        num_inputs = input_data["num_inputs"]
        output_cols = input_data["output_truth_tables"] # List of strings, one per wire
        current_num_gates = input_data["current_num_gates"]
        time_limit = input_data.get("time_limit", 10)
        solver_name = input_data.get("solver_name", "cadical153")
        
        # Transpose columns to rows for TruthTable constructor
        # output_cols[i] is the string of bits for wire i
        # rows[r] should be [wire0, wire1, ...] for row r
        num_rows = len(output_cols[0])
        rows = []
        for r in range(num_rows):
            row = []
            for i in range(num_inputs):
                bit_char = output_cols[i][r]
                row.append(1 if bit_char == '1' else 0)
            rows.append(row)
            
        tt = TruthTable(num_inputs, bits=rows)
        
        # Try to find a shorter circuit
        # We iterate from 0 to current_num_gates - 1
        # (Though 0 is trivial)
        
        found_solution = None
        
        # Optimization: start checking from lower bound?
        # For now, just linear scan.
        
        # Check if 0 gates works (identity functionality)
        # TruthTable(N) creates identity
        id_tt = TruthTable(num_inputs)
        if tt == id_tt:
             print(json.dumps({
                "success": True,
                "gates": []
            }))
             return

        for gc in range(1, current_num_gates):
            # Check timeout? 
            # We rely on solver internal check or loop break
            
            # Instantiate solver
            solver = Solver(solver_name)
            synth = ECA57Synthesizer(tt, gc, solver)
            
            # Solve
            circuit = synth.solve()
            
            if circuit:
                # Found a shorter circuit!
                gates = []
                for g in circuit.gates():
                    # g is [t, c1, c2]
                    gates.append(list(g))
                
                print(json.dumps({
                    "success": True,
                    "gates": gates
                }))
                return
                
        # If we get here, no shorter circuit found
        print(json.dumps({
            "success": False,
            "error": "No shorter circuit found"
        }))
        
    except Exception as e:
        # sys.stderr.write(f"Error: {e}\n")
        print(json.dumps({
            "success": False,
            "error": str(e)
        }))
        exit(1)

if __name__ == "__main__":
    main()
