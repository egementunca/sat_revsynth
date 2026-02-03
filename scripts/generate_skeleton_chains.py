#!/usr/bin/env python3
"""
Generate Skeleton Chains (Backbones)
Generates identity circuits with strict chain collision constraints.
"""

import sys
import os
import time

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from sat.solver import Solver

from synthesizers.eca57_skeleton_synthesizer import ECA57SkeletonSynthesizer
from circuit.circuit import Circuit
from truth_table.truth_table import TruthTable

# Helper to match UI's character mapping
def wire_to_char(w):
    if 0 <= w <= 9:
        return str(w)
    if 10 <= w <= 35:
        return chr(w - 10 + ord('a'))
    if 36 <= w <= 61:
        return chr(w - 36 + ord('A'))
    return "?"

def generate_chain(wires, gates, chain_len, filename):
    print(f"Generating: Wires={wires}, Gates={gates}, Chain={chain_len}...")
    start = time.time()
    
    # Target: Identity (Empty Truth Table implies identity if we synthesize to match input=output, 
    # but simplest is to synthesize "Identity" function)
    # The synthesizer takes 'output' truth table. For identity, output = input.
    # However, TruthTable class usually takes num_inputs, num_outputs.
    # Let's check how to construct Identity TruthTable.
    # Actually, for large wires, full TruthTable is impossible.
    # But SAT synthesizer works symbolically. We might bypass TruthTable if the class supports it,
    # or use a partial spec.
    # The ECA57SkeletonSynthesizer takes `output: TruthTable`. 
    # Wait, for 16 wires, TT is 2^16 entries. Doable (65k).
    # For 32 wires, impossible. The user asked for "low to medium widths". 
    # Let's stick to 4, 8, maybe 12. 16 is pushing it for full TT synthesis unless we use symbolic 'Identity' constraint directly.
    # Looking at the code, it uses `self.output.values`. 
    # Let's try 4 and 8 wires first.
    
    # Construct Identity TT
    # For N wires, we have 2^N rows.
    # Identity: f(x) = x.
    identity_values = list(range(1 << wires))
    
    # Explicitly pass values to avoid constructor ambiguity
    tt = TruthTable(wires, values=identity_values)
        
    solver = Solver("glucose4")
    synth = ECA57SkeletonSynthesizer(
        output=tt,
        gate_count=gates,
        solver=solver,
        chain_length=chain_len,
        avoid_adjacent_identical=True
    )
    
    result = synth.solve()
    duration = time.time() - start
    
    if result:
        print(f"  Success in {duration:.2f}s")
        with open(filename, "w") as f:
            for g in result.gates():
                # UI Format: Target, Ctrl1, Ctrl2 (No spaces)
                # e.g. "012;"
                t = wire_to_char(g.target)
                c1 = wire_to_char(g.ctrl1)
                c2 = wire_to_char(g.ctrl2)
                line = f"{t}{c1}{c2};"
                f.write(line + "\n")
        print(f"  Saved to {filename}")
    else:
        print(f"  Failed (UNSAT) in {duration:.2f}s")

def main():
    out_dir = os.path.join(os.path.dirname(__file__), "..", "generated_skeletons")
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    # 3 wires, 8 gates (relaxed from 6 to find solution)
    generate_chain(3, 8, 8, os.path.join(out_dir, "chain_3w_8g.gate"))
    
    # 4 wires, 10 gates
    generate_chain(4, 10, 10, os.path.join(out_dir, "chain_4w_10g.gate"))
    
    # Medium Width (Might take longer due to TT size 2^8 = 256, feasible)
    generate_chain(6, 12, 12, os.path.join(out_dir, "chain_6w_12g.gate"))
    
    # 8 Wires (256 rows, 20 gates - might be slow for SAT)
    # Let's try a short one
    generate_chain(8, 16, 16, os.path.join(out_dir, "chain_8w_16g.gate"))

if __name__ == "__main__":
    main()
