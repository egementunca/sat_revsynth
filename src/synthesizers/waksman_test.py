"""Tests for Waksman permutation network implementation.

Tests cover:
- ECA57 swap macro correctness
- Simple swap network correctness
- Large circuit synthesis and verification
"""
from __future__ import annotations

import random
from itertools import permutations

import pytest

from gates.eca57 import ECA57Circuit
from synthesizers.waksman import (
    ECA57SwapMacro,
    SimpleSwapNetwork,
    WaksmanNetwork,
    synthesize_waksman,
    synthesize_permutation,
)


class TestECA57SwapMacro:
    """Tests for the 6-gate ECA57 swap macro."""

    def test_swap_correctness_width3(self):
        """Verify swap circuit correctly swaps wires 0 and 1 in 3-wire circuit."""
        circuit = ECA57SwapMacro.generate_swap(
            wire_a=0, wire_b=1, aux=2, width=3
        )

        for i in range(8):
            input_state = [(i >> b) & 1 for b in range(3)]
            output_state = circuit.apply(input_state)

            assert output_state[0] == input_state[1], f"Wire 0 should have wire 1's value for input {i}"
            assert output_state[1] == input_state[0], f"Wire 1 should have wire 0's value for input {i}"
            assert output_state[2] == input_state[2], f"Aux wire should be preserved for input {i}"

    def test_swap_gate_count(self):
        """Verify swap macro uses exactly 6 gates."""
        circuit = ECA57SwapMacro.generate_swap(
            wire_a=0, wire_b=1, aux=2, width=3
        )
        assert len(circuit) == 6, "Swap macro should have exactly 6 gates"

    def test_swap_different_wires(self):
        """Test swap with different wire combinations."""
        circuit = ECA57SwapMacro.generate_swap(
            wire_a=1, wire_b=2, aux=0, width=3
        )

        for i in range(8):
            input_state = [(i >> b) & 1 for b in range(3)]
            output_state = circuit.apply(input_state)

            assert output_state[1] == input_state[2]
            assert output_state[2] == input_state[1]
            assert output_state[0] == input_state[0]

    def test_swap_wider_circuit(self):
        """Test swap in a wider (4-wire) circuit."""
        circuit = ECA57SwapMacro.generate_swap(
            wire_a=0, wire_b=2, aux=3, width=4
        )

        for i in range(16):
            input_state = [(i >> b) & 1 for b in range(4)]
            output_state = circuit.apply(input_state)

            assert output_state[0] == input_state[2]
            assert output_state[2] == input_state[0]
            assert output_state[1] == input_state[1]
            assert output_state[3] == input_state[3]

    def test_verify_swap_method(self):
        """Test the verify_swap method."""
        circuit = ECA57SwapMacro.generate_swap(
            wire_a=0, wire_b=1, aux=2, width=3
        )
        assert ECA57SwapMacro.verify_swap(circuit, 0, 1, 2)

    def test_swap_reversibility(self):
        """Test that applying swap twice returns to original."""
        circuit = ECA57SwapMacro.generate_swap(
            wire_a=0, wire_b=1, aux=2, width=3
        )

        for i in range(8):
            input_state = [(i >> b) & 1 for b in range(3)]
            intermediate = circuit.apply(input_state)
            output_state = circuit.apply(intermediate)

            assert output_state == input_state


