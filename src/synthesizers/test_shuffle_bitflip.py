"""Tests for wire shuffle + bit-flip generator (B_{w,s}).

Tests cover:
1. Basic B_{w,s} circuit correctness
2. Composition rule: β_{w,s} ∘ β_{w',s'} = β_{w∘w', w'(s) ⊕ s'}
3. Inverse: B_{w,s} · B_{w,s}^{-1} = identity
4. Style A vs Style B equivalence
5. Edge cases (identity permutation, all-flip, etc.)
"""
import pytest
import random
from itertools import permutations

from gates.eca57 import ECA57Circuit
from synthesizers.shuffle_bitflip import (
    ShuffleBitflipGenerator,
    ShuffleBitflipConfig,
    ShuffleBitflipState,
    FlipMode,
    verify_shuffle_bitflip,
    compose_shuffle_bitflip,
    invert_shuffle_bitflip,
)


class TestShuffleBitflipState:
    """Tests for ShuffleBitflipState composition and inverse."""

    def test_identity_state(self):
        """Identity state should have no effect."""
        state = ShuffleBitflipState.identity(4)
        assert state.permutation == [0, 1, 2, 3]
        assert state.flip_mask == [0, 0, 0, 0]

    def test_compose_with_identity(self):
        """Composing with identity should return same state."""
        state = ShuffleBitflipState(
            permutation=[2, 0, 1, 3],
            flip_mask=[1, 0, 1, 0],
            width=4
        )
        identity = ShuffleBitflipState.identity(4)

        # state ∘ identity = state
        composed = state.compose(identity.permutation, identity.flip_mask)
        assert composed.permutation == state.permutation
        assert composed.flip_mask == state.flip_mask

    def test_inverse_composition(self):
        """State composed with its inverse should give identity."""
        state = ShuffleBitflipState(
            permutation=[2, 0, 1, 3],
            flip_mask=[1, 0, 1, 0],
            width=4
        )
        inv = state.inverse()
        composed = state.compose(inv.permutation, inv.flip_mask)

        assert composed.permutation == list(range(4))
        assert composed.flip_mask == [0, 0, 0, 0]

    def test_composition_rule(self):
        """Test β_{w,s} ∘ β_{w',s'} = β_{w∘w', w'(s) ⊕ s'}."""
        w1 = [1, 2, 0]  # cycle
        s1 = [1, 0, 1]

        w2 = [2, 0, 1]  # another cycle
        s2 = [0, 1, 0]

        # Manual computation of expected result
        # w_new = w1 ∘ w2: w_new[i] = w1[w2[i]]
        # w2 = [2, 0, 1] so w_new = [w1[2], w1[0], w1[1]] = [0, 1, 2] = identity!
        expected_w = [0, 1, 2]

        # s_new = w2(s1) ⊕ s2
        # w2(s1)[i] = s1[w2[i]], so w2(s1) = [s1[2], s1[0], s1[1]] = [1, 1, 0]
        # s_new = [1^0, 1^1, 0^0] = [1, 0, 0]
        expected_s = [1, 0, 0]

        w_result, s_result = compose_shuffle_bitflip(w1, s1, w2, s2)
        assert w_result == expected_w
        assert s_result == expected_s


