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
