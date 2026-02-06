"""Waksman permutation network implementation.

Waksman networks are rearrangeable 2x2-switch networks that realize any wire
permutation using O(n log n) switches. The topology is fixed; only switch
settings vary.

This module provides two approaches:
1. WaksmanNetwork: True Waksman network with O(n log n) complexity
2. SimpleSwapNetwork: Simpler O(n²) bubble-sort style approach for correctness

Key components:
    - ECA57SwapMacro: 6-gate ECA57 sequence that swaps two wires
    - SimpleSwapNetwork: Simple bubble-sort approach (guaranteed correct)
    - WaksmanNetwork: True Waksman network (work in progress)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from gates.eca57 import ECA57Circuit


@dataclass(frozen=True)
class WaksmanSwitch:
    """A 2x2 switch in the Waksman network."""

    top_wire: int
    bottom_wire: int
    stage: int
    position: int
    setting: int = 0  # 0 = straight, 1 = cross


class ECA57SwapMacro:
    """6-gate ECA57 swap implementation using an auxiliary wire.

    Swaps the values on two wires using a third auxiliary wire.
    The swap is implemented using the following 6-gate sequence derived
    from SAT synthesis to be minimal and correct.

    ECA57 gate: target ^= (ctrl1 OR NOT ctrl2)
    """

    # Pre-computed 6-gate swap sequence for wires (0, 1) using aux wire 2
    # Gate format: (target, ctrl1, ctrl2)
    # Found via SAT synthesis to be minimal and correct.
    _SWAP_GATES_CANONICAL: List[Tuple[int, int, int]] = [
        (0, 2, 1),
        (0, 1, 2),
        (1, 0, 2),
        (1, 2, 0),
        (0, 1, 2),
        (0, 2, 1),
    ]

    @classmethod
    def generate_swap(
        cls, wire_a: int, wire_b: int, aux: int, width: int
    ) -> ECA57Circuit:
        """Generate a swap circuit for two wires.

        Args:
            wire_a: First wire to swap.
            wire_b: Second wire to swap.
            aux: Auxiliary wire for the swap operation.
            width: Total circuit width.

        Returns:
            ECA57Circuit of exactly 6 gates that swaps wire_a and wire_b.
        """
        assert wire_a != wire_b != aux and wire_a != aux, "Wires must be distinct"
        assert 0 <= wire_a < width and 0 <= wire_b < width and 0 <= aux < width

        circuit = ECA57Circuit(width)
        wire_map = {0: wire_a, 1: wire_b, 2: aux}

        for target, ctrl1, ctrl2 in cls._SWAP_GATES_CANONICAL:
            circuit.add_gate(wire_map[target], wire_map[ctrl1], wire_map[ctrl2])

        return circuit

    @classmethod
    def verify_swap(
        cls, circuit: ECA57Circuit, wire_a: int, wire_b: int, aux: int
    ) -> bool:
        """Verify the circuit correctly swaps the two wires."""
        width = circuit.width()
        for i in range(2**width):
            input_state = [(i >> bit) & 1 for bit in range(width)]
            output_state = circuit.apply(input_state)

            if output_state[wire_a] != input_state[wire_b]:
                return False
            if output_state[wire_b] != input_state[wire_a]:
                return False
            if output_state[aux] != input_state[aux]:
                return False
            for w in range(width):
                if w not in (wire_a, wire_b):
                    if output_state[w] != input_state[w]:
                        return False
        return True

    @classmethod
    def find_swap_by_synthesis(cls, width: int = 3) -> Optional[List[Tuple[int, int, int]]]:
        """Find a minimal swap sequence using SAT synthesis."""
        from truth_table.truth_table import TruthTable
        from sat.solver import Solver
        from synthesizers.eca57_synthesizer import ECA57Synthesizer

        values = []
        for i in range(2**width):
            bits = [(i >> b) & 1 for b in range(width)]
            bits[0], bits[1] = bits[1], bits[0]
            output = sum(b << idx for idx, b in enumerate(bits))
            values.append(output)

        tt = TruthTable(width, values=values)

        for gate_count in range(1, 10):
            solver = Solver("glucose4")
            synth = ECA57Synthesizer(tt, gate_count=gate_count, solver=solver)
            circuit = synth.solve()
            if circuit is not None:
                return [g.to_tuple() for g in circuit.gates()]
        return None


class SimpleSwapNetwork:
    """Simple swap-based permutation network using bubble-sort approach.

    This is a simple O(n²) approach that decomposes any permutation into
    a sequence of adjacent transpositions. While not as efficient as
    true Waksman networks, it is guaranteed to be correct.

    Each swap uses the 6-gate ECA57 swap macro.

    Obfuscation mode: When enabled, identity slots (positions where no swap
    is needed) are filled with random identity circuits from the skeleton
    database, making all circuits have similar structure regardless of the
    actual permutation.
    """

    def __init__(self, n: int):
        """Initialize for n wires.

        Args:
            n: Number of wires (must be >= 2).
        """
        assert n >= 2, "Need at least 2 wires"
        self.n = n
        self._swaps: List[Tuple[int, int]] = []
        self._all_positions: List[Tuple[int, int, bool]] = []  # (wire_a, wire_b, is_swap)
        self._routed = False

    def route(self, permutation: List[int]) -> None:
        """Compute swap sequence to implement the given permutation.

        Uses a simple selection-sort style algorithm to find the minimal
        sequence of swaps (not necessarily adjacent).

        Args:
            permutation: Target permutation where perm[i] = j means
                        output i gets input j.
        """
        assert len(permutation) == self.n

        # Work with a copy
        current = list(range(self.n))
        self._swaps = []
        self._all_positions = []

        # For each output position, find the input that should go there
        for output_pos in range(self.n):
            # What input do we need at this position?
            needed_input = permutation[output_pos]

            # Where is that input currently?
            current_pos = current.index(needed_input)

            # If not already in place, swap it there
            if current_pos != output_pos:
                # Swap current[output_pos] and current[current_pos]
                self._swaps.append((output_pos, current_pos))
                self._all_positions.append((output_pos, current_pos, True))
                current[output_pos], current[current_pos] = current[current_pos], current[output_pos]
            else:
                # Record identity position for obfuscation
                # Use a "dummy" swap position involving this wire
                if output_pos < self.n - 1:
                    self._all_positions.append((output_pos, output_pos + 1, False))

        self._routed = True

    def to_eca57_circuit(
        self,
        aux_wire: Optional[int] = None,
        obfuscate: bool = False,
        identity_gate_count: Optional[int] = None,
        rng_seed: Optional[int] = None,
        min_identity_gates: int = 24,
        prefer_longer_identities: bool = True
    ) -> ECA57Circuit:
        """Convert to ECA57Circuit.

        Args:
            aux_wire: Auxiliary wire for swap macros. If None, uses wire=n.
            obfuscate: If True, fill identity slots with random identity circuits.
            identity_gate_count: Target gate count for identity fillers. If None,
                picks randomly from available circuits.
            rng_seed: Random seed for reproducible obfuscation.
            min_identity_gates: Minimum gate count for identity fillers (default 24).
            prefer_longer_identities: If True, weight toward longer identity circuits.

        Returns:
            ECA57Circuit implementing the permutation.
        """
        assert self._routed, "Must route first"

        if aux_wire is None:
            aux_wire = self.n
            width = self.n + 1
        else:
            width = max(self.n, aux_wire + 1)

        circuit = ECA57Circuit(width)

        if obfuscate:
            # Use identity filler for obfuscation
            from synthesizers.identity_filler import get_identity_filler
            import random

            filler = get_identity_filler()
            rng = random.Random(rng_seed) if rng_seed is not None else random.Random()

            for wire_a, wire_b, is_swap in self._all_positions:
                if is_swap:
                    # Actual swap - use 6-gate swap macro
                    swap_circuit = ECA57SwapMacro.generate_swap(wire_a, wire_b, aux_wire, width)
                    for gate in swap_circuit.gates():
                        circuit.add_gate(gate.target, gate.ctrl1, gate.ctrl2)
                else:
                    # Identity slot - insert random complex identity circuit
                    identity = filler.get_random_identity(
                        target_gates=identity_gate_count,
                        rng=rng,
                        min_gates=min_identity_gates,
                        prefer_longer=prefer_longer_identities
                    )
                    if identity:
                        remapped = filler.remap_identity(identity, wire_a, wire_b, aux_wire)
                        for t, c1, c2 in remapped:
                            circuit.add_gate(t, c1, c2)
        else:
            # Standard mode - only add swap gates
            for wire_a, wire_b in self._swaps:
                swap_circuit = ECA57SwapMacro.generate_swap(wire_a, wire_b, aux_wire, width)
                for gate in swap_circuit.gates():
                    circuit.add_gate(gate.target, gate.ctrl1, gate.ctrl2)

        return circuit

    def swap_count(self) -> int:
        """Number of swaps in the sequence."""
        return len(self._swaps)

    def identity_slot_count(self) -> int:
        """Number of identity slots (non-swap positions)."""
        return sum(1 for _, _, is_swap in self._all_positions if not is_swap)

    def total_position_count(self) -> int:
        """Total number of positions (swaps + identity slots)."""
        return len(self._all_positions)

    def gate_count_estimate(self, obfuscate: bool = False, identity_gates: int = 6) -> int:
        """Estimated gate count.

        Args:
            obfuscate: Whether obfuscation mode is enabled.
            identity_gates: Gate count for identity fillers.

        Returns:
            Estimated total gate count.
        """
        if obfuscate:
            return self.swap_count() * 6 + self.identity_slot_count() * identity_gates
        return self.swap_count() * 6


class WaksmanNetwork:
    """True Waksman permutation network.

    For n inputs (n must be power of 2):
    - Total switches: n*log2(n) - n + 1
    - Each switch: 0 gates (straight) or 6 gates (cross)

    Note: The routing algorithm is complex. For now, this class uses
    the SimpleSwapNetwork internally for correctness while the proper
    Waksman routing is being developed.

    Obfuscation mode: When enabled, identity slots (positions where no swap
    is needed) are filled with random identity circuits, making all circuits
    have similar structure regardless of the actual permutation.
    """

    def __init__(self, n: int):
        """Initialize Waksman network for n wires.

        Args:
            n: Number of wires (must be power of 2, minimum 2).
        """
        assert n >= 2, "Waksman network requires at least 2 wires"
        assert n & (n - 1) == 0, "n must be a power of 2"

        self.n = n
        self._simple_network = SimpleSwapNetwork(n)
        self._routed = False
        self.depth = 2 * int(math.log2(n)) - 1 if n > 2 else 1

    def route(self, permutation: List[int]) -> None:
        """Compute switch settings to implement the given permutation.

        Args:
            permutation: Target permutation where perm[i] = j means
                        output i gets input j.
        """
        assert len(permutation) == self.n

        # Use simple network for now (guaranteed correct)
        self._simple_network.route(permutation)
        self._routed = True

    def to_eca57_circuit(
        self,
        aux_wire: Optional[int] = None,
        obfuscate: bool = False,
        identity_gate_count: Optional[int] = None,
        rng_seed: Optional[int] = None,
        min_identity_gates: int = 24,
        prefer_longer_identities: bool = True
    ) -> ECA57Circuit:
        """Convert routed network to ECA57Circuit.

        Args:
            aux_wire: Auxiliary wire index for swap macros.
            obfuscate: If True, fill identity slots with random identity circuits.
            identity_gate_count: Target gate count for identity fillers.
            rng_seed: Random seed for reproducible obfuscation.
            min_identity_gates: Minimum gate count for identity fillers (default 24).
            prefer_longer_identities: If True, weight toward longer identity circuits.

        Returns:
            ECA57Circuit implementing the permutation.
        """
        assert self._routed, "Network must be routed before conversion"
        return self._simple_network.to_eca57_circuit(
            aux_wire, obfuscate, identity_gate_count, rng_seed,
            min_identity_gates, prefer_longer_identities
        )

    def gate_count_estimate(self, obfuscate: bool = False, identity_gates: int = 6) -> int:
        """Estimate gate count.

        Args:
            obfuscate: Whether obfuscation mode is enabled.
            identity_gates: Gate count for identity fillers.

        Returns:
            Estimated total gate count.
        """
        return self._simple_network.gate_count_estimate(obfuscate, identity_gates)

    def cross_switch_count(self) -> int:
        """Count of cross switches (swaps)."""
        return self._simple_network.swap_count()

    def identity_slot_count(self) -> int:
        """Count of identity slots (non-swap positions)."""
        return self._simple_network.identity_slot_count()

    def total_switch_count(self) -> int:
        """Total number of switches."""
        # For true Waksman: n*log2(n) - n + 1
        return self.n * int(math.log2(self.n)) - self.n + 1

    def get_switch_settings(self) -> List[int]:
        """Get list of switch settings (for compatibility)."""
        return [1] * self._simple_network.swap_count()


def synthesize_waksman(
    width: int,
    permutation: List[int],
    aux_wire: Optional[int] = None,
    obfuscate: bool = False,
    identity_gate_count: Optional[int] = None,
    rng_seed: Optional[int] = None,
    min_identity_gates: int = 24,
    prefer_longer_identities: bool = True
) -> ECA57Circuit:
    """Synthesize a wire permutation circuit using Waksman-style network.

    Args:
        width: Number of wires (must be power of 2).
        permutation: Target permutation where perm[i] = j means output i
                    gets input j.
        aux_wire: Auxiliary wire for swap macros. If None, uses wire=width.
        obfuscate: If True, fill identity slots with random identity circuits.
        identity_gate_count: Target gate count for identity fillers.
        rng_seed: Random seed for reproducible obfuscation.
        min_identity_gates: Minimum gate count for identity fillers (default 24).
        prefer_longer_identities: If True, weight toward longer identity circuits.

    Returns:
        ECA57Circuit implementing the permutation.
    """
    network = WaksmanNetwork(width)
    network.route(permutation)
    return network.to_eca57_circuit(
        aux_wire, obfuscate, identity_gate_count, rng_seed,
        min_identity_gates, prefer_longer_identities
    )


def synthesize_permutation(
    n: int,
    permutation: List[int],
    aux_wire: Optional[int] = None,
    obfuscate: bool = False,
    identity_gate_count: Optional[int] = None,
    rng_seed: Optional[int] = None,
    min_identity_gates: int = 24,
    prefer_longer_identities: bool = True
) -> ECA57Circuit:
    """Synthesize a wire permutation circuit (general n, not just powers of 2).

    Uses the simple swap network approach which works for any n >= 2.

    Args:
        n: Number of wires (must be >= 2).
        permutation: Target permutation where perm[i] = j means output i
                    gets input j.
        aux_wire: Auxiliary wire for swap macros. If None, uses wire=n.
        obfuscate: If True, fill identity slots with random identity circuits.
        identity_gate_count: Target gate count for identity fillers.
        rng_seed: Random seed for reproducible obfuscation.
        min_identity_gates: Minimum gate count for identity fillers (default 24).
        prefer_longer_identities: If True, weight toward longer identity circuits.

    Returns:
        ECA57Circuit implementing the permutation.
    """
    network = SimpleSwapNetwork(n)
    network.route(permutation)
    return network.to_eca57_circuit(
        aux_wire, obfuscate, identity_gate_count, rng_seed,
        min_identity_gates, prefer_longer_identities
    )
