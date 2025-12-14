"""Tests for ECA57 gate and synthesizer."""
from __future__ import annotations

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from gates.eca57 import ECA57Gate, ECA57Circuit, all_eca57_gates
from gates.gate_set import GateSetType, ECA57GateSet, get_gate_set


class TestECA57Gate:
    """Tests for ECA57 gate primitive."""
    
    def test_gate_creation(self):
        """Test basic gate creation."""
        gate = ECA57Gate(target=0, ctrl1=1, ctrl2=2)
        assert gate.target == 0
        assert gate.ctrl1 == 1
        assert gate.ctrl2 == 2
    
    def test_gate_same_wire_error(self):
        """Test that same wire for different roles raises error."""
        with pytest.raises(AssertionError):
            ECA57Gate(target=0, ctrl1=0, ctrl2=1)
        with pytest.raises(AssertionError):
            ECA57Gate(target=0, ctrl1=1, ctrl2=0)
        with pytest.raises(AssertionError):
            ECA57Gate(target=0, ctrl1=1, ctrl2=1)
    
    def test_gate_apply_truth_table(self):
        """Test gate application matches expected truth table.
        
        For target=0, ctrl1=1, ctrl2=2:
        target ^= (ctrl1 OR NOT ctrl2)
        
        c1 c2 | c1 OR NOT c2 | result if target=0
        0  0  | 1            | flip
        0  1  | 0            | no flip
        1  0  | 1            | flip
        1  1  | 1            | flip
        """
        gate = ECA57Gate(target=0, ctrl1=1, ctrl2=2)
        
        # Test all 8 inputs for 3-wire circuit
        # Format: [w0, w1, w2] = [target, ctrl1, ctrl2]
        test_cases = [
            # input state -> expected output
            ([0, 0, 0], [1, 0, 0]),  # c1=0, c2=0, flip
            ([0, 0, 1], [0, 0, 1]),  # c1=0, c2=1, no flip
            ([0, 1, 0], [1, 1, 0]),  # c1=1, c2=0, flip
            ([0, 1, 1], [1, 1, 1]),  # c1=1, c2=1, flip
            ([1, 0, 0], [0, 0, 0]),  # target=1, flip -> 0
            ([1, 0, 1], [1, 0, 1]),  # no flip
            ([1, 1, 0], [0, 1, 0]),  # flip -> 0
            ([1, 1, 1], [0, 1, 1]),  # flip -> 0
        ]
        
        for input_state, expected in test_cases:
            result = gate.apply(input_state)
            assert result == expected, f"Input {input_state}: expected {expected}, got {result}"
    
    def test_gate_involutory(self):
        """Test that applying gate twice returns to original state."""
        gate = ECA57Gate(target=0, ctrl1=1, ctrl2=2)
        
        for i in range(8):
            state = [(i >> b) & 1 for b in range(3)]
            after_one = gate.apply(state)
            after_two = gate.apply(after_one)
            assert after_two == state


class TestECA57Circuit:
    """Tests for ECA57 circuit class."""
    
    def test_empty_circuit_is_identity(self):
        """Test that empty circuit is identity."""
        circ = ECA57Circuit(3)
        assert circ.is_identity()
    
    def test_single_gate_not_identity(self):
        """Test that single gate is not identity (in general)."""
        circ = ECA57Circuit(3)
        circ.add_gate(0, 1, 2)
        assert not circ.is_identity()
    
    def test_double_gate_is_identity(self):
        """Test that applying same gate twice is identity."""
        circ = ECA57Circuit(3)
        circ.add_gate(0, 1, 2)
        circ.add_gate(0, 1, 2)
        assert circ.is_identity()
    
    def test_circuit_len(self):
        """Test circuit length."""
        circ = ECA57Circuit(3)
        assert len(circ) == 0
        circ.add_gate(0, 1, 2)
        assert len(circ) == 1
        circ.add_gate(1, 0, 2)
        assert len(circ) == 2
    
    def test_all_eca57_gates_count(self):
        """Test that all_eca57_gates returns correct count."""
        gates_3 = all_eca57_gates(3)
        assert len(gates_3) == 3 * 2 * 1  # 6
        
        gates_4 = all_eca57_gates(4)
        assert len(gates_4) == 4 * 3 * 2  # 24


class TestECA57GateSet:
    """Tests for ECA57 gate set abstraction."""
    
    def test_gate_set_type(self):
        """Test gate set type."""
        gs = ECA57GateSet()
        assert gs.gate_type == GateSetType.ECA57
    
    def test_num_gates(self):
        """Test gate count calculation."""
        gs = ECA57GateSet()
        assert gs.num_gates(3) == 6
        assert gs.num_gates(4) == 24
        assert gs.num_gates(5) == 60
    
    def test_enumerate_gates(self):
        """Test gate enumeration."""
        gs = ECA57GateSet()
        gates = gs.enumerate_gates(3)
        assert len(gates) == 6
        
        # Check all gates are unique
        assert len(set(gates)) == len(gates)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
