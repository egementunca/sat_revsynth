"""Dimension Group for Reversible Circuits.

A DimGroup holds circuits that share the same (width, gate_count) dimensions.
It serves as a container for equivalence class representatives, enabling
operations like merging groups and removing reducible circuits.

Hierarchy:
    Collection → DimGroup → Circuit → Gate

Example:
    >>> dg = DimGroup(3, 4)  # 3 wires, 4 gates
    >>> dg.append(some_circuit)
    >>> dg.remove_reducibles(smaller_identities)
"""
from circuit.circuit import Circuit


class DimGroup:
    """Container for circuits with identical (width, gate_count) dimensions.
    
    All circuits in a DimGroup must have exactly the same number of wires
    and gates. This enables efficient grouping for synthesis enumeration
    and reducibility checking.
    
    Attributes:
        _width: Number of wires for all circuits in this group.
        _gate_count: Number of gates for all circuits in this group.
        _circuits: List of Circuit objects.
    """
    def __init__(self, width: int, gate_count: int):
        """Create an empty DimGroup for the given dimensions."""
        self._width = width
        self._gate_count = gate_count
        self._circuits = []

    def __len__(self) -> int:
        return len(self._circuits)

    def __getitem__(self, key: int) -> Circuit:
        return self._circuits[key]

    def __bool__(self) -> bool:
        return bool(self._circuits)

    def _validate_circuit(self, circuit: Circuit) -> None:
        msg = (
            f"({self._width}, {self._gate_count}) != ({circuit._width}, {len(circuit)})"
        )
        assert (self._width, self._gate_count) == (circuit._width, len(circuit)), msg

    def _validate_dimgroup(self, other: "DimGroup") -> None:
        msg = f"({self._width}, {self._gate_count}) != ({other._width}, {other._gate_count})"
        assert (self._width, self._gate_count) == (other._width, other._gate_count), msg

    def append(self, circuit: Circuit) -> None:
        """Add a circuit to the group (validates dimensions match)."""
        self._validate_circuit(circuit)
        self._circuits.append(circuit)

    def extend(self, other: list[Circuit]) -> None:
        """Add multiple circuits to the group."""
        for circ in other:
            self.append(circ)

    def join(self, other: "DimGroup") -> None:
        """Merge another DimGroup's circuits into this group."""
        self._validate_dimgroup(other)
        self._circuits += other._circuits

    def remove_reducibles(self, reductors: "DimGroup"):
        """Remove circuits that contain any reductor circuit as a subcircuit.
        
        A circuit is "reducible" if it contains a smaller identity template,
        meaning it's not a minimal irreducible representative.
        
        Args:
            reductors: DimGroup of smaller circuits to check as subcircuits.
        """
        assert reductors._width == self._width
        assert reductors._gate_count <= self._gate_count
        irreducible = [
            circ for circ in self._circuits if not circ.reducible(reductors._circuits)
        ]
        self._circuits = irreducible

    def remove_duplicates(self):
        """Remove duplicate circuits from the group."""
        self._circuits = Circuit.filter_duplicates(self._circuits)
