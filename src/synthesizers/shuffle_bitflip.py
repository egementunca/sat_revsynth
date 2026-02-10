"""Wire shuffle + bit-flip generator (B_{w,s}).

This module implements the wire shuffle with bit-flip integration as described
in the PLAN_wire_shuffle_bitflip.md document.

Key concepts:
    - w: permutation on wires 1..n
    - s: bit-flip mask in {0,1}^n
    - β_{w,s}(x_1,..,x_n) = (x_{w(1)} ⊕ s_1, ..., x_{w(n)} ⊕ s_n)
    - B_{w,s}: circuit implementing β_{w,s}

Flip modes:
    - Style A (separate): Build B_{w,0} then add X gates for s
    - Style B (embedded): Use swap-with-flip gadgets from library

Composition rule:
    β_{w,s} ∘ β_{w',s'} = β_{w∘w', w'(s) ⊕ s'}
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from gates.eca57 import ECA57Circuit, ECA57Gate
from synthesizers.waksman import (
    ECA57SwapMacro,
    ECA57SwapLibrary,
    ECA57SwapFlipLibrary,
    SimpleSwapNetwork,
    FlipMask,
    FLIP_MASKS,
)


class FlipMode(Enum):
    """Bit-flip integration mode."""
    NONE = "none"          # No bit-flips
    SEPARATE = "separate"  # Style A: explicit X layer after shuffle
    EMBEDDED = "embedded"  # Style B: swap-with-flip gadgets


@dataclass
class ShuffleBitflipState:
    """Cumulative state for shuffle + bit-flip composition.

    Tracks (w_total, s_total) through multiple applications to generate
    the correct inverse block.

    Attributes:
        permutation: Current cumulative permutation w_total.
        flip_mask: Current cumulative flip mask s_total.
        width: Number of wires.
    """
    permutation: List[int]
    flip_mask: List[int]
    width: int

    @classmethod
    def identity(cls, width: int) -> "ShuffleBitflipState":
        """Create identity state (no shuffle, no flips)."""
        return cls(
            permutation=list(range(width)),
            flip_mask=[0] * width,
            width=width
        )

    def compose(self, w_prime: List[int], s_prime: List[int]) -> "ShuffleBitflipState":
        """Compose with another (w', s') pair.

        Uses: β_{w,s} ∘ β_{w',s'} = β_{w∘w', w'(s) ⊕ s'}

        Args:
            w_prime: New permutation to apply.
            s_prime: New flip mask to apply.

        Returns:
            New ShuffleBitflipState with composed result.
        """
        # w_new = w ∘ w' (apply w' then w)
        w_new = [self.permutation[w_prime[i]] for i in range(self.width)]

        # s_new = w'(s) ⊕ s' where w'(s) permutes s by w'
        # w'(s)[i] = s[w'(i)]
        s_permuted = [self.flip_mask[w_prime[i]] for i in range(self.width)]
        s_new = [s_permuted[i] ^ s_prime[i] for i in range(self.width)]

        return ShuffleBitflipState(
            permutation=w_new,
            flip_mask=s_new,
            width=self.width
        )

    def inverse(self) -> "ShuffleBitflipState":
        """Compute inverse state.

        For β_{w,s}, the inverse is β_{w^{-1}, w^{-1}(s)}
        since β_{w,s} ∘ β_{w^{-1}, w^{-1}(s)} = identity.

        Returns:
            Inverse ShuffleBitflipState.
        """
        # w_inv[w[i]] = i
        w_inv = [0] * self.width
        for i in range(self.width):
            w_inv[self.permutation[i]] = i

        # s_inv = w^{-1}(s)
        s_inv = [self.flip_mask[w_inv[i]] for i in range(self.width)]

        return ShuffleBitflipState(
            permutation=w_inv,
            flip_mask=s_inv,
            width=self.width
        )


@dataclass
class ShuffleBitflipConfig:
    """Configuration for shuffle + bit-flip generator.

    Attributes:
        flip_mode: How to integrate bit-flips.
        aux_wire: Auxiliary wire for swap gadgets (None = use width).
        swap_library: Optional library of swap gadgets (Style A fallback).
        swap_flip_library: Optional library of swap-with-flip gadgets (Style B).
        rng_seed: Random seed for reproducibility.
        target_swap_gates: Target gate count for swap gadgets.
    """
    flip_mode: FlipMode = FlipMode.EMBEDDED
    aux_wire: Optional[int] = None
    swap_library: Optional[ECA57SwapLibrary] = None
    swap_flip_library: Optional[ECA57SwapFlipLibrary] = None
    rng_seed: Optional[int] = None
    target_swap_gates: Optional[int] = None


class ShuffleBitflipGenerator:
    """Generator for B_{w,s} circuits.

    Implements wire shuffle with bit-flip integration using either
    Style A (explicit flip layer) or Style B (swap-with-flip gadgets).
    """

    def __init__(self, width: int, config: Optional[ShuffleBitflipConfig] = None):
        """Initialize generator.

        Args:
            width: Number of wires.
            config: Configuration options.
        """
        self.width = width
        self.config = config or ShuffleBitflipConfig()
        self._rng = random.Random(self.config.rng_seed)

        # Determine auxiliary wire
        if self.config.aux_wire is not None:
            self._aux = self.config.aux_wire
            self._circuit_width = max(width, self.config.aux_wire + 1)
        else:
            self._aux = width
            self._circuit_width = width + 1

    def generate(
        self,
        permutation: List[int],
        flip_mask: Optional[List[int]] = None
    ) -> ECA57Circuit:
        """Generate B_{w,s} circuit.

        Args:
            permutation: Wire permutation w where perm[i] = j means
                        output wire i gets input from wire j.
            flip_mask: Bit-flip mask s (None = no flips).

        Returns:
            ECA57Circuit implementing β_{w,s}.
        """
        assert len(permutation) == self.width
        if flip_mask is None:
            flip_mask = [0] * self.width
        assert len(flip_mask) == self.width

        if self.config.flip_mode == FlipMode.NONE:
            return self._generate_shuffle_only(permutation)
        elif self.config.flip_mode == FlipMode.SEPARATE:
            return self._generate_style_a(permutation, flip_mask)
        else:  # EMBEDDED
            return self._generate_style_b(permutation, flip_mask)

    def generate_inverse(
        self,
        permutation: List[int],
        flip_mask: Optional[List[int]] = None
    ) -> ECA57Circuit:
        """Generate inverse B_{w,s}^{-1} circuit.

        Args:
            permutation: Wire permutation w.
            flip_mask: Bit-flip mask s.

        Returns:
            ECA57Circuit implementing β_{w,s}^{-1}.
        """
        state = ShuffleBitflipState(
            permutation=permutation,
            flip_mask=flip_mask or [0] * self.width,
            width=self.width
        )
        inv_state = state.inverse()
        return self.generate(inv_state.permutation, inv_state.flip_mask)

    def generate_random(
        self,
        flip_probability: float = 0.5
    ) -> Tuple[ECA57Circuit, List[int], List[int]]:
        """Generate random B_{w,s} circuit.

        Args:
            flip_probability: Probability of flipping each wire.

        Returns:
            Tuple of (circuit, permutation, flip_mask).
        """
        # Random permutation
        permutation = list(range(self.width))
        self._rng.shuffle(permutation)

        # Random flip mask
        flip_mask = [
            1 if self._rng.random() < flip_probability else 0
            for _ in range(self.width)
        ]

        circuit = self.generate(permutation, flip_mask)
        return circuit, permutation, flip_mask

    def _generate_shuffle_only(self, permutation: List[int]) -> ECA57Circuit:
        """Generate shuffle-only circuit (no bit-flips)."""
        network = SimpleSwapNetwork(self.width)
        network.route(permutation)
        return network.to_eca57_circuit(
            aux_wire=self._aux,
            swap_library=self.config.swap_library,
            swap_gate_count=self.config.target_swap_gates
        )

    def _generate_style_a(
        self,
        permutation: List[int],
        flip_mask: List[int]
    ) -> ECA57Circuit:
        """Generate Style A: shuffle followed by explicit X layer.

        First applies the permutation, then adds X gates for each bit
        that needs to be flipped.
        """
        # First: generate shuffle circuit
        circuit = self._generate_shuffle_only(permutation)

        # Then: add X gates for flips
        # ECA57 unconditional flip: target ^= (ctrl1 OR NOT ctrl2)
        # If ctrl2 = 0 (ancilla), then (ctrl1 OR NOT 0) = (ctrl1 OR 1) = 1, so target flips
        # We use aux wire as ctrl2 (inverted control) assuming it's 0
        for wire in range(self.width):
            if flip_mask[wire]:
                # ctrl2 = aux (assumed to be 0), ctrl1 = any other wire
                ctrl2 = self._aux if self._aux != wire else (
                    (wire + 1) % self._circuit_width
                )
                # ctrl1 must be different from both target and ctrl2
                ctrl1_candidates = [w for w in range(self._circuit_width)
                                   if w != wire and w != ctrl2]
                ctrl1 = ctrl1_candidates[0] if ctrl1_candidates else ctrl2
                circuit.add_gate(wire, ctrl1, ctrl2)

        return circuit

    def _generate_style_b(
        self,
        permutation: List[int],
        flip_mask: List[int]
    ) -> ECA57Circuit:
        """Generate Style B: swap-with-flip gadgets.

        Uses swap gadgets that have bit-flips embedded, distributing
        the flip mask across the swap operations.
        """
        circuit = ECA57Circuit(self._circuit_width)

        # Decompose permutation into swaps using selection-sort approach
        # For each swap, determine flip contribution
        current = list(range(self.width))
        remaining_flips = flip_mask.copy()

        for output_pos in range(self.width):
            needed_input = permutation[output_pos]
            current_pos = current.index(needed_input)

            if current_pos != output_pos:
                # Need to swap current[output_pos] and current[current_pos]
                wire_a = output_pos
                wire_b = current_pos

                # Determine flip mask for this swap
                # We can "consume" flips here if we have a suitable gadget
                swap_flip = self._select_swap_flip(
                    wire_a, wire_b,
                    remaining_flips[wire_a],
                    remaining_flips[wire_b]
                )

                # Generate swap-with-flip circuit
                swap_circuit = self._generate_swap_flip(
                    wire_a, wire_b, self._aux, swap_flip
                )

                # Add gates to main circuit
                for gate in swap_circuit.gates():
                    circuit.add_gate(gate.target, gate.ctrl1, gate.ctrl2)

                # Update remaining flips (consumed by this swap)
                if swap_flip[0]:
                    remaining_flips[wire_a] ^= 1
                if swap_flip[1]:
                    remaining_flips[wire_b] ^= 1

                # Update current permutation state
                current[output_pos], current[current_pos] = (
                    current[current_pos], current[output_pos]
                )

        # Any remaining flips need explicit X gates
        # Use aux as ctrl2 (assumed 0) for unconditional flip
        for wire in range(self.width):
            if remaining_flips[wire]:
                ctrl2 = self._aux if self._aux != wire else (
                    (wire + 1) % self._circuit_width
                )
                ctrl1_candidates = [w for w in range(self._circuit_width)
                                   if w != wire and w != ctrl2]
                ctrl1 = ctrl1_candidates[0] if ctrl1_candidates else ctrl2
                circuit.add_gate(wire, ctrl1, ctrl2)

        return circuit

    def _select_swap_flip(
        self,
        wire_a: int,
        wire_b: int,
        need_flip_a: int,
        need_flip_b: int
    ) -> FlipMask:
        """Select appropriate flip mask for a swap operation.

        Tries to consume pending flips if suitable gadgets are available.

        Args:
            wire_a: First swap wire.
            wire_b: Second swap wire.
            need_flip_a: Whether wire_a needs a flip (0 or 1).
            need_flip_b: Whether wire_b needs a flip (0 or 1).

        Returns:
            FlipMask to use for this swap.
        """
        desired: FlipMask = (need_flip_a, need_flip_b)

        # If we have swap-flip library, check if desired mask is available
        if self.config.swap_flip_library is not None:
            if self.config.swap_flip_library.has_flip_mask(desired):
                return desired

        # Fallback: no flip (will add explicit X later)
        return (0, 0)

    def _generate_swap_flip(
        self,
        wire_a: int,
        wire_b: int,
        aux: int,
        flip_mask: FlipMask
    ) -> ECA57Circuit:
        """Generate a single swap-with-flip gadget.

        Args:
            wire_a: First wire to swap.
            wire_b: Second wire to swap.
            aux: Auxiliary wire.
            flip_mask: (s0, s1) flip mask for this swap.

        Returns:
            ECA57Circuit implementing the swap-with-flip.
        """
        # Try swap-flip library first
        if self.config.swap_flip_library is not None:
            return self.config.swap_flip_library.random_swap_flip(
                wire_a, wire_b, aux, self._circuit_width,
                flip_mask, self._rng,
                target_gates=self.config.target_swap_gates
            )

        # Fallback to swap library + explicit flips
        if self.config.swap_library is not None:
            circuit = self.config.swap_library.random_swap(
                wire_a, wire_b, aux, self._circuit_width, self._rng,
                target_gates=self.config.target_swap_gates
            )
        else:
            circuit = ECA57SwapMacro.generate_swap(
                wire_a, wire_b, aux, self._circuit_width
            )

        # Add explicit flips if needed (unconditional flip using aux as ctrl2)
        s0, s1 = flip_mask
        if s0:
            ctrl2 = aux if aux != wire_a else wire_b
            ctrl1_candidates = [w for w in range(self._circuit_width)
                               if w != wire_a and w != ctrl2]
            ctrl1 = ctrl1_candidates[0] if ctrl1_candidates else ctrl2
            circuit.add_gate(wire_a, ctrl1, ctrl2)
        if s1:
            ctrl2 = aux if aux != wire_b else wire_a
            ctrl1_candidates = [w for w in range(self._circuit_width)
                               if w != wire_b and w != ctrl2]
            ctrl1 = ctrl1_candidates[0] if ctrl1_candidates else ctrl2
            circuit.add_gate(wire_b, ctrl1, ctrl2)

        return circuit


def verify_shuffle_bitflip(
    circuit: ECA57Circuit,
    permutation: List[int],
    flip_mask: List[int],
    data_wires: Optional[List[int]] = None,
    ancilla_zero: bool = True
) -> bool:
    """Verify a B_{w,s} circuit is correct.

    Args:
        circuit: Circuit to verify.
        permutation: Expected wire permutation.
        flip_mask: Expected bit-flip mask.
        data_wires: Which wires carry data (default: 0..len(perm)-1).
        ancilla_zero: If True, only test with ancilla wires initialized to 0.
                     This reflects the expected operational state where aux
                     wires are clean ancillas. Default: True.

    Returns:
        True if circuit implements β_{w,s} correctly.
    """
    width = circuit.width()
    n = len(permutation)

    if data_wires is None:
        data_wires = list(range(n))

    # Determine which wires are ancillas (non-data wires)
    ancilla_wires = [w for w in range(width) if w not in data_wires]

    # Only iterate over data wire combinations (ancillas fixed at 0)
    if ancilla_zero and ancilla_wires:
        num_data_inputs = 2 ** n
        for i in range(num_data_inputs):
            # Build input state: data wires from i, ancillas = 0
            input_state = [0] * width
            for bit_idx, data_wire in enumerate(data_wires):
                input_state[data_wire] = (i >> bit_idx) & 1

            output_state = circuit.apply(input_state)

            # Check data wires implement β_{w,s}
            for out_idx, data_wire in enumerate(data_wires):
                in_wire = permutation[out_idx]
                expected = input_state[data_wires[in_wire]] ^ flip_mask[out_idx]
                if output_state[data_wire] != expected:
                    return False

            # Check ancilla wires are preserved (should still be 0)
            for w in ancilla_wires:
                if output_state[w] != input_state[w]:
                    return False
    else:
        # Test all input combinations
        for i in range(2**width):
            input_state = [(i >> bit) & 1 for bit in range(width)]
            output_state = circuit.apply(input_state)

            # Check data wires implement β_{w,s}
            for out_idx, data_wire in enumerate(data_wires):
                in_wire = permutation[out_idx]
                expected = input_state[data_wires[in_wire]] ^ flip_mask[out_idx]
                if output_state[data_wire] != expected:
                    return False

            # Check non-data wires are preserved
            for w in range(width):
                if w not in data_wires:
                    if output_state[w] != input_state[w]:
                        return False

    return True


def compose_shuffle_bitflip(
    w1: List[int], s1: List[int],
    w2: List[int], s2: List[int]
) -> Tuple[List[int], List[int]]:
    """Compose two (w, s) pairs.

    Uses: β_{w1,s1} ∘ β_{w2,s2} = β_{w1∘w2, w2(s1) ⊕ s2}

    Args:
        w1, s1: First permutation and flip mask.
        w2, s2: Second permutation and flip mask.

    Returns:
        Tuple of (composed_permutation, composed_flip_mask).
    """
    n = len(w1)

    # w_new = w1 ∘ w2
    w_new = [w1[w2[i]] for i in range(n)]

    # s_new = w2(s1) ⊕ s2
    s_permuted = [s1[w2[i]] for i in range(n)]
    s_new = [s_permuted[i] ^ s2[i] for i in range(n)]

    return w_new, s_new


def invert_shuffle_bitflip(
    w: List[int], s: List[int]
) -> Tuple[List[int], List[int]]:
    """Compute inverse of (w, s) pair.

    The inverse of β_{w,s} is β_{w^{-1}, w^{-1}(s)}.

    Args:
        w: Permutation.
        s: Flip mask.

    Returns:
        Tuple of (inverse_permutation, inverse_flip_mask).
    """
    n = len(w)

    # w_inv[w[i]] = i
    w_inv = [0] * n
    for i in range(n):
        w_inv[w[i]] = i

    # s_inv = w^{-1}(s)
    s_inv = [s[w_inv[i]] for i in range(n)]

    return w_inv, s_inv
