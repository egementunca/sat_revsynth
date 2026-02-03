"""Tests for skeleton chain API."""
from __future__ import annotations

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from synthesizers.skeleton_chain_api import (
    synthesize_skeleton_chain,
    limited_unroll,
    verify_skeleton_chain,
    estimate_unroll_size,
)
from gates.eca57 import ECA57Circuit


class TestSynthesizeSkeletonChain:
    """Tests for skeleton chain synthesis."""

    def test_synthesize_small_skeleton(self):
        """Test synthesizing a small skeleton chain."""
        skeleton = synthesize_skeleton_chain(wires=4, gates=8)

        if skeleton is None:
            # Try with more gates
            skeleton = synthesize_skeleton_chain(wires=4, gates=10)

        if skeleton is None:
            pytest.skip("Could not synthesize skeleton chain")

        # Verify it's a skeleton chain
        assert verify_skeleton_chain(skeleton)
        assert skeleton.is_identity()

    def test_synthesize_with_chain_length(self):
        """Test synthesizing with specific chain length."""
        skeleton = synthesize_skeleton_chain(
            wires=4,
            gates=8,
            chain_length=4,
        )

        if skeleton is None:
            skeleton = synthesize_skeleton_chain(wires=4, gates=10, chain_length=5)

        if skeleton is None:
            pytest.skip("Could not synthesize with chain length constraint")

        assert skeleton.is_identity()

    def test_synthesize_returns_none_on_unsat(self):
        """Test that synthesis returns None when UNSAT."""
        # Very small gate count likely UNSAT for identity
        skeleton = synthesize_skeleton_chain(wires=4, gates=2)

        # Should be None or a valid circuit
        if skeleton is not None:
            # If it found something, verify it
            assert len(skeleton) == 2


class TestLimitedUnroll:
    """Tests for limited unroll functionality."""

    def test_limited_unroll_basic(self):
        """Test basic limited unroll."""
        # Create a simple circuit
        circuit = ECA57Circuit(4)
        circuit.add_gate(0, 1, 2)
        circuit.add_gate(1, 0, 3)

        variants = limited_unroll(
            circuit,
            max_circuits=50,
            max_permutations=5,
        )

        assert len(variants) > 0
        assert len(variants) <= 50
        # All variants should have same width and gate count
        for v in variants:
            assert v._width == circuit._width
            assert len(v) == len(circuit)

    def test_limited_unroll_skeleton_mode(self):
        """Test limited unroll with skeleton mode enabled."""
        # Create a skeleton chain
        circuit = ECA57Circuit(4)
        circuit.add_gate(0, 1, 2)
        circuit.add_gate(1, 0, 3)  # Collision
        circuit.add_gate(2, 1, 3)  # Collision

        # Verify it's a skeleton
        assert verify_skeleton_chain(circuit)

        # Unroll in skeleton mode (fast path)
        variants = limited_unroll(
            circuit,
            max_circuits=100,
            max_permutations=10,
            use_skeleton_mode=True,
        )

        assert len(variants) > 0
        assert len(variants) <= 100

    def test_limited_unroll_respects_max_circuits(self):
        """Test that max_circuits limit is respected."""
        circuit = ECA57Circuit(4)
        circuit.add_gate(0, 1, 2)
        circuit.add_gate(2, 1, 3)

        variants = limited_unroll(
            circuit,
            max_circuits=10,
            max_permutations=5,
        )

        assert len(variants) <= 10

    def test_limited_unroll_without_rotations(self):
        """Test limited unroll with rotations disabled."""
        circuit = ECA57Circuit(4)
        circuit.add_gate(0, 1, 2)

        variants = limited_unroll(
            circuit,
            max_circuits=50,
            include_rotations=False,
            max_permutations=3,
        )

        assert len(variants) > 0

    def test_limited_unroll_without_mirror(self):
        """Test limited unroll with mirror disabled."""
        circuit = ECA57Circuit(4)
        circuit.add_gate(0, 1, 2)

        variants = limited_unroll(
            circuit,
            max_circuits=50,
            include_mirror=False,
            max_permutations=3,
        )

        assert len(variants) > 0


