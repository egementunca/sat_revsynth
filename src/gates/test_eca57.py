"""Tests for ECA57 gate and synthesizer."""
from __future__ import annotations

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from gates.eca57 import ECA57Gate, ECA57Circuit, all_eca57_gates
from gates.gate_set import GateSetType, ECA57GateSet


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


class TestECA57LimitedUnroll:
    """Tests for limited unroll functionality."""

    def test_limited_unroll_respects_max_total_circuits(self):
        """Test that max_total_circuits limit is respected."""
        circuit = ECA57Circuit(4)
        circuit.add_gate(0, 1, 2)
        circuit.add_gate(2, 1, 3)

        # Request at most 10 circuits
        limited = circuit.limited_unroll(max_total_circuits=10)

        assert len(limited) <= 10
        assert len(limited) > 0

    def test_limited_unroll_with_permutation_sampling(self):
        """Test that permutation sampling works."""
        circuit = ECA57Circuit(4)
        circuit.add_gate(0, 1, 2)

        # Sample only 5 permutations (4! = 24 total)
        limited = circuit.limited_unroll(
            max_swap_depth=1,
            max_swap_circuits=10,
            max_permutations=5,
            max_total_circuits=1000,
        )

        # Should generate circuits (exact count depends on dedup)
        assert len(limited) > 0
        assert len(limited) <= 1000

    def test_limited_unroll_without_rotations(self):
        """Test that include_rotations=False works."""
        circuit = ECA57Circuit(4)
        circuit.add_gate(0, 1, 2)
        circuit.add_gate(1, 0, 3)

        # Without rotations - should generate circuits
        without_rot = circuit.limited_unroll(
            max_swap_depth=1,
            max_swap_circuits=10,
            max_permutations=5,
            include_rotations=False,
            include_mirror=True,
        )

        # With rotations - should also generate circuits
        with_rot = circuit.limited_unroll(
            max_swap_depth=1,
            max_swap_circuits=10,
            max_permutations=5,
            include_rotations=True,
            include_mirror=True,
        )

        # Both should generate circuits (exact count depends on dedup and budget)
        assert len(without_rot) > 0
        assert len(with_rot) > 0
        # Note: with_rot may have fewer circuits if budget is hit earlier due to rotations

    def test_limited_unroll_without_mirror(self):
        """Test that include_mirror=False works."""
        circuit = ECA57Circuit(4)
        circuit.add_gate(0, 1, 2)

        # Without mirror
        without_mirror = circuit.limited_unroll(
            max_swap_depth=1,
            max_permutations=5,
            include_rotations=True,
            include_mirror=False,
        )

        # With mirror
        with_mirror = circuit.limited_unroll(
            max_swap_depth=1,
            max_permutations=5,
            include_rotations=True,
            include_mirror=True,
        )

        # With mirror should have more circuits (or equal if circuit is palindromic)
        assert len(without_mirror) <= len(with_mirror)

    def test_limited_unroll_smaller_than_full_unroll(self):
        """Test that limited_unroll generates fewer circuits than full unroll."""
        circuit = ECA57Circuit(3)  # Small circuit to make full unroll feasible
        circuit.add_gate(0, 1, 2)
        circuit.add_gate(1, 0, 2)

        # Get full unroll
        full = circuit.unroll()

        # Get limited unroll with tight constraints
        limited = circuit.limited_unroll(
            max_swap_depth=1,
            max_swap_circuits=5,
            max_permutations=3,
            max_total_circuits=20,
        )

        # Limited should be smaller or equal
        assert len(limited) <= len(full)

    def test_limited_unroll_on_skeleton_chain(self):
        """Test limited_unroll on skeleton chain returns bounded set."""
        # Create a skeleton chain
        circuit = ECA57Circuit(4)
        circuit.add_gate(0, 1, 2)
        circuit.add_gate(1, 0, 3)  # Collision
        circuit.add_gate(2, 1, 3)  # Collision

        # Limited unroll with small permutation sample
        limited = circuit.limited_unroll(
            max_swap_depth=5,  # Doesn't matter - no swaps exist
            max_permutations=6,  # Sample 6 permutations
            max_total_circuits=100,
        )

        # Should generate circuits from rotations × mirror × sampled perms
        # Skeleton has no swaps, so equivalents = rotations × mirror × perms
        # With 3 gates: ~3 rotations, 2 mirrors, 6 perms = ~36 circuits (with dedup)
        assert len(limited) > 0
        assert len(limited) <= 100


