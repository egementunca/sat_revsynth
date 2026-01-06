"""ECA57 Dimension Group Container.

Container for ECA57 circuits with identical (width, gate_count) dimensions.
Supports the unroll-exclude synthesis pattern.
"""
from __future__ import annotations

from typing import List, Iterator, TYPE_CHECKING
from gates.eca57 import ECA57Circuit

if TYPE_CHECKING:
    pass


class ECA57DimGroup:
    """Container for ECA57 circuits with identical dimensions.
    
    All circuits in a DimGroup must have exactly the same number of wires
    and gates. This enables efficient grouping for synthesis enumeration.
    
    Attributes:
        _width: Number of wires for all circuits.
        _gate_count: Number of gates for all circuits.
        _circuits: List of ECA57Circuit objects.
    """
    
    def __init__(self, width: int, gate_count: int):
        """Create an empty DimGroup for the given dimensions."""
        assert width >= 3, "ECA57 requires at least 3 wires"
        self._width = width
        self._gate_count = gate_count
        self._circuits: List[ECA57Circuit] = []
    
    def __len__(self) -> int:
        return len(self._circuits)
    
    def __getitem__(self, key: int) -> ECA57Circuit:
        return self._circuits[key]
    
    def __bool__(self) -> bool:
        return bool(self._circuits)
    
    def __iter__(self) -> Iterator[ECA57Circuit]:
        return iter(self._circuits)
    
    @property
    def width(self) -> int:
        return self._width
    
    @property
    def gate_count(self) -> int:
        return self._gate_count
    
    def _validate_circuit(self, circuit: ECA57Circuit) -> None:
        """Validate that circuit matches this group's dimensions."""
        msg = f"({self._width}, {self._gate_count}) != ({circuit.width()}, {len(circuit)})"
        assert (self._width, self._gate_count) == (circuit.width(), len(circuit)), msg
    
    def _validate_dimgroup(self, other: "ECA57DimGroup") -> None:
        """Validate that other group has same dimensions."""
        msg = f"({self._width}, {self._gate_count}) != ({other._width}, {other._gate_count})"
        assert (self._width, self._gate_count) == (other._width, other._gate_count), msg
    
    def append(self, circuit: ECA57Circuit) -> None:
        """Add a circuit to the group (validates dimensions match)."""
        self._validate_circuit(circuit)
        self._circuits.append(circuit)
    
    def extend(self, circuits: List[ECA57Circuit]) -> None:
        """Add multiple circuits to the group."""
        for circ in circuits:
            self.append(circ)
    
    def join(self, other: "ECA57DimGroup") -> None:
        """Merge another DimGroup's circuits into this group."""
        self._validate_dimgroup(other)
        self._circuits.extend(other._circuits)
    
    def remove_reducibles(self, reductors: "ECA57DimGroup") -> None:
        """Remove circuits containing any reductor as a subcircuit.
        
        A circuit is "reducible" if it contains a smaller identity template,
        meaning it's not a minimal irreducible representative.
        
        Args:
            reductors: DimGroup of smaller circuits to check.
        """
        assert reductors._width == self._width
        assert reductors._gate_count <= self._gate_count
        
        irreducible = []
        for circ in self._circuits:
            is_reducible = False
            for red in reductors._circuits:
                if self._contains_subcircuit(circ, red):
                    is_reducible = True
                    break
            if not is_reducible:
                irreducible.append(circ)
        self._circuits = irreducible
    
    def _contains_subcircuit(self, outer: ECA57Circuit, inner: ECA57Circuit) -> bool:
        """Check if outer contains inner as contiguous gate subsequence."""
        outer_gates = [g.to_tuple() for g in outer.gates()]
        inner_gates = [g.to_tuple() for g in inner.gates()]
        
        inner_len = len(inner_gates)
        for i in range(len(outer_gates) - inner_len + 1):
            if outer_gates[i:i + inner_len] == inner_gates:
                return True
        return False
    
    def remove_duplicates(self) -> None:
        """Remove duplicate circuits (by canonical key)."""
        seen = set()
        unique = []
        for circ in self._circuits:
            key = tuple(g.to_tuple() for g in circ.gates())
            if key not in seen:
                seen.add(key)
                unique.append(circ)
        self._circuits = unique
    
    def circuits(self) -> List[ECA57Circuit]:
        """Return list of all circuits."""
        return self._circuits.copy()
    
    def to_dict(self) -> dict:
        """Serialize to dictionary for storage."""
        return {
            "width": self._width,
            "gate_count": self._gate_count,
            "circuits": [
                [g.to_tuple() for g in c.gates()]
                for c in self._circuits
            ]
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ECA57DimGroup":
        """Deserialize from dictionary."""
        dg = cls(data["width"], data["gate_count"])
        for gate_list in data["circuits"]:
            circ = ECA57Circuit(data["width"])
            for t, c1, c2 in gate_list:
                circ.add_gate(t, c1, c2)
            dg._circuits.append(circ)
        return dg
