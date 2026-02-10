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
from typing import Dict, List, Optional, Tuple

import json
import random

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


class ECA57SwapLibrary:
    """Library of swap gadgets (3-wire circuits) loaded from JSON."""

    def __init__(self, circuits: List[List[Tuple[int, int, int]]]):
        self._circuits = circuits

    @classmethod
    def load_json(cls, path: str) -> "ECA57SwapLibrary":
        with open(path, "r") as f:
            payload = json.load(f)

        circuits: List[List[Tuple[int, int, int]]] = []
        if isinstance(payload, dict):
            raw = payload.get("circuits", [])
        else:
            raw = payload

        for item in raw:
            if isinstance(item, dict):
                gates = item.get("gates", [])
            else:
                gates = item
            circuits.append([tuple(g) for g in gates])

        return cls(circuits)

    def random_swap(
        self,
        wire_a: int,
        wire_b: int,
        aux: int,
        width: int,
        rng: random.Random,
        target_gates: Optional[int] = None
    ) -> ECA57Circuit:
        """Pick a random swap gadget and remap wires."""
        if not self._circuits:
            return ECA57SwapMacro.generate_swap(wire_a, wire_b, aux, width)

        candidates = self._circuits
        if target_gates is not None:
            filtered = [c for c in self._circuits if len(c) == target_gates]
            if filtered:
                candidates = filtered

        gates = rng.choice(candidates)
        circuit = ECA57Circuit(width)
        wire_map = {0: wire_a, 1: wire_b, 2: aux}
        for t, c1, c2 in gates:
            circuit.add_gate(wire_map[t], wire_map[c1], wire_map[c2])
        return circuit

    def circuit_count(self) -> int:
        return len(self._circuits)


# Flip mask type alias
FlipMask = Tuple[int, int]

# Predefined flip masks
FLIP_MASKS: Dict[str, FlipMask] = {
    "no_flip": (0, 0),
    "flip_wire0": (1, 0),
    "flip_wire1": (0, 1),
    "flip_both": (1, 1),
}


