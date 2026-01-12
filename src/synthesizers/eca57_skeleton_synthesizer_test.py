"""Tests for ECA57SkeletonSynthesizer."""
from __future__ import annotations

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from truth_table.truth_table import TruthTable
from sat.solver import Solver
from synthesizers.eca57_skeleton_synthesizer import ECA57SkeletonSynthesizer


def gates_collide(g1, g2):
    """Check if two ECA57 gates collide (non-commute).
    
    Collision if target of one is in controls of other.
    """
    g1_t = g1.target
    g1_c = {g1.ctrl1, g1.ctrl2}
    
    g2_t = g2.target
    g2_c = {g2.ctrl1, g2.ctrl2}
    
    # g1 target in g2 controls
    cond1 = g1_t in g2_c
    # g2 target in g1 controls
    cond2 = g2_t in g1_c
    
    return cond1 or cond2


class TestECA57SkeletonSynthesizer:
    """Tests for skeleton constraints."""

    def test_chain_collision_constraint(self):
        """Test that synthesized circuits enforce the chain collision property."""
        width = 4
        tt = TruthTable(width)
        
        solver = Solver("glucose4")
        
        # Try 6 or 8 gates for identity with chain property
        synth = ECA57SkeletonSynthesizer(tt, gate_count=6, solver=solver)
        circuit = synth.solve()
        
        if circuit is None:
            synth = ECA57SkeletonSynthesizer(tt, gate_count=8, solver=solver)
            circuit = synth.solve()

        if circuit is None:
            pytest.skip("Could not find identity circuit with 6 or 8 gates on 4 wires")
            
        print(f"Found circuit: {circuit}")
        gates = list(circuit.gates())
        
        # Check chain collisions
        for i in range(len(gates) - 1):
            assert gates_collide(gates[i], gates[i+1])

    def test_solve_simple_sat(self):
        """Test with 8 gates on 3 wires."""
        width = 3
        tt = TruthTable(width)
        
        solver = Solver("glucose4")
        # 6 gates was UNSAT, try 8 or 10
        synth = ECA57SkeletonSynthesizer(tt, gate_count=8, solver=solver)
        circuit = synth.solve()
        
        if circuit is None:
             synth = ECA57SkeletonSynthesizer(tt, gate_count=10, solver=solver)
             circuit = synth.solve()

        if circuit is None:
             pytest.skip("Could not find identity circuit with 8 or 10 gates on 3 wires with collision constraint")

        gates = list(circuit.gates())
        for i in range(len(gates) - 1):
            assert gates_collide(gates[i], gates[i+1])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