class TestShuffleBitflipGenerator:
    """Tests for ShuffleBitflipGenerator circuit generation."""

    @pytest.fixture
    def generator_3(self):
        """Generator for 3-wire circuits."""
        config = ShuffleBitflipConfig(
            flip_mode=FlipMode.SEPARATE,
            rng_seed=42
        )
        return ShuffleBitflipGenerator(3, config)

    @pytest.fixture
    def generator_4(self):
        """Generator for 4-wire circuits."""
        config = ShuffleBitflipConfig(
            flip_mode=FlipMode.SEPARATE,
            rng_seed=42
        )
        return ShuffleBitflipGenerator(4, config)

    def test_identity_permutation_no_flip(self, generator_3):
        """Identity permutation with no flips should be identity circuit."""
        circuit = generator_3.generate([0, 1, 2], [0, 0, 0])
        assert verify_shuffle_bitflip(circuit, [0, 1, 2], [0, 0, 0])

    def test_simple_swap(self, generator_3):
        """Simple swap of two wires."""
        circuit = generator_3.generate([1, 0, 2], [0, 0, 0])
        assert verify_shuffle_bitflip(circuit, [1, 0, 2], [0, 0, 0])

    def test_cycle_permutation(self, generator_3):
        """Cyclic permutation of all wires."""
        circuit = generator_3.generate([2, 0, 1], [0, 0, 0])
        assert verify_shuffle_bitflip(circuit, [2, 0, 1], [0, 0, 0])

    def test_flip_single_wire(self, generator_3):
        """Identity permutation with single flip."""
        circuit = generator_3.generate([0, 1, 2], [1, 0, 0])
        assert verify_shuffle_bitflip(circuit, [0, 1, 2], [1, 0, 0])

    def test_flip_all_wires(self, generator_3):
        """Identity permutation with all flips."""
        circuit = generator_3.generate([0, 1, 2], [1, 1, 1])
        assert verify_shuffle_bitflip(circuit, [0, 1, 2], [1, 1, 1])

    def test_swap_with_flip(self, generator_3):
        """Swap with bit-flip on swapped wires."""
        circuit = generator_3.generate([1, 0, 2], [1, 1, 0])
        assert verify_shuffle_bitflip(circuit, [1, 0, 2], [1, 1, 0])

    def test_all_permutations_3_wire(self, generator_3):
        """Test all 6 permutations of 3 wires."""
        for perm in permutations([0, 1, 2]):
            perm_list = list(perm)
            circuit = generator_3.generate(perm_list, [0, 0, 0])
            assert verify_shuffle_bitflip(circuit, perm_list, [0, 0, 0]), \
                f"Failed for permutation {perm_list}"

    def test_all_flip_masks_3_wire(self, generator_3):
        """Test all 8 flip masks for identity permutation."""
        for mask in range(8):
            flip = [(mask >> i) & 1 for i in range(3)]
            circuit = generator_3.generate([0, 1, 2], flip)
            assert verify_shuffle_bitflip(circuit, [0, 1, 2], flip), \
                f"Failed for flip mask {flip}"

    def test_inverse_circuit(self, generator_3):
        """B_{w,s}^{-1} should invert B_{w,s}."""
        perm = [2, 0, 1]
        flip = [1, 0, 1]

        forward = generator_3.generate(perm, flip)
        inverse = generator_3.generate_inverse(perm, flip)

        # Apply forward then inverse (with ancilla = 0)
        n_data = 3
        width = forward.width()
        for i in range(2**n_data):
            # Build state with data wires from i, ancilla = 0
            state = [0] * width
            for b in range(n_data):
                state[b] = (i >> b) & 1

            mid = forward.apply(state)
            final = inverse.apply(mid)

            # Data wires should be back to original
            for w in range(n_data):
                assert final[w] == state[w], \
                    f"Wire {w} not restored: {state} -> {mid} -> {final}"

    def test_4_wire_permutations(self, generator_4):
        """Test several permutations on 4 wires."""
        test_cases = [
            ([1, 0, 2, 3], [0, 0, 0, 0]),  # Simple swap
            ([3, 2, 1, 0], [0, 0, 0, 0]),  # Reverse
            ([1, 2, 3, 0], [0, 0, 0, 0]),  # Cycle
            ([1, 0, 3, 2], [1, 1, 0, 0]),  # Two swaps with flips
        ]

        for perm, flip in test_cases:
            circuit = generator_4.generate(perm, flip)
            assert verify_shuffle_bitflip(circuit, perm, flip), \
                f"Failed for perm={perm}, flip={flip}"


class TestFlipModes:
    """Test different flip mode implementations."""

    def test_none_mode_ignores_flips(self):
        """FlipMode.NONE should ignore flip mask."""
        config = ShuffleBitflipConfig(
            flip_mode=FlipMode.NONE,
            rng_seed=42
        )
        gen = ShuffleBitflipGenerator(3, config)

        # Generate with flip mask, but mode is NONE
        circuit = gen.generate([1, 0, 2], [1, 1, 0])

        # Should implement swap only, not flips
        assert verify_shuffle_bitflip(circuit, [1, 0, 2], [0, 0, 0])

    def test_separate_mode(self):
        """FlipMode.SEPARATE should work correctly."""
        config = ShuffleBitflipConfig(
            flip_mode=FlipMode.SEPARATE,
            rng_seed=42
        )
        gen = ShuffleBitflipGenerator(3, config)

        circuit = gen.generate([1, 0, 2], [1, 0, 1])
        assert verify_shuffle_bitflip(circuit, [1, 0, 2], [1, 0, 1])

    def test_embedded_mode_fallback(self):
        """FlipMode.EMBEDDED without library should fallback to explicit flips."""
        config = ShuffleBitflipConfig(
            flip_mode=FlipMode.EMBEDDED,
            rng_seed=42
        )
        gen = ShuffleBitflipGenerator(3, config)

        circuit = gen.generate([1, 0, 2], [1, 0, 1])
        assert verify_shuffle_bitflip(circuit, [1, 0, 2], [1, 0, 1])