class ECA57SwapFlipLibrary:
    """Library of swap-with-flip gadgets (3-wire circuits) loaded from JSON.

    Each gadget performs swap(wire0, wire1) with optional bit-flips on the
    swapped outputs. This supports Style B integration for wire shuffle +
    bit-flip obfuscation.

    Flip masks:
        (0, 0): swap only, no flips
        (1, 0): swap + flip output wire 0
        (0, 1): swap + flip output wire 1
        (1, 1): swap + flip both output wires
    """

    def __init__(
        self,
        circuits_by_flip: Dict[FlipMask, List[List[Tuple[int, int, int]]]]
    ):
        """Initialize from circuits organized by flip mask.

        Args:
            circuits_by_flip: Dict mapping flip mask to list of gate sequences.
        """
        self._circuits_by_flip = circuits_by_flip

    @classmethod
    def load_json(cls, path: str) -> "ECA57SwapFlipLibrary":
        """Load swap-with-flip gadget library from JSON.

        Expected JSON format:
        {
            "circuits": [
                {
                    "gates": [[t, c1, c2], ...],
                    "flip_mask": [s0, s1]
                },
                ...
            ]
        }

        Args:
            path: Path to JSON file.

        Returns:
            ECA57SwapFlipLibrary instance.
        """
        with open(path, "r") as f:
            payload = json.load(f)

        circuits_by_flip: Dict[FlipMask, List[List[Tuple[int, int, int]]]] = {
            (0, 0): [],
            (1, 0): [],
            (0, 1): [],
            (1, 1): [],
        }

        raw = payload.get("circuits", []) if isinstance(payload, dict) else payload

        for item in raw:
            if isinstance(item, dict):
                gates = [tuple(g) for g in item.get("gates", [])]
                flip_list = item.get("flip_mask", [0, 0])
                flip_mask = (flip_list[0], flip_list[1])
            else:
                # Fallback: assume no-flip swap
                gates = [tuple(g) for g in item]
                flip_mask = (0, 0)

            if flip_mask in circuits_by_flip:
                circuits_by_flip[flip_mask].append(gates)

        return cls(circuits_by_flip)

    def has_flip_mask(self, flip_mask: FlipMask) -> bool:
        """Check if library has gadgets for the given flip mask."""
        return len(self._circuits_by_flip.get(flip_mask, [])) > 0

    def circuit_count(self, flip_mask: Optional[FlipMask] = None) -> int:
        """Count circuits, optionally filtered by flip mask."""
        if flip_mask is not None:
            return len(self._circuits_by_flip.get(flip_mask, []))
        return sum(len(v) for v in self._circuits_by_flip.values())

    def random_swap_flip(
        self,
        wire_a: int,
        wire_b: int,
        aux: int,
        width: int,
        flip_mask: FlipMask,
        rng: random.Random,
        target_gates: Optional[int] = None
    ) -> ECA57Circuit:
        """Pick a random swap-with-flip gadget and remap wires.

        Args:
            wire_a: First wire to swap.
            wire_b: Second wire to swap.
            aux: Auxiliary wire.
            width: Total circuit width.
            flip_mask: (s0, s1) indicating which outputs to flip.
            rng: Random number generator.
            target_gates: Optional target gate count.

        Returns:
            ECA57Circuit implementing swap-with-flip.
        """
        candidates = self._circuits_by_flip.get(flip_mask, [])

        if not candidates:
            # Fallback: use canonical swap and add X gates for flips
            return self._fallback_swap_flip(wire_a, wire_b, aux, width, flip_mask)

        if target_gates is not None:
            filtered = [c for c in candidates if len(c) == target_gates]
            if filtered:
                candidates = filtered

        gates = rng.choice(candidates)
        circuit = ECA57Circuit(width)
        wire_map = {0: wire_a, 1: wire_b, 2: aux}

        for t, c1, c2 in gates:
            circuit.add_gate(wire_map[t], wire_map[c1], wire_map[c2])

        return circuit

    def _fallback_swap_flip(
        self,
        wire_a: int,
        wire_b: int,
        aux: int,
        width: int,
        flip_mask: FlipMask
    ) -> ECA57Circuit:
        """Fallback: use canonical swap followed by X gates for flips.

        This is Style A (explicit flip layer) used when Style B gadgets
        are not available.
        """
        # First, do the swap
        circuit = ECA57SwapMacro.generate_swap(wire_a, wire_b, aux, width)

        # Then add X gates for flips
        # ECA57 unconditional flip: target ^= (ctrl1 OR NOT ctrl2)
        # If ctrl2 = 0 (ancilla), then (ctrl1 OR NOT 0) = (ctrl1 OR 1) = 1
        # Use aux as ctrl2 (assumed 0), and another distinct wire as ctrl1
        s0, s1 = flip_mask

        if s0:
            # Flip wire_a: use aux as ctrl2 (inverted control, assumed 0)
            ctrl2 = aux if aux != wire_a else wire_b
            ctrl1_candidates = [w for w in range(width) if w != wire_a and w != ctrl2]
            ctrl1 = ctrl1_candidates[0] if ctrl1_candidates else ctrl2
            circuit.add_gate(wire_a, ctrl1, ctrl2)

        if s1:
            # Flip wire_b: use aux as ctrl2 (inverted control, assumed 0)
            ctrl2 = aux if aux != wire_b else wire_a
            ctrl1_candidates = [w for w in range(width) if w != wire_b and w != ctrl2]
            ctrl1 = ctrl1_candidates[0] if ctrl1_candidates else ctrl2
            circuit.add_gate(wire_b, ctrl1, ctrl2)

        return circuit

    def get_flip_masks(self) -> List[FlipMask]:
        """Return list of available flip masks with gadgets."""
        return [fm for fm in self._circuits_by_flip if self._circuits_by_flip[fm]]