class TestSimpleSwapNetwork:
    """Tests for the simple swap network."""

    def _verify_permutation(self, circuit: ECA57Circuit, perm: list, n: int) -> bool:
        """Verify circuit implements the given wire permutation."""
        width = circuit.width()
        for i in range(2**n):
            input_state = [(i >> b) & 1 for b in range(width)]
            output_state = circuit.apply(input_state)
            for k in range(n):
                if output_state[k] != input_state[perm[k]]:
                    return False
        return True

    def test_identity_n2(self):
        """Test identity permutation for n=2."""
        network = SimpleSwapNetwork(2)
        network.route([0, 1])
        circuit = network.to_eca57_circuit()

        assert network.swap_count() == 0
        assert len(circuit) == 0
        assert self._verify_permutation(circuit, [0, 1], 2)

    def test_swap_n2(self):
        """Test swap permutation for n=2."""
        network = SimpleSwapNetwork(2)
        network.route([1, 0])
        circuit = network.to_eca57_circuit()

        assert network.swap_count() == 1
        assert len(circuit) == 6
        assert self._verify_permutation(circuit, [1, 0], 2)

    def test_identity_n4(self):
        """Test identity permutation for n=4."""
        network = SimpleSwapNetwork(4)
        network.route([0, 1, 2, 3])
        circuit = network.to_eca57_circuit()

        assert network.swap_count() == 0
        assert len(circuit) == 0
        assert self._verify_permutation(circuit, [0, 1, 2, 3], 4)

    def test_reverse_n4(self):
        """Test reverse permutation for n=4."""
        perm = [3, 2, 1, 0]
        network = SimpleSwapNetwork(4)
        network.route(perm)
        circuit = network.to_eca57_circuit()

        assert self._verify_permutation(circuit, perm, 4)

    @pytest.mark.parametrize("perm", list(permutations(range(4))))
    def test_all_perms_n4(self, perm):
        """Test all 24 permutations of n=4."""
        perm = list(perm)
        network = SimpleSwapNetwork(4)
        network.route(perm)
        circuit = network.to_eca57_circuit()
        assert self._verify_permutation(circuit, perm, 4), f"Failed for perm {perm}"


class TestWaksmanNetwork:
    """Tests for the Waksman network wrapper."""

    def _verify_permutation(self, circuit: ECA57Circuit, perm: list, n: int) -> bool:
        """Verify circuit implements the given wire permutation."""
        width = circuit.width()
        for i in range(2**n):
            input_state = [(i >> b) & 1 for b in range(width)]
            output_state = circuit.apply(input_state)
            for k in range(n):
                if output_state[k] != input_state[perm[k]]:
                    return False
        return True

    def test_network_n2(self):
        """Test n=2 network."""
        network = WaksmanNetwork(2)
        network.route([1, 0])
        circuit = network.to_eca57_circuit()
        assert self._verify_permutation(circuit, [1, 0], 2)

    def test_network_n4(self):
        """Test n=4 network."""
        network = WaksmanNetwork(4)
        network.route([3, 2, 1, 0])
        circuit = network.to_eca57_circuit()
        assert self._verify_permutation(circuit, [3, 2, 1, 0], 4)

    def test_network_n8(self):
        """Test n=8 network."""
        network = WaksmanNetwork(8)
        perm = [7, 6, 5, 4, 3, 2, 1, 0]
        network.route(perm)
        circuit = network.to_eca57_circuit()
        assert self._verify_permutation(circuit, perm, 8)

    def test_power_of_two_required(self):
        """Test that non-power-of-2 raises assertion."""
        with pytest.raises(AssertionError):
            WaksmanNetwork(3)
        with pytest.raises(AssertionError):
            WaksmanNetwork(5)


class TestSynthesizeWaksman:
    """Tests for the synthesize_waksman function."""

    def _verify_permutation(self, circuit: ECA57Circuit, perm: list, n: int) -> bool:
        """Verify circuit implements the given wire permutation."""
        width = circuit.width()
        for i in range(2**n):
            input_state = [(i >> b) & 1 for b in range(width)]
            output_state = circuit.apply(input_state)
            for k in range(n):
                if output_state[k] != input_state[perm[k]]:
                    return False
        return True

    def test_identity_n2(self):
        """Test identity permutation n=2."""
        circuit = synthesize_waksman(2, [0, 1])
        assert len(circuit) == 0
        assert self._verify_permutation(circuit, [0, 1], 2)

    def test_swap_n2(self):
        """Test swap permutation n=2."""
        circuit = synthesize_waksman(2, [1, 0])
        assert len(circuit) == 6
        assert self._verify_permutation(circuit, [1, 0], 2)

    @pytest.mark.parametrize("perm", list(permutations(range(4))))
    def test_all_perms_n4(self, perm):
        """Test all 24 permutations of n=4."""
        perm = list(perm)
        circuit = synthesize_waksman(4, perm)
        assert self._verify_permutation(circuit, perm, 4), f"Failed for perm {perm}"


