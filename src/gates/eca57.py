"""ECA Rule 57 gate implementation.

ECA Rule 57 is a reversible gate defined by:
    target ^= (ctrl1 OR NOT ctrl2)
    
This gate flips the target bit when (ctrl1 OR NOT ctrl2) is True.
It is a universal reversible gate capable of implementing any reversible function.

The gate has three wires:
    - target (a): the wire that gets flipped
    - ctrl1 (c1): active-high control, contributes to the OR condition
    - ctrl2 (c2): active-low control (inverted), contributes as NOT to the OR

Truth table for the control condition:
    c1  c2  | c1 OR NOT c2
    0   0   |  1  (NOT c2 = 1)
    0   1   |  0  
    1   0   |  1
    1   1   |  1
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class ECA57Gate:
    """ECA Rule 57 Gate: target ^= (ctrl1 OR NOT ctrl2)
    
    Attributes:
        target: Wire index that gets conditionally flipped.
        ctrl1: Active-high control wire (contributes c1 to OR).
        ctrl2: Active-low control wire (contributes NOT c2 to OR).
    """
    target: int
    ctrl1: int
    ctrl2: int
    
    def __post_init__(self):
        assert self.target != self.ctrl1, "Target cannot be same as ctrl1"
        assert self.target != self.ctrl2, "Target cannot be same as ctrl2"
        assert self.ctrl1 != self.ctrl2, "ctrl1 cannot be same as ctrl2"
    
    def apply(self, state: List[int]) -> List[int]:
        """Apply the gate to a state vector.
        
        Args:
            state: List of bits [bit0, bit1, ...].
            
        Returns:
            New state after gate application.
        """
        result = state.copy()
        c1 = state[self.ctrl1]
        c2 = state[self.ctrl2]
        
        # target ^= (c1 OR NOT c2)
        condition = c1 | (1 - c2)
        result[self.target] ^= condition
        
        return result
    
    def to_tuple(self) -> Tuple[int, int, int]:
        """Convert to (target, ctrl1, ctrl2) tuple."""
        return (self.target, self.ctrl1, self.ctrl2)
    
    @classmethod
    def from_tuple(cls, t: Tuple[int, int, int]) -> "ECA57Gate":
        """Create gate from (target, ctrl1, ctrl2) tuple."""
        return cls(target=t[0], ctrl1=t[1], ctrl2=t[2])


class ECA57Circuit:
    """A circuit composed of ECA57 gates.
    
    Similar interface to the MCT Circuit class but using ECA57 gates.
    """
    
    def __init__(self, width: int):
        """Initialize empty circuit.
        
        Args:
            width: Number of wires in the circuit.
        """
        assert width >= 3, "ECA57 gates require at least 3 wires"
        self._width = width
        self._gates: List[ECA57Gate] = []
    
    def width(self) -> int:
        """Return circuit width."""
        return self._width
    
    def __len__(self) -> int:
        return len(self._gates)
    
    def gates(self) -> List[ECA57Gate]:
        """Return list of gates."""
        return self._gates.copy()
    
    def add_gate(self, target: int, ctrl1: int, ctrl2: int) -> "ECA57Circuit":
        """Add an ECA57 gate to the circuit.
        
        Args:
            target: Target wire index.
            ctrl1: Active-high control wire.
            ctrl2: Active-low control wire.
            
        Returns:
            Self for chaining.
        """
        assert 0 <= target < self._width
        assert 0 <= ctrl1 < self._width
        assert 0 <= ctrl2 < self._width
        
        gate = ECA57Gate(target, ctrl1, ctrl2)
        self._gates.append(gate)
        return self
    
    def apply(self, state: List[int]) -> List[int]:
        """Apply all gates to a state.
        
        Args:
            state: Initial state as list of bits.
            
        Returns:
            Final state after all gates.
        """
        result = state.copy()
        for gate in self._gates:
            result = gate.apply(result)
        return result
    
    def compute_truth_table(self) -> List[List[int]]:
        """Compute the full truth table of the circuit.
        
        Returns:
            List of output states for each input (0 to 2^width - 1).
        """
        rows = 2 ** self._width
        table = []
        
        for i in range(rows):
            # Convert int to bit list
            state = [(i >> bit) & 1 for bit in range(self._width)]
            output = self.apply(state)
            table.append(output)
        
        return table
    
    def is_identity(self) -> bool:
        """Check if circuit implements identity function."""
        tt = self.compute_truth_table()
        for i, output in enumerate(tt):
            expected = [(i >> bit) & 1 for bit in range(self._width)]
            if output != expected:
                return False
        return True
    
    def __str__(self) -> str:
        """ASCII representation of the circuit."""
        lines = [f"ECA57 Circuit (width={self._width}, gates={len(self)})"]
        for i, gate in enumerate(self._gates):
            lines.append(f"  [{i}] target={gate.target}, ctrl1={gate.ctrl1}, ctrl2={gate.ctrl2}")
        return "\n".join(lines)
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, ECA57Circuit):
            return False
        return self._width == other._width and self._gates == other._gates
    
    def __hash__(self):
        return hash((self._width, tuple(self._gates)))
    
    def copy(self) -> "ECA57Circuit":
        """Create a copy of this circuit."""
        new = ECA57Circuit(self._width)
        new._gates = self._gates.copy()
        return new
    
    def gate_swappable(self, index: int, ignore_identical: bool = True) -> bool:
        """Check if gates at index and index+1 can be swapped (commute).
        
        Gates commute if neither's target is used by the other AND they don't share a target.
        For ECA57: gates commute if:
        - t_i ∉ {ctrl1_{i+1}, ctrl2_{i+1}}
        - t_{i+1} ∉ {ctrl1_i, ctrl2_i}
        
        Args:
            index: Index of first gate (second is index+1 mod length).
            ignore_identical: If True, don't swap identical gates.
            
        Returns:
            True if gates can be swapped.
        """
        g1 = self._gates[index]
        g2 = self._gates[(index + 1) % len(self)]
        
        if ignore_identical and g1 == g2:
            return False
        
        # Check if target of g1 is used by g2
        g1_target_collision = g1.target in (g2.ctrl1, g2.ctrl2)
        # Check if target of g2 is used by g1
        g2_target_collision = g2.target in (g1.ctrl1, g1.ctrl2)
        
        return not g1_target_collision and not g2_target_collision
    
    def swap(self, index: int) -> "ECA57Circuit":
        """Return new circuit with gates at index and index+1 swapped."""
        new = self.copy()
        next_idx = (index + 1) % len(self)
        new._gates[index], new._gates[next_idx] = new._gates[next_idx], new._gates[index]
        return new
    
    def rotate(self, shift: int) -> "ECA57Circuit":
        """Return circuit with gates cyclically rotated by shift positions."""
        new = ECA57Circuit(self._width)
        n = len(self)
        if n == 0:
            return new
        shift = shift % n
        new._gates = self._gates[shift:] + self._gates[:shift]
        return new
    
    def reverse(self) -> "ECA57Circuit":
        """Return circuit with gate order reversed (mirror)."""
        new = ECA57Circuit(self._width)
        new._gates = self._gates[::-1]
        return new
    
    def permute(self, perm: List[int]) -> "ECA57Circuit":
        """Return circuit with wire labels permuted.
        
        Args:
            perm: Permutation list where perm[old_wire] = new_wire.
            
        Returns:
            New circuit with permuted wire labels.
        """
        new = ECA57Circuit(self._width)
        for g in self._gates:
            new_gate = ECA57Gate(perm[g.target], perm[g.ctrl1], perm[g.ctrl2])
            new._gates.append(new_gate)
        return new
    
    def swaps(self) -> List["ECA57Circuit"]:
        """Return list of circuits reachable by one valid swap."""
        results = [self.copy()]
        for i in range(len(self)):
            if self.gate_swappable(i):
                results.append(self.swap(i))
        return results
    
    def rotations(self) -> List["ECA57Circuit"]:
        """Return all unique rotations of this circuit."""
        seen = set()
        results = []
        for shift in range(len(self)):
            rotated = self.rotate(shift)
            key = tuple(g.to_tuple() for g in rotated._gates)
            if key not in seen:
                seen.add(key)
                results.append(rotated)
        return results
    
    def permutations(self) -> List["ECA57Circuit"]:
        """Return all unique wire permutations of this circuit."""
        from itertools import permutations as iterperms
        seen = set()
        results = []
        for perm in iterperms(range(self._width)):
            permuted = self.permute(list(perm))
            key = tuple(g.to_tuple() for g in permuted._gates)
            if key not in seen:
                seen.add(key)
                results.append(permuted)
        return results
    
    def swap_space_bfs(self) -> List["ECA57Circuit"]:
        """Find all circuits reachable by gate swaps (BFS)."""
        from collections import deque
        visited = set()
        results = []
        queue = deque([self])
        
        while queue:
            curr = queue.popleft()
            key = tuple(g.to_tuple() for g in curr._gates)
            if key not in visited:
                visited.add(key)
                results.append(curr)
                for neighbor in curr.swaps():
                    nkey = tuple(g.to_tuple() for g in neighbor._gates)
                    if nkey not in visited:
                        queue.append(neighbor)
        return results
    
    def unroll(self) -> List["ECA57Circuit"]:
        """Generate all equivalent circuits via Algorithm 2.
        
        Applies: DFS swaps, rotations, reversal, permutations.
        
        Returns:
            List of all equivalent circuits.
        """
        # Step 1: Swap space (DFS/BFS)
        equivalents = self.swap_space_bfs()
        
        # Step 2: Rotations
        new_equivs = []
        for c in equivalents:
            new_equivs.extend(c.rotations())
        equivalents = new_equivs
        
        # Step 3: Mirror (reverse)
        new_equivs = []
        for c in equivalents:
            new_equivs.append(c)
            new_equivs.append(c.reverse())
        equivalents = new_equivs
        
        # Step 4: Remove duplicates
        seen = set()
        unique = []
        for c in equivalents:
            key = tuple(g.to_tuple() for g in c._gates)
            if key not in seen:
                seen.add(key)
                unique.append(c)
        equivalents = unique
        
        # Step 5: Wire permutations
        new_equivs = []
        for c in equivalents:
            new_equivs.extend(c.permutations())
        
        # Final dedup
        seen = set()
        unique = []
        for c in new_equivs:
            key = tuple(g.to_tuple() for g in c._gates)
            if key not in seen:
                seen.add(key)
                unique.append(c)
        
        return unique
    
    def canonical(self) -> "ECA57Circuit":
        """Return the canonical (lexicographically smallest) equivalent circuit.
        
        Among all circuits in the equivalence class, returns the one with
        the lexicographically smallest gate tuple sequence. This provides
        a unique representative for storage.
        
        Returns:
            Canonical form of this circuit.
        """
        equivalents = self.unroll()
        
        # Convert to (tuple_key, circuit) pairs
        keyed = [(tuple(g.to_tuple() for g in c._gates), c) for c in equivalents]
        
        # Find lexicographically smallest
        keyed.sort(key=lambda x: x[0])
        
        return keyed[0][1]
    
    def canonical_key(self) -> Tuple[Tuple[int, int, int], ...]:
        """Return the canonical key (gate tuple sequence) for this circuit.
        
        This is the lexicographically smallest representation among all equivalents.
        Useful for deduplication and comparison.
        
        Returns:
            Tuple of (target, ctrl1, ctrl2) tuples for canonical form.
        """
        return tuple(g.to_tuple() for g in self.canonical()._gates)
    
    def slice(self, start: int, end: int) -> "ECA57Circuit":
        """Extract subsequence of gates [start:end].
        
        Args:
            start: Starting index (inclusive).
            end: Ending index (exclusive).
            
        Returns:
            New circuit with gates[start:end].
        """
        new = ECA57Circuit(self._width)
        new._gates = self._gates[start:end]
        return new
    
    def min_slice(self) -> "ECA57Circuit":
        """Return the first half (+1) of the circuit.
        
        For identity circuits of length 2n, returns gates 0 to n (inclusive),
        which can be used as a "witness" or template.
        
        Returns:
            New circuit with first half + 1 gates.
        """
        return self.slice(0, len(self) // 2 + 1)
    
    def add_empty_line(self, line_id: int) -> "ECA57Circuit":
        """Insert a new wire at position line_id that no gate touches.
        
        All wire indices >= line_id are shifted up by 1.
        
        Args:
            line_id: Position to insert new wire (0 <= line_id <= width).
            
        Returns:
            New circuit with width+1 wires.
        """
        assert 0 <= line_id <= self._width
        new = ECA57Circuit(self._width + 1)
        
        for gate in self._gates:
            new_target = gate.target if line_id > gate.target else gate.target + 1
            new_ctrl1 = gate.ctrl1 if line_id > gate.ctrl1 else gate.ctrl1 + 1
            new_ctrl2 = gate.ctrl2 if line_id > gate.ctrl2 else gate.ctrl2 + 1
            new.add_gate(new_target, new_ctrl1, new_ctrl2)
        
        return new
    
    def empty_line_extensions(self, target_width: int) -> List["ECA57Circuit"]:
        """Generate all ways to add spectator wires to reach target_width.
        
        Args:
            target_width: Target number of wires.
            
        Returns:
            List of circuits with width = target_width.
        """
        from itertools import combinations
        
        lines_to_insert = target_width - self._width
        assert lines_to_insert >= 0
        
        extensions = []
        for lines_ids in combinations(range(target_width), lines_to_insert):
            new = self
            for line_id in lines_ids:
                new = new.add_empty_line(line_id)
            extensions.append(new)
        
        return extensions
    
    def contains(self, subcircuit: "ECA57Circuit") -> bool:
        """Check if this circuit contains subcircuit as contiguous subsequence.
        
        Args:
            subcircuit: Circuit to search for.
            
        Returns:
            True if subcircuit is found as contiguous gates.
        """
        if subcircuit._width != self._width:
            return False
        
        outer = [g.to_tuple() for g in self._gates]
        inner = [g.to_tuple() for g in subcircuit._gates]
        
        inner_len = len(inner)
        for i in range(len(outer) - inner_len + 1):
            if outer[i:i + inner_len] == inner:
                return True
        return False


def all_eca57_gates(width: int) -> List[ECA57Gate]:
    """Generate all possible ECA57 gates for a given width.
    
    Args:
        width: Number of wires.
        
    Returns:
        List of all valid ECA57 gates (width * (width-1) * (width-2) gates).
    """
    gates = []
    for target in range(width):
        for ctrl1 in range(width):
            if ctrl1 == target:
                continue
            for ctrl2 in range(width):
                if ctrl2 == target or ctrl2 == ctrl1:
                    continue
                gates.append(ECA57Gate(target, ctrl1, ctrl2))
    return gates