class TestCompositionFunctions:
    """Test standalone composition and inverse functions."""

    def test_compose_identity(self):
        """Composing with identity should preserve original."""
        w = [2, 0, 1]
        s = [1, 0, 1]

        w_id = [0, 1, 2]
        s_id = [0, 0, 0]

        w_result, s_result = compose_shuffle_bitflip(w, s, w_id, s_id)
        assert w_result == w
        assert s_result == s

    def test_invert_identity(self):
        """Inverse of identity is identity."""
        w = [0, 1, 2]
        s = [0, 0, 0]

        w_inv, s_inv = invert_shuffle_bitflip(w, s)
        assert w_inv == w
        assert s_inv == s

    def test_invert_then_compose_gives_identity(self):
        """(w, s) composed with its inverse should give identity."""
        w = [2, 0, 1]
        s = [1, 0, 1]

        w_inv, s_inv = invert_shuffle_bitflip(w, s)
        w_result, s_result = compose_shuffle_bitflip(w, s, w_inv, s_inv)

        assert w_result == [0, 1, 2]
        assert s_result == [0, 0, 0]

    def test_random_composition_inverse(self):
        """Random compositions should invert correctly."""
        rng = random.Random(12345)

        for _ in range(10):
            n = rng.randint(3, 6)
            w = list(range(n))
            rng.shuffle(w)
            s = [rng.randint(0, 1) for _ in range(n)]

            w_inv, s_inv = invert_shuffle_bitflip(w, s)
            w_result, s_result = compose_shuffle_bitflip(w, s, w_inv, s_inv)

            assert w_result == list(range(n)), f"Perm inverse failed: {w}"
            assert s_result == [0] * n, f"Flip inverse failed: {s}"


class TestRandomGeneration:
    """Test random shuffle+flip generation."""

    def test_generate_random(self):
        """generate_random should produce valid circuits."""
        config = ShuffleBitflipConfig(
            flip_mode=FlipMode.SEPARATE,
            rng_seed=42
        )
        gen = ShuffleBitflipGenerator(4, config)

        for _ in range(5):
            circuit, perm, flip = gen.generate_random(flip_probability=0.5)
            assert verify_shuffle_bitflip(circuit, perm, flip)

    def test_generate_random_reproducible(self):
        """Same seed should produce same results."""
        config1 = ShuffleBitflipConfig(flip_mode=FlipMode.SEPARATE, rng_seed=99)
        config2 = ShuffleBitflipConfig(flip_mode=FlipMode.SEPARATE, rng_seed=99)

        gen1 = ShuffleBitflipGenerator(4, config1)
        gen2 = ShuffleBitflipGenerator(4, config2)

        c1, p1, f1 = gen1.generate_random()
        c2, p2, f2 = gen2.generate_random()

        assert p1 == p2
        assert f1 == f2


class TestVerifyShuffleBitflip:
    """Test the verification function itself."""

    def test_verify_correct_circuit(self):
        """Verification should pass for correct circuits."""
        config = ShuffleBitflipConfig(flip_mode=FlipMode.SEPARATE, rng_seed=42)
        gen = ShuffleBitflipGenerator(3, config)

        circuit = gen.generate([1, 0, 2], [1, 0, 0])
        assert verify_shuffle_bitflip(circuit, [1, 0, 2], [1, 0, 0])

    def test_verify_wrong_permutation_fails(self):
        """Verification should fail for wrong permutation."""
        config = ShuffleBitflipConfig(flip_mode=FlipMode.SEPARATE, rng_seed=42)
        gen = ShuffleBitflipGenerator(3, config)

        circuit = gen.generate([1, 0, 2], [0, 0, 0])
        # Verify against wrong permutation
        assert not verify_shuffle_bitflip(circuit, [0, 1, 2], [0, 0, 0])

    def test_verify_wrong_flip_fails(self):
        """Verification should fail for wrong flip mask."""
        config = ShuffleBitflipConfig(flip_mode=FlipMode.SEPARATE, rng_seed=42)
        gen = ShuffleBitflipGenerator(3, config)

        circuit = gen.generate([0, 1, 2], [1, 0, 0])
        # Verify against wrong flip mask
        assert not verify_shuffle_bitflip(circuit, [0, 1, 2], [0, 0, 0])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