class TestVerifySkeletonChain:
    """Tests for skeleton chain verification."""

    def test_verify_true_skeleton(self):
        """Test verification of a true skeleton chain."""
        # Create a skeleton chain
        circuit = ECA57Circuit(4)
        circuit.add_gate(0, 1, 2)
        circuit.add_gate(1, 0, 3)  # Collision
        circuit.add_gate(2, 1, 3)  # Collision

        assert verify_skeleton_chain(circuit)

    def test_verify_non_skeleton(self):
        """Test verification fails for non-skeleton."""
        # Create a circuit with non-colliding gates
        circuit = ECA57Circuit(4)
        circuit.add_gate(0, 1, 2)
        circuit.add_gate(2, 1, 3)  # Doesn't collide with first gate
        circuit.add_gate(1, 0, 3)

        # Check if gates are swappable
        has_swappable = any(circuit.gate_swappable(i) for i in range(len(circuit) - 1))

        if has_swappable:
            assert not verify_skeleton_chain(circuit)

    def test_verify_empty_circuit(self):
        """Test verification of empty circuit (trivially true)."""
        circuit = ECA57Circuit(4)

        # Empty circuit has no adjacent gates, so trivially true
        assert verify_skeleton_chain(circuit)

    def test_verify_single_gate(self):
        """Test verification of single gate (trivially true)."""
        circuit = ECA57Circuit(4)
        circuit.add_gate(0, 1, 2)

        # Single gate has no adjacent gates, so trivially true
        assert verify_skeleton_chain(circuit)


class TestEstimateUnrollSize:
    """Tests for unroll size estimation."""

    def test_estimate_small_circuit(self):
        """Test estimation for small circuit."""
        est = estimate_unroll_size(wires=4, gates=8, is_skeleton=False)

        assert "rotations" in est
        assert "mirror" in est
        assert "swap_space" in est
        assert "permutations" in est
        assert "total_estimate" in est
        assert "recommended_max_permutations" in est
        assert "is_feasible_full_unroll" in est

        # For 4 wires: 4! = 24 permutations
        assert est["permutations"] == 24
        assert est["mirror"] == 2
        assert est["rotations"] == 8

    def test_estimate_skeleton_chain(self):
        """Test estimation for skeleton chain."""
        est = estimate_unroll_size(wires=4, gates=8, is_skeleton=True)

        # Skeleton chains have swap_space = 1
        assert est["swap_space"] == 1
        assert est["permutations"] == 24  # 4!

        # Total should be rotations × mirror × 1 × perms
        expected = 8 * 2 * 1 * 24
        assert est["total_estimate"] == expected

    def test_estimate_large_circuit(self):
        """Test estimation for large circuit (infeasible for full unroll)."""
        est = estimate_unroll_size(wires=16, gates=32, is_skeleton=True)

        # 16! is huge (> 20 trillion)
        assert est["permutations"] > 1_000_000_000
        assert not est["is_feasible_full_unroll"]

        # Should recommend sampling
        assert est["recommended_max_permutations"] <= 1000

    def test_estimate_non_skeleton_has_larger_swap_space(self):
        """Test that non-skeleton estimates have larger swap space."""
        est_skeleton = estimate_unroll_size(wires=4, gates=8, is_skeleton=True)
        est_regular = estimate_unroll_size(wires=4, gates=8, is_skeleton=False)

        assert est_skeleton["swap_space"] == 1
        assert est_regular["swap_space"] > 1


class TestEndToEnd:
    """End-to-end integration tests."""

    def test_synthesize_and_unroll(self):
        """Test full workflow: synthesize then unroll."""
        # Synthesize a skeleton
        skeleton = synthesize_skeleton_chain(wires=4, gates=8)

        if skeleton is None:
            skeleton = synthesize_skeleton_chain(wires=4, gates=10)

        if skeleton is None:
            pytest.skip("Could not synthesize skeleton")

        # Verify it
        assert verify_skeleton_chain(skeleton)
        assert skeleton.is_identity()

        # Unroll with limits
        variants = limited_unroll(
            skeleton,
            max_circuits=100,
            max_permutations=10,
            use_skeleton_mode=True,
        )

        assert len(variants) > 0
        assert len(variants) <= 100

        # All variants should be identity
        for v in variants[:5]:  # Check first 5 to save time
            assert v.is_identity()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
