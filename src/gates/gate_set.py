"""Gate set abstraction for different reversible gate families."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Tuple, Any
from enum import Enum


class GateSetType(Enum):
    """Supported gate set types."""
    MCT = "mct"      # Multiple-Control Toffoli
    ECA57 = "eca57"  # Elementary Cellular Automaton Rule 57


class GateSet(ABC):
    """Abstract base class for gate set definitions."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return gate set name."""
        pass
    
    @property
    @abstractmethod
    def gate_type(self) -> GateSetType:
        """Return gate set type enum."""
        pass
    
    @abstractmethod
    def num_gates(self, width: int) -> int:
        """Return number of possible gates for given width."""
        pass
    
    @abstractmethod
    def enumerate_gates(self, width: int) -> List[Any]:
        """Enumerate all possible gates for given width."""
        pass


class MCTGateSet(GateSet):
    """Multiple-Control Toffoli gate set.
    
    Gates are represented as (controls, target) where controls is a list
    of control wire indices and target is the target wire index.
    """
    
    @property
    def name(self) -> str:
        return "MCT (Multiple-Control Toffoli)"
    
    @property
    def gate_type(self) -> GateSetType:
        return GateSetType.MCT
    
    def num_gates(self, width: int) -> int:
        """For each target wire, any subset of other wires can be controls."""
        # width targets * 2^(width-1) control subsets = width * 2^(width-1)
        return width * (2 ** (width - 1))
    
    def enumerate_gates(self, width: int) -> List[Tuple[List[int], int]]:
        """Enumerate all MCT gates.
        
        Returns:
            List of (controls, target) tuples.
        """
        from itertools import combinations
        
        gates = []
        for target in range(width):
            other_wires = [w for w in range(width) if w != target]
            # All subsets of other wires as controls
            for num_controls in range(len(other_wires) + 1):
                for controls in combinations(other_wires, num_controls):
                    gates.append((list(controls), target))
        return gates


class ECA57GateSet(GateSet):
    """ECA Rule 57 gate set.
    
    Gates are represented as (target, ctrl1, ctrl2) where:
    - target ^= (ctrl1 OR NOT ctrl2)
    """
    
    @property
    def name(self) -> str:
        return "ECA57 (Elementary Cellular Automaton Rule 57)"
    
    @property
    def gate_type(self) -> GateSetType:
        return GateSetType.ECA57
    
    def num_gates(self, width: int) -> int:
        """width choices for target * (width-1) for ctrl1 * (width-2) for ctrl2."""
        return width * (width - 1) * (width - 2)
    
    def enumerate_gates(self, width: int) -> List[Tuple[int, int, int]]:
        """Enumerate all ECA57 gates.
        
        Returns:
            List of (target, ctrl1, ctrl2) tuples.
        """
        gates = []
        for target in range(width):
            for ctrl1 in range(width):
                if ctrl1 == target:
                    continue
                for ctrl2 in range(width):
                    if ctrl2 == target or ctrl2 == ctrl1:
                        continue
                    gates.append((target, ctrl1, ctrl2))
        return gates


def get_gate_set(gate_type: GateSetType) -> GateSet:
    """Factory function to get gate set by type."""
    if gate_type == GateSetType.MCT:
        return MCTGateSet()
    elif gate_type == GateSetType.ECA57:
        return ECA57GateSet()
    else:
        raise ValueError(f"Unknown gate type: {gate_type}")