class TestECA57LimitedBFS:
    """Tests for limited swap space BFS."""

    def test_swap_space_bfs_limited_respects_max_circuits(self):
        """Test that max_circuits limit is respected."""
        # Create a circuit with some swappable gates
        circuit = ECA57Circuit(4)
        circuit.add_gate(0, 1, 2)
        circuit.add_gate(2, 1, 3)  # Doesn't collide with first gate
        circuit.add_gate(1, 0, 3)

        # Get limited results
        limited = circuit.swap_space_bfs_limited(max_depth=10, max_circuits=5)

        # Should have at most 5 circuits
        assert len(limited) <= 5
        assert len(limited) > 0

    def test_swap_space_bfs_limited_respects_max_depth(self):
        """Test that max_depth limit is respected."""
        # Create a circuit with swappable gates
        circuit = ECA57Circuit(4)
        circuit.add_gate(0, 1, 2)
        circuit.add_gate(2, 1, 3)

        # With depth=0, should only get the original circuit
        limited = circuit.swap_space_bfs_limited(max_depth=0, max_circuits=1000)
        assert len(limited) == 1
        assert limited[0] == circuit

        # With depth=1, should get more circuits
        limited = circuit.swap_space_bfs_limited(max_depth=1, max_circuits=1000)
        assert len(limited) >= 1

    def test_swap_space_bfs_limited_on_skeleton_chain(self):
        """Test that limited BFS on skeleton chain returns only the original."""
        # Create a skeleton chain where no gates are swappable
        circuit = ECA57Circuit(4)
        circuit.add_gate(0, 1, 2)
        circuit.add_gate(1, 0, 3)  # Uses wire 0 from previous gate (collision)
        circuit.add_gate(2, 1, 3)  # Uses wire 1 from previous gate (collision)

        # Verify it's a collision chain
        swappable_count = sum(1 for i in range(len(circuit) - 1) if circuit.gate_swappable(i))
        assert swappable_count == 0, "Should have no swappable gates"

        # Limited BFS should return only the original circuit
        limited = circuit.swap_space_bfs_limited(max_depth=10, max_circuits=1000)
        assert len(limited) == 1
        assert limited[0] == circuit

    def test_swap_space_bfs_limited_smaller_than_full(self):
        """Test that limited BFS returns fewer circuits than full BFS."""
        # Create a circuit with multiple swappable gates
        circuit = ECA57Circuit(5)
        circuit.add_gate(0, 1, 2)
        circuit.add_gate(3, 1, 4)  # Doesn't collide
        circuit.add_gate(2, 3, 4)  # Doesn't collide with middle gate

        # Get full swap space
        full = circuit.swap_space_bfs()

        # Get limited swap space with small limits
        limited = circuit.swap_space_bfs_limited(max_depth=2, max_circuits=10)

        # Limited should be smaller or equal
        assert len(limited) <= len(full)
        assert len(limited) <= 10