class TestLargeCircuits:
    """Tests for larger circuit synthesis."""

    def _verify_permutation_sampled(self, circuit: ECA57Circuit, perm: list, n: int, samples: int = 100) -> bool:
        """Verify circuit with sampling for large n."""
        width = circuit.width()
        rng = random.Random(42)

        if n <= 8:
            test_inputs = list(range(2**n))
        else:
            # For large n, generate random inputs directly
            test_inputs = [rng.randint(0, 2**n - 1) for _ in range(samples)]

        for i in test_inputs:
            input_state = [(i >> b) & 1 for b in range(width)]
            output_state = circuit.apply(input_state)
            for k in range(n):
                if output_state[k] != input_state[perm[k]]:
                    return False
        return True

    def test_n8_identity(self):
        """Test n=8 identity permutation."""
        perm = list(range(8))
        circuit = synthesize_waksman(8, perm)
        assert len(circuit) == 0
        assert self._verify_permutation_sampled(circuit, perm, 8)

    def test_n8_reverse(self):
        """Test n=8 reverse permutation."""
        perm = list(range(7, -1, -1))
        circuit = synthesize_waksman(8, perm)
        assert self._verify_permutation_sampled(circuit, perm, 8)

    def test_n8_random(self):
        """Test n=8 random permutations."""
        random.seed(42)
        for _ in range(10):
            perm = list(range(8))
            random.shuffle(perm)
            circuit = synthesize_waksman(8, perm)
            assert self._verify_permutation_sampled(circuit, perm, 8), f"Failed for perm {perm}"

    def test_n16_reverse(self):
        """Test n=16 reverse permutation."""
        perm = list(range(15, -1, -1))
        circuit = synthesize_waksman(16, perm)
        assert self._verify_permutation_sampled(circuit, perm, 16)

    def test_n16_random(self):
        """Test n=16 random permutation."""
        random.seed(42)
        perm = list(range(16))
        random.shuffle(perm)
        circuit = synthesize_waksman(16, perm)
        assert self._verify_permutation_sampled(circuit, perm, 16)

    def test_n32_random(self):
        """Test n=32 random permutation."""
        random.seed(42)
        perm = list(range(32))
        random.shuffle(perm)
        circuit = synthesize_waksman(32, perm)
        assert self._verify_permutation_sampled(circuit, perm, 32, samples=200)

    def test_n64_random(self):
        """Test n=64 random permutation."""
        random.seed(42)
        perm = list(range(64))
        random.shuffle(perm)
        circuit = synthesize_waksman(64, perm)
        assert self._verify_permutation_sampled(circuit, perm, 64, samples=200)


class TestSynthesizePermutation:
    """Tests for the general synthesize_permutation function."""

    def _verify_permutation(self, circuit: ECA57Circuit, perm: list, n: int) -> bool:
        """Verify circuit implements the given wire permutation."""
        width = circuit.width()
        for i in range(2**n):
            input_state = [(i >> b) & 1 for b in range(width)]
            output_state = circuit.apply(input_state)
            for k in range(n):
                if output_state[k] != input_state[perm[k]]:
                    return False
        return True

    def test_non_power_of_two(self):
        """Test that synthesize_permutation works for non-power-of-2."""
        # n=3
        perm = [2, 0, 1]
        circuit = synthesize_permutation(3, perm)
        assert self._verify_permutation(circuit, perm, 3)

        # n=5
        perm = [4, 3, 2, 1, 0]
        circuit = synthesize_permutation(5, perm)
        assert self._verify_permutation(circuit, perm, 5)

        # n=6
        perm = [5, 4, 3, 2, 1, 0]
        circuit = synthesize_permutation(6, perm)
        assert self._verify_permutation(circuit, perm, 6)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
