"""Reversible Circuit Representation.

This module provides the Circuit class for representing reversible logic circuits
composed of MCT (Multiple-Control Toffoli) gates. It supports:

- Gate operations: X, CX, MCX (multiple-control X)
- Equivalence transformations: rotate, reverse, permute, swap
- Identity template enumeration via swap-space exploration (unroll)
- Circuit comparison and truth table computation

The equivalence operations define equivalence classes of circuits:
    - Rotations: cyclic permutation of gate order
    - Reversals: mirror the circuit
    - Wire permutations: relabel wires
    - Swaps: commute adjacent non-interfering gates

Example:
    >>> circ = Circuit(3)
    >>> circ.cx(0, 1).mcx([0, 1], 2)  # CNOT then Toffoli
    >>> print(circ)  # ASCII circuit diagram
"""
from __future__ import annotations

from qiskit import QuantumCircuit
from copy import copy, deepcopy
from itertools import permutations, combinations
from functools import reduce
from truth_table.truth_table import TruthTable
from utils.inplace import inplace
from collections import deque


Gate = tuple[list[int], int]  # Gate in integer representation: (controls, target)


class Circuit:
    """A reversible circuit composed of MCT gates.
    
    A circuit operates on a fixed number of wires (width) and consists of
    a sequence of gates. Each gate is defined by its control wires and target wire.
    
    Attributes:
        _width: Number of wires in the circuit.
        _gates: List of gates as (controls, target) tuples.
        _tt: Cached truth table (computed on demand).
    
    Example:
        >>> circ = Circuit(2)
        >>> circ.cx(0, 1)  # CNOT gate
        >>> circ.tt()  # Get truth table
    """
    def __init__(self, bits_num: int):
        self._width = bits_num
        self._tt: TruthTable | None = None
        self._gates: list[Gate] = []
        self._exclusion_list: None | list[int] = None

    def __copy__(self) -> "Circuit":
        """Create a shallow copy of the circuit."""
        new = Circuit(self._width)
        new._tt = copy(self._tt)
        new._gates = deepcopy(self._gates)
        return new

    def __str__(self) -> str:
        """Return an ASCII diagram of the circuit."""
        qc = QuantumCircuit(self._width)
        for controls, target in self._gates:
            if len(controls) == 0:
                qc.x(target)
            else:
                qc.mcx(controls, target)
            qc.barrier()
        return str(qc.draw(justify="none", plot_barriers=False, output="text"))

    def __len__(self) -> int:
        return len(self._gates)

    def __eq__(self, other) -> bool:
        return (self._width, self._gates) == (other._width, other._gates)

    def __add__(self, other: "Circuit") -> "Circuit":
        assert self._width == other._width
        new_width = self._width
        new_circuit = Circuit(new_width)
        new_circuit._gates = self._gates + other._gates
        return new_circuit

    def __getitem__(self, key: int) -> Gate:
        return self._gates[key]

    def width(self) -> int:
        return self._width

    def tt(self) -> TruthTable:
        """Compute and return the truth table for this circuit.
        
        The result is cached.
        
        Returns:
            TruthTable object representing the circuit's function.
        """
        if self._tt is None:
            self._tt = TruthTable(self._width)
            for controls, target in self._gates:
                self._tt.mcx(controls, target)
        return self._tt

    def gates(self) -> list[Gate]:
        """Return list of gates as (controls, target) tuples."""
        return self._gates

    def controls_num(self) -> int:
        """Count total control wires across all gates."""
        return reduce(lambda x, y: x + len(y[0]), self._gates, 0)

    def gate_swappable(self, index: int, ignore_identical: bool = False) -> bool:
        """Check if gates at index and index+1 can be swapped.
        
        Two gates can swap if neither's target is in the other's controls.
        """
        lhs = self._gates[index]
        rhs = self._gates[(index + 1) % len(self)]
        if ignore_identical and lhs == rhs:
            return False
        lhs_controls, lhs_target = lhs
        rhs_controls, rhs_target = rhs
        lhs_collision = lhs_target in rhs_controls
        rhs_collision = rhs_target in lhs_controls
        return not (lhs_collision) and not (rhs_collision)

    def swappable_gates(self, ignore_identical: bool = True) -> list[int]:
        """Return indices of all swappable gate positions."""
        indices = [
            i for i in range(len(self)) if self.gate_swappable(i, ignore_identical)
        ]
        return indices

    def contains(self, subcircuit: "Circuit") -> bool:
        """Check if this circuit contains subcircuit as contiguous subsequence."""
        assert self._width == subcircuit._width
        inner_len = len(subcircuit)
        len_diff = len(self) - inner_len
        for i in range(0, len_diff + 1):
            slice = self._gates[i: i + inner_len]
            if subcircuit._gates == slice:
                return True
        return False

    def reducible(self, subcircuits: list["Circuit"]) -> bool:
        """Check if circuit contains any of the given subcircuits."""
        return any(self.contains(subc) for subc in subcircuits)

    @classmethod
    def filter_duplicates(cls, unfiltered: list["Circuit"]) -> list["Circuit"]:
        """Remove duplicate circuits from list (preserves first occurrence)."""
        return [circ for i, circ in enumerate(unfiltered) if circ not in unfiltered[:i]]

    @inplace
    def x(self, target: int, **_) -> "Circuit":
        assert 0 <= target and target < self._width
        self._gates.append(([], target))
        self._tt = None
        return self

    @inplace
    def cx(self, control: int, target: int, **_) -> "Circuit":
        """Append a CNOT gate.
        
        Args:
            control: Control wire index.
            target: Target wire index.
        """
        assert 0 <= target and target < self._width
        assert 0 <= control and control < self._width
        self._gates.append(([control], target))
        self._tt = None
        return self

    @inplace
    def mcx(self, controls: list[int], target: int, **_) -> "Circuit":
        """Append a Multiple-Control Toffoli gate.
        
        Args:
            controls: List of control wire indices.
            target: Target wire index.
        """
        assert 0 <= target and target < self._width
        assert all([0 <= cid and cid < self._width for cid in controls])
        controls = sorted(controls)
        self._gates.append((controls, target))
        self._tt = None
        return self

    @inplace
    def append(self, gate: Gate, **_) -> "Circuit":
        controls, target = gate
        self.mcx(controls, target)
        self._tt = None
        return self

    @inplace
    def pop(self, **_) -> "Circuit":
        self._gates.pop()
        self._tt = None
        return self

    def reverse(self) -> "Circuit":
        """Return reversed circuit: [A,B,C] → [C,B,A]."""
        new = Circuit(self._width)
        new._gates = deepcopy(self._gates)
        new._gates.reverse()
        return new

    def rotate(self, shift: int) -> "Circuit":
        """Return rotated circuit: cyclic shift of gate order."""
        size = len(self)
        shift = (shift % size) + size % size
        new = Circuit(self._width)
        new._gates = deepcopy(self._gates)
        new._gates = new._gates[shift:] + new._gates[:shift]
        return new

    def permute(self, permutation: list[int]) -> "Circuit":
        """Return circuit with relabeled wires: wire i → wire perm[i]."""
        new_gates: list[Gate] = []
        for controls, target in self._gates:
            new_target = permutation[target]
            new_controls = sorted([permutation[c] for c in controls])
            new_gates.append((new_controls, new_target))
        new = Circuit(self._width)
        new._gates = new_gates
        return new

    def swap(self, id: int) -> "Circuit":
        """Return circuit with gates at id and id+1 swapped."""
        assert 0 <= id and id < len(self)
        next_id = (id + 1) % len(self)
        new = Circuit(self._width)
        new._gates = deepcopy(self._gates)
        new._gates[id], new._gates[next_id] = new._gates[next_id], new._gates[id]
        return new

    def slice(self, start: int, end: int) -> "Circuit":
        """Extract subsequence of gates [start:end]."""
        new = Circuit(self._width)
        new._gates = self._gates[start:end]
        return new

    def compress(self, direction: str = "left", max_iterations: int = 100, 
                  track_indices: bool = False) -> "Circuit | tuple[Circuit, list[int]]":
        """Compress circuit by canceling inverse gate pairs.
        
        Pushes gates through commuting neighbors to find and cancel identical pairs.
        MCT/ECA57 gates are self-inverse: G·G = I.
        
        Args:
            direction: "left", "right", "best", or "alternate".
            max_iterations: Max compression passes.
            track_indices: If True, return (circuit, surviving_indices).
        """
        if direction == "best":
            left = self._do_compress(from_right=False, max_iters=max_iterations, track=track_indices)
            right = self._do_compress(from_right=True, max_iters=max_iterations, track=track_indices)
            left_len = len(left[0]) if track_indices else len(left)
            right_len = len(right[0]) if track_indices else len(right)
            return left if left_len <= right_len else right
        elif direction == "alternate":
            return self._do_compress_alt(max_iters=max_iterations, track=track_indices)
        else:
            return self._do_compress(from_right=(direction == "right"), 
                                      max_iters=max_iterations, track=track_indices)
    
    def _do_compress(self, from_right: bool, max_iters: int, track: bool):
        """Core compression: push gates in one direction until fixpoint."""
        gates = [(g, i) for i, g in enumerate(self._gates)]
        for _ in range(max_iters):
            if not self._compress_pass(gates, from_right):
                break
        return self._build_result(gates, track)
    
    def _do_compress_alt(self, max_iters: int, track: bool):
        """Alternate left/right until no progress."""
        gates = [(g, i) for i, g in enumerate(self._gates)]
        for _ in range(max_iters):
            prog_l = self._compress_pass(gates, from_right=False)
            prog_r = self._compress_pass(gates, from_right=True)
            if not prog_l and not prog_r:
                break
        return self._build_result(gates, track)
    
    def _compress_pass(self, gates: list, from_right: bool) -> bool:
        """One compression pass. Mutates gates list. Returns True if any cancellation."""
        made_progress = False
        while True:
            n = len(gates)
            if n == 0:
                break
            cancelled = False
            for idx in (range(n-1, -1, -1) if from_right else range(n)):
                if idx >= len(gates):
                    continue
                gate, _ = gates[idx]
                pos = idx
                step = -1 if from_right else 1
                bound = (lambda p: p > 0) if from_right else (lambda p: p < len(gates) - 1)
                
                while bound(pos):
                    neighbor, _ = gates[pos + step]
                    if gate == neighbor:
                        # Cancel pair
                        del gates[max(pos, pos + step)]
                        del gates[min(pos, pos + step)]
                        cancelled = made_progress = True
                        break
                    if self._gates_commute(gate, neighbor):
                        gates[pos], gates[pos + step] = gates[pos + step], gates[pos]
                        pos += step
                    else:
                        break
                if cancelled:
                    break
            if not cancelled:
                break
        return made_progress
    
    def _build_result(self, gates: list, track: bool):
        """Build Circuit from gates list."""
        result = Circuit(self._width)
        result._gates = [g for g, _ in gates]
        if track:
            return result, [i for _, i in gates]
        return result
    
    def _gates_commute(self, g1: Gate, g2: Gate) -> bool:
        """Check if two gates commute (can swap without changing result).
        
        Gates commute UNLESS one's target is in the other's controls.
        Same-target gates always commute (XOR is commutative).
        """
        c1, t1 = g1
        c2, t2 = g2
        # Only non-commuting case: target in other's controls
        return t1 not in c2 and t2 not in c1

    def min_slice(self) -> "Circuit":
        """Return first half+1 of circuit (for identity template analysis)."""
        return self.slice(0, len(self) // 2 + 1)

    def add_empty_line(self, line_id: int) -> "Circuit":
        """Insert new wire at line_id that no gate touches."""
        assert 0 <= line_id and line_id <= self._width
        new = Circuit(self._width + 1)
        for controls, target in self._gates:
            new_target = target if line_id > target else target + 1
            new_controls = [(c if line_id > c else c + 1) for c in controls]
            new.mcx(new_controls, new_target)
        return new

    def add_full_line(self, line_id: int) -> "Circuit":
        """Insert new wire at line_id as control to all gates."""
        assert 0 <= line_id and line_id <= self._width
        new = Circuit(self._width + 1)
        for controls, target in self._gates:
            new_target = target if line_id > target else target + 1
            new_controls = [(c if line_id > c else c + 1) for c in controls] + [line_id]
            new.mcx(new_controls, new_target)
        return new

    def rotations(self) -> list["Circuit"]:
        """Return all unique cyclic rotations of this circuit."""
        equivalents = [self.rotate(s) for s in range(len(self))]
        unique = self.filter_duplicates(equivalents)
        return unique

    def permutations(self) -> list["Circuit"]:
        """Return all unique wire permutations of this circuit."""
        all_permutations = permutations(list(range(self._width)))
        equivalents = [self.permute(list(perm)) for perm in all_permutations]
        unique = self.filter_duplicates(equivalents)
        return unique

    def swaps(self) -> list["Circuit"]:
        """Return all circuits reachable by one adjacent gate swap."""
        swap_ids = self.swappable_gates()
        equivalents = [copy(self)] + [self.swap(id) for id in swap_ids]
        unique = self.filter_duplicates(equivalents)
        return unique

    def _dfs(self, visited: list["Circuit"]):
        visited.append(self)
        neighbours = self.swaps()
        for node in neighbours:
            if node not in visited:
                node._dfs(visited)

    def swap_space_dfs(self) -> list["Circuit"]:
        """Find all circuits reachable via gate swaps (DFS traversal)."""
        nodes = []
        self._dfs(nodes)
        return nodes

    def swap_space_bfs(self, initial: list["Circuit"] = []) -> list["Circuit"]:
        """Find all circuits reachable via gate swaps (BFS traversal).
        
        Returns the "swap space" - all circuits equivalent under commuting
        adjacent non-interfering gates.
        """
        visited: list["Circuit"] = []
        queue: deque["Circuit"] = deque()
        queue.append(self)
        for other in initial:
            if other not in initial:
                queue.append(other)
        while queue:
            curr = queue.popleft()
            if curr not in visited:
                visited.append(curr)
                for neighbor in curr.swaps():
                    if neighbor not in visited:
                        queue.append(neighbor)
        return visited

    def local_unroll(self) -> list["Circuit"]:
        """Quick equivalence: rotations + reverse + permutations (no swaps)."""
        equivalents = self.rotations()
        temp_list = [circuit.reverse() for circuit in equivalents]
        equivalents += temp_list
        temp_list = []
        for circuit in equivalents:
            temp_list += circuit.permutations()
        equivalents = temp_list
        return equivalents

    def unroll(self, initial: list["Circuit"] = []) -> list["Circuit"]:
        """Full equivalence class enumeration.
        
        Combines: swap-space × rotations × reverse × wire permutations.
        Returns all circuits equivalent to this one under these transformations.
        """
        equivalents = self.swap_space_bfs(initial)

        temp_list = []
        for circuit in equivalents:
            rotations = circuit.rotations()
            temp_list += rotations
        equivalents = temp_list

        temp_list = [circuit.reverse() for circuit in equivalents]
        equivalents += temp_list
        equivalents = Circuit.filter_duplicates(equivalents)

        temp_list = []
        for circuit in equivalents:
            temp_list += circuit.permutations()
        equivalents = temp_list

        equivalents = Circuit.filter_duplicates(equivalents)
        return equivalents

    def empty_line_extensions(self, target_width: int) -> list["Circuit"]:
        """All ways to add empty (spectator) wires to reach target_width.
        
        Args:
            target_width: Desired final width.
            
        Returns:
            List of circuits with new empty lines inserted.
        """
        lines_to_insert = target_width - self._width
        assert lines_to_insert >= 0
        extensions = []
        for lines_ids in combinations(range(target_width), lines_to_insert):
            new = self
            for line_id in lines_ids:
                new = new.add_empty_line(line_id)
            extensions.append(new)
        return extensions

    def full_line_extensions(self, target_width: int) -> list["Circuit"]:
        """All ways to add control wires to reach target_width.
        
        Adds lines that control every gate in the circuit.
        
        Args:
            target_width: Desired final width.
            
        Returns:
            List of circuits with new control lines inserted.
        """
        lines_to_insert = target_width - self._width
        assert lines_to_insert >= 0
        extensions = []
        for lines_ids in combinations(range(target_width), lines_to_insert):
            new = self
            for line_id in lines_ids:
                new = new.add_full_line(line_id)
            extensions.append(new)
        return extensions