@dataclass(frozen=True)
class SwitchOp:
    wire_a: int
    wire_b: int
    setting: int  # 0 = straight, 1 = cross (swap)


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

    def __init__(self, n: int, randomize: bool = False, rng_seed: Optional[int] = None):
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
        prefer_longer_identities: bool = True,
        swap_library: Optional[ECA57SwapLibrary] = None,
        swap_gate_count: Optional[int] = None
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
        rng = random.Random(rng_seed) if rng_seed is not None else random.Random()

        if obfuscate:
            # Use identity filler for obfuscation
            from synthesizers.identity_filler import get_identity_filler

            filler = get_identity_filler()

            for wire_a, wire_b, is_swap in self._all_positions:
                if is_swap:
                    # Actual swap - use 6-gate swap macro
                    if swap_library is not None:
                        swap_circuit = swap_library.random_swap(
                            wire_a, wire_b, aux_wire, width, rng, target_gates=swap_gate_count
                        )
                    else:
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
                if swap_library is not None:
                    swap_circuit = swap_library.random_swap(
                        wire_a, wire_b, aux_wire, width, rng, target_gates=swap_gate_count
                    )
                else:
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

    Note: The routing algorithm is complex. For now, this class uses the
    SimpleSwapNetwork internally for correctness while minimal Waksman
    routing remains future work.

    Obfuscation mode: When enabled, identity slots (positions where no swap
    is needed) are filled with random identity circuits, making all circuits
    have similar structure regardless of the actual permutation.
    """

    def __init__(self, n: int, randomize: bool = False, rng_seed: Optional[int] = None):
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
        prefer_longer_identities: bool = True,
        swap_library: Optional[ECA57SwapLibrary] = None,
        swap_gate_count: Optional[int] = None
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
            min_identity_gates, prefer_longer_identities, swap_library, swap_gate_count
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


class BenesNetwork:
    """Beneš (fixed-topology) permutation network with optional randomized routing."""

    def __init__(self, n: int, randomize: bool = False, rng_seed: Optional[int] = None):
        assert n >= 2, "Beneš network requires at least 2 wires"
        assert n & (n - 1) == 0, "n must be a power of 2"
        self.n = n
        self._randomize = randomize
        self._rng = random.Random(rng_seed) if rng_seed is not None else random.Random()
        self._stage_pairs: List[List[Tuple[int, int]]] = self._build_stage_pairs()
        self._stage_settings: List[List[int]] = []
        self._routed = False

    def route(self, permutation: List[int]) -> None:
        assert len(permutation) == self.n
        self._stage_settings = self._route_settings(permutation)
        self._routed = True

    @staticmethod
    def _build_stage_pairs_for(n: int) -> List[List[Tuple[int, int]]]:
        k = int(math.log2(n))
        stages: List[List[Tuple[int, int]]] = []
        for s in range(2 * k - 1):
            bit = s if s < k else (2 * k - 2 - s)
            pairs: List[Tuple[int, int]] = []
            for i in range(n):
                if (i >> bit) & 1 == 0:
                    j = i ^ (1 << bit)
                    pairs.append((i, j))
            stages.append(pairs)
        return stages

    def _build_stage_pairs(self) -> List[List[Tuple[int, int]]]:
        return self._build_stage_pairs_for(self.n)

    def _route_settings(self, permutation: List[int]) -> List[List[int]]:
        n = len(permutation)
        if n == 2:
            return [[0]] if permutation == [0, 1] else [[1]]

        # Convert output->input into input->output mapping
        perm_in_to_out = [0] * n
        for out_idx, in_idx in enumerate(permutation):
            perm_in_to_out[in_idx] = out_idx

        input_pairs = [[2 * i, 2 * i + 1] for i in range(n // 2)]
        output_pairs: List[List[int]] = [[] for _ in range(n // 2)]
        for x in range(n):
            output_pairs[perm_in_to_out[x] // 2].append(x)
        for edges in output_pairs:
            if len(edges) != 2:
                raise ValueError("Invalid output pair edges (not a permutation?)")

        colors: List[Optional[int]] = [None] * n  # 0 = upper, 1 = lower

        def other_in_pair(pair: List[int], edge: int) -> int:
            return pair[0] if pair[1] == edge else pair[1]

        for start in range(n):
            if colors[start] is not None:
                continue
            color = self._rng.randint(0, 1) if self._randomize else 0
            current = start
            while True:
                colors[current] = color
                out_pair = output_pairs[perm_in_to_out[current] // 2]
                other = other_in_pair(out_pair, current)
                if colors[other] is None:
                    colors[other] = 1 - color
                in_pair = input_pairs[other // 2]
                current = other_in_pair(in_pair, other)
                if current == start or colors[current] is not None:
                    break

        # Stage 0 settings
        stage0 = [0] * (n // 2)
        for i in range(n // 2):
            a = 2 * i
            stage0[i] = 0 if colors[a] == 0 else 1

        # Last stage settings
        input_for_output = [0] * n
        for x in range(n):
            input_for_output[perm_in_to_out[x]] = x
        stage_last = [0] * (n // 2)
        for o in range(n // 2):
            y0 = 2 * o
            stage_last[o] = 0 if colors[input_for_output[y0]] == 0 else 1

        # Upper/lower subnetworks
        upper_perm = [0] * (n // 2)
        lower_perm = [0] * (n // 2)
        for i in range(n // 2):
            a, b = input_pairs[i]
            if colors[a] == 0:
                upper_in = a
                lower_in = b
            else:
                upper_in = b
                lower_in = a
            upper_perm[i] = perm_in_to_out[upper_in] // 2
            lower_perm[i] = perm_in_to_out[lower_in] // 2

        upper_stages = self._route_settings(upper_perm)
        lower_stages = self._route_settings(lower_perm)
        if len(upper_stages) != len(lower_stages):
            raise ValueError("Upper/lower stage length mismatch")

        def stage_bit(stage_idx: int, size: int) -> int:
            k = int(math.log2(size))
            return stage_idx if stage_idx < k else (2 * k - 2 - stage_idx)

        def remove_bit(x: int, bit: int) -> int:
            lower = x & ((1 << bit) - 1)
            upper = x >> (bit + 1)
            return lower | (upper << bit)

        stage_pairs = self._build_stage_pairs_for(n)
        middle: List[List[int]] = []
        for t in range(len(upper_stages)):
            full_pairs = stage_pairs[t + 1]  # skip stage 0
            bit = stage_bit(t + 1, n)
            sub_bit = bit - 1
            stage_settings: List[int] = []
            for i, _j in full_pairs:
                if i % 2 == 0:
                    i_sub = i >> 1
                    idx = remove_bit(i_sub, sub_bit)
                    stage_settings.append(upper_stages[t][idx])
                else:
                    i_sub = i >> 1
                    idx = remove_bit(i_sub, sub_bit)
                    stage_settings.append(lower_stages[t][idx])
            middle.append(stage_settings)

        return [stage0] + middle + [stage_last]

    def to_eca57_circuit(
        self,
        aux_wire: Optional[int] = None,
        obfuscate: bool = False,
        identity_gate_count: Optional[int] = None,
        rng_seed: Optional[int] = None,
        min_identity_gates: int = 24,
        prefer_longer_identities: bool = True,
        swap_library: Optional[ECA57SwapLibrary] = None,
        swap_gate_count: Optional[int] = None
    ) -> ECA57Circuit:
        assert self._routed, "Network must be routed before conversion"

        if aux_wire is None:
            aux_wire = self.n
            width = self.n + 1
        else:
            width = max(self.n, aux_wire + 1)

        circuit = ECA57Circuit(width)
        rng = random.Random(rng_seed) if rng_seed is not None else random.Random()

        if obfuscate:
            from synthesizers.identity_filler import get_identity_filler
            filler = get_identity_filler()

        for stage_idx, stage in enumerate(self._stage_pairs):
            settings = self._stage_settings[stage_idx]
            for op_idx, (wire_a, wire_b) in enumerate(stage):
                setting = settings[op_idx]
                if setting == 1:
                    if swap_library is not None:
                        swap_circuit = swap_library.random_swap(
                            wire_a, wire_b, aux_wire, width, rng, target_gates=swap_gate_count
                        )
                    else:
                        swap_circuit = ECA57SwapMacro.generate_swap(wire_a, wire_b, aux_wire, width)
                    for gate in swap_circuit.gates():
                        circuit.add_gate(gate.target, gate.ctrl1, gate.ctrl2)
                elif obfuscate:
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

        return circuit

    def swap_count(self) -> int:
        return sum(sum(1 for s in stage if s == 1) for stage in self._stage_settings)

    def identity_slot_count(self) -> int:
        return sum(sum(1 for s in stage if s == 0) for stage in self._stage_settings)

    def gate_count_estimate(self, obfuscate: bool = False, identity_gates: int = 6) -> int:
        if obfuscate:
            return self.swap_count() * 6 + self.identity_slot_count() * identity_gates
        return self.swap_count() * 6


def synthesize_waksman(
    width: int,
    permutation: List[int],
    aux_wire: Optional[int] = None,
    obfuscate: bool = False,
    identity_gate_count: Optional[int] = None,
    rng_seed: Optional[int] = None,
    min_identity_gates: int = 24,
    prefer_longer_identities: bool = True,
    randomize_routing: bool = False,
    swap_library: Optional[ECA57SwapLibrary] = None,
    swap_gate_count: Optional[int] = None
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
    network = WaksmanNetwork(width, randomize=randomize_routing, rng_seed=rng_seed)
    network.route(permutation)
    return network.to_eca57_circuit(
        aux_wire, obfuscate, identity_gate_count, rng_seed,
        min_identity_gates, prefer_longer_identities, swap_library, swap_gate_count
    )


def synthesize_benes(
    width: int,
    permutation: List[int],
    aux_wire: Optional[int] = None,
    obfuscate: bool = False,
    identity_gate_count: Optional[int] = None,
    rng_seed: Optional[int] = None,
    min_identity_gates: int = 24,
    prefer_longer_identities: bool = True,
    randomize_routing: bool = False,
    swap_library: Optional[ECA57SwapLibrary] = None,
    swap_gate_count: Optional[int] = None
) -> ECA57Circuit:
    """Synthesize a wire permutation circuit using Beneš fixed topology."""
    network = BenesNetwork(width, randomize=randomize_routing, rng_seed=rng_seed)
    network.route(permutation)
    return network.to_eca57_circuit(
        aux_wire, obfuscate, identity_gate_count, rng_seed,
        min_identity_gates, prefer_longer_identities, swap_library, swap_gate_count
    )


def synthesize_permutation(
    n: int,
    permutation: List[int],
    aux_wire: Optional[int] = None,
    obfuscate: bool = False,
    identity_gate_count: Optional[int] = None,
    rng_seed: Optional[int] = None,
    min_identity_gates: int = 24,
    prefer_longer_identities: bool = True,
    swap_library: Optional[ECA57SwapLibrary] = None,
    swap_gate_count: Optional[int] = None
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
        min_identity_gates, prefer_longer_identities, swap_library, swap_gate_count
    )
