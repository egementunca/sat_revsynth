#!/usr/bin/env python3
"""
Experiment: Skeleton Based SAT ID Creation
Generates ECA57 identity circuits with skeleton constraints (chain collisions).
"""
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from truth_table.truth_table import TruthTable
from sat.solver import Solver
from synthesizers.eca57_skeleton_synthesizer import ECA57SkeletonSynthesizer

def run_experiment(wires, min_gates, max_gates, chain_length=None):
    print(f"\n--- Experiment: Wires={wires}, ChainLength={chain_length} ---")
    tt = TruthTable(wires)
    solver = Solver("glucose4") # Ensure glucose4 is available or use another solver if needed
    
    start_time = time.time()
    found_circuit = None
    
    for gate_count in range(min_gates, max_gates + 1, 2): # Even steps for identity usually
        print(f"Trying {gate_count} gates...", end="", flush=True)
        # Re-init solver for clean state usually better, or create new synthesizer
        synth = ECA57SkeletonSynthesizer(
            tt, 
            gate_count=gate_count, 
            solver=Solver("glucose4"),
            chain_length=chain_length
        )
        circuit = synth.solve()
        
        if circuit:
            print(f" FOUND!")
            found_circuit = circuit
            break
        else:
            print(" UNSAT")
            
    end_time = time.time()
    duration = end_time - start_time
    
    if found_circuit:
        print(f"SUCCESS: Found circuit with {len(list(found_circuit.gates()))} gates in {duration:.2f}s")
        print(f"Circuit: {found_circuit}")
    else:
        print(f"FAILURE: No circuit found up to {max_gates} gates in {duration:.2f}s")

def main():
    print("Starting Skeleton SAT ID Creation Experiments...")
    
    # 1. Small Identity: 3 wires, chain_length=None (full chain)
    run_experiment(wires=3, min_gates=6, max_gates=10, chain_length=None)
    
    # 2. Medium Identity: 4 wires, chain_length=None
    run_experiment(wires=4, min_gates=8, max_gates=12, chain_length=None)
    
    # 3. Constrained Identity: 4 wires, chain_length=3
    run_experiment(wires=4, min_gates=8, max_gates=12, chain_length=3)

    # 4. Larger Identity: 5 wires (May be slow)
    run_experiment(wires=5, min_gates=10, max_gates=14, chain_length=None)

if __name__ == "__main__":
    main()