class TestECA57SkeletonCanonical:
    """Tests for skeleton chain canonical form methods."""

    def test_canonical_skeleton_equivalence_with_synthesizer(self):
        """Test that skeleton canonical form works correctly with synthesized chain."""
        try:
            from truth_table.truth_table import TruthTable
            from sat.solver import Solver
            from synthesizers.eca57_skeleton_synthesizer import ECA57SkeletonSynthesizer
        except ImportError:
            pytest.skip("Synthesizer dependencies not available")

        # Synthesize a small skeleton chain
        width = 4
        tt = TruthTable(width)
        solver = Solver("glucose4")

        # Try with 8 gates first
        synth = ECA57SkeletonSynthesizer(tt, gate_count=8, solver=solver)
        skeleton = synth.solve()

        if skeleton is None:
            # Try with 10 gates
            synth = ECA57SkeletonSynthesizer(tt, gate_count=10, solver=Solver("glucose4"))
            skeleton = synth.solve()

        if skeleton is None:
            pytest.skip("Could not synthesize skeleton chain")

        # Verify all adjacent gates collide (no swappable gates)
        for i in range(len(skeleton) - 1):
            assert not skeleton.gate_swappable(i), f"Skeleton should have no swappable gates at index {i}"

        # Test: rotation should be equivalent
        if len(skeleton) > 2:
            rotated = skeleton.rotate(2)
            assert skeleton.are_equivalent_skeleton(rotated), "Rotation should be equivalent"
            assert skeleton.canonical_skeleton_key() == rotated.canonical_skeleton_key()

        # Test: mirror should be equivalent
        mirrored = skeleton.reverse()
        assert skeleton.are_equivalent_skeleton(mirrored), "Mirror should be equivalent"
        assert skeleton.canonical_skeleton_key() == mirrored.canonical_skeleton_key()

        # Test: permutation should be equivalent
        perm = [1, 0, 2, 3]  # Swap wires 0 and 1
        permuted = skeleton.permute(perm)
        assert skeleton.are_equivalent_skeleton(permuted), "Permutation should be equivalent"
        assert skeleton.canonical_skeleton_key() == permuted.canonical_skeleton_key()

        # Test: canonical_skeleton should be consistent (calling twice gives same result)
        canonical1 = skeleton.canonical_skeleton()
        canonical2 = skeleton.canonical_skeleton()
        assert canonical1 == canonical2

    def test_canonical_skeleton_manual_chain(self):
        """Test canonical_skeleton with manually created collision chain."""
        # Manually create a simple collision chain
        # For a skeleton chain, each gate must collide with the next
        # Gate i+1 must use gate i's target as a control
        circuit = ECA57Circuit(4)

        # Build a chain: each gate's target is used by next gate
        # Gate 0: target=0, ctrl1=1, ctrl2=2
        # Gate 1: target=1, ctrl1=0, ctrl2=3  (uses wire 0 from gate 0)
        # Gate 2: target=2, ctrl1=1, ctrl2=3  (uses wire 1 from gate 1)
        # Gate 3: target=3, ctrl1=2, ctrl2=0  (uses wire 2 from gate 2)
        circuit.add_gate(0, 1, 2)
        circuit.add_gate(1, 0, 3)
        circuit.add_gate(2, 1, 3)
        circuit.add_gate(3, 2, 0)

        # Verify it's a collision chain
        for i in range(len(circuit) - 1):
            assert not circuit.gate_swappable(i), f"Should have collision at index {i}"

        # Test canonical_skeleton works
        canonical = circuit.canonical_skeleton()
        assert canonical is not None
        assert len(canonical) == len(circuit)

        # Test equivalence checking
        rotated = circuit.rotate(1)
        assert circuit.are_equivalent_skeleton(rotated)

    def test_canonical_skeleton_key_uniqueness(self):
        """Test that canonical_skeleton_key is unique for equivalence class."""
        # Create two different circuits
        circuit1 = ECA57Circuit(4)
        circuit1.add_gate(0, 1, 2)
        circuit1.add_gate(1, 0, 3)

        circuit2 = ECA57Circuit(4)
        circuit2.add_gate(2, 1, 3)
        circuit2.add_gate(3, 2, 0)

        # These are different circuits
        key1 = circuit1.canonical_skeleton_key()
        key2 = circuit2.canonical_skeleton_key()

        # They should have different canonical keys (unless they happen to be equivalent)
        # We mainly just test that the method runs without error
        assert isinstance(key1, tuple)
        assert isinstance(key2, tuple)
        assert len(key1) == len(circuit1)
        assert len(key2) == len(circuit2)

    def test_are_equivalent_skeleton_different_sizes(self):
        """Test that circuits of different sizes are not equivalent."""
        circuit1 = ECA57Circuit(4)
        circuit1.add_gate(0, 1, 2)

        circuit2 = ECA57Circuit(4)
        circuit2.add_gate(0, 1, 2)
        circuit2.add_gate(1, 0, 3)

        assert not circuit1.are_equivalent_skeleton(circuit2)

    def test_are_equivalent_skeleton_different_widths(self):
        """Test that circuits of different widths are not equivalent."""
        circuit1 = ECA57Circuit(3)
        circuit1.add_gate(0, 1, 2)

        circuit2 = ECA57Circuit(4)
        circuit2.add_gate(0, 1, 2)

        assert not circuit1.are_equivalent_skeleton(circuit2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
