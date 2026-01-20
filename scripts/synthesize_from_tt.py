
import sys
import json
import time
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from truth_table.truth_table import TruthTable
from synthesizers.eca57_synthesizer import ECA57Synthesizer
from sat.solver import Solver

import concurrent.futures
import threading

def solve_with_racer(input_tt, gate_count, solvers_list):
    """
    Race multiple solvers to find a circuit with gate_count gates.
    Returns the circuit if found, or None.
    """
    result_circuit = None
    stop_event = threading.Event()
    
    def _run_solver(solver_name):
        nonlocal result_circuit
        if stop_event.is_set():
            return None
            
        try:
            solver = Solver(solver_name)
            # Create a new synthesizer instance for this thread
            # Assuming ECA57Synthesizer is thread-safe or lightweight enough
            # Make a copy of truth table if needed, but it seems immutable enough here
            synth = ECA57Synthesizer(input_tt, gate_count, solver)
            
            # Check stop event periodically? 
            # The solve() method blocks, so we can't easily interrupt it 
            # without modifying the synthesizer/solver 
            # but we can check immediately after return
            
            circuit = synth.solve()
            
            if circuit and not stop_event.is_set():
                result_circuit = circuit
                stop_event.set() # Signal other threads to stop (lazy cancellation)
                return circuit
        except Exception:
            pass
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(solvers_list)) as executor:
        futures = {executor.submit(_run_solver, name): name for name in solvers_list}
        
        # Wait for first success
        for future in concurrent.futures.as_completed(futures):
            if stop_event.is_set():
                # We have a winner, try to cancel others (best effort)
                for f in futures:
                    f.cancel()
                break
                
    return result_circuit

def main():
    try:
        # Read JSON from stdin
        input_data = json.load(sys.stdin)
        
        num_inputs = input_data["num_inputs"]
        output_cols = input_data["output_truth_tables"] 
        current_num_gates = input_data["current_num_gates"]
        time_limit = input_data.get("time_limit", 10)
        
        # Determine solvers to race
        # Default portfolio for racing
        default_racers = ["cadical153", "glucose4", "minisat22"]
        
        explicit_solver = input_data.get("solver_name")
        solvers_to_use = [explicit_solver] if explicit_solver else default_racers

        # Transpose columns to rows for TruthTable constructor
        num_rows = len(output_cols[0])
        rows = []
        for r in range(num_rows):
            row = []
            for i in range(num_inputs):
                bit_char = output_cols[i][r]
                row.append(1 if bit_char == '1' else 0)
            rows.append(row)
            
        tt = TruthTable(num_inputs, bits=rows)
        
        # Check if 0 gates works (identity functionality)
        id_tt = TruthTable(num_inputs)
        if tt == id_tt:
             print(json.dumps({
                "success": True,
                "gates": []
            }))
             return

        for gc in range(1, current_num_gates):
            # Use racing strategy
            circuit = solve_with_racer(tt, gc, solvers_to_use)
            
            if circuit:
                # Found a shorter circuit!
                gates = []
                for g in circuit.gates():
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
