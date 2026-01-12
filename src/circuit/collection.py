"""Collection of Identity Circuit Templates.

A Collection is a 2D grid of DimGroups, indexed by [width][gate_count].
It provides operations for:
- Loading/storing circuit databases
- Extending circuits with empty/full control lines
- Removing reducible circuits (those containing smaller identities)

File format:
    h <max_width> <max_gc>      # Header
    c <width> <gc>              # Circuit start
    <target> <ctrl1> <ctrl2>... # Gate (one per line, gc lines total)

Example:
    >>> coll = Collection(max_width=5, max_gate_count=8)
    >>> coll.from_file("identities.txt")
    >>> coll.fill_empty_line_extensions()
    >>> coll.remove_reducibles()
"""
from circuit.dim_group import DimGroup
from circuit.circuit import Circuit
from itertools import product
from copy import copy


class Collection:
    """2D grid of DimGroups indexed by [width][gate_count].
    
    Provides operations for building and manipulating circuit databases,
    including extension to larger widths and reducibility filtering.
    
    Attributes:
        _max_width: Maximum wire count.
        _max_gate_count: Maximum gate count.
        _groups: 2D list of DimGroups, _groups[width][gc].
    """
    def __init__(self, max_width: int, max_gate_count: int):
        """Create a Collection with empty DimGroups for all dimension pairs."""
        self._max_width = max_width
        self._max_gate_count = max_gate_count
        self._w_iter = range(max_width + 1)
        self._gc_iter = range(max_gate_count + 1)
        self._group_ids_iter = product(self._w_iter, self._gc_iter)
        self._groups = [
            [DimGroup(width, gc) for gc in self._gc_iter] for width in self._w_iter
        ]

    def __len__(self) -> int:
        return len(self._groups)

    def __getitem__(self, key: int) -> list[DimGroup]:
        return self._groups[key]

    def __str__(self) -> str:
        string = ""
        for width, gc in copy(self._group_ids_iter):
            dimg = self[width][gc]
            string += f"({width}, {gc}): {len(dimg)}\n"
        return string

    def fill_empty_line_extensions(self) -> "Collection":
        """Extend all circuits by adding spectator wires up to max_width.
        
        For each circuit, generates versions with additional wires that
        no gate touches. Works for any MCT gate (NOT, CNOT, Toffoli, etc.).
        """
        extensions = self._empty_line_extensions()
        self.join(extensions)
        return self

    def fill_full_line_extensions(self) -> "Collection":
        """Extend all circuits by adding control wires up to max_width.
        
        For each circuit, generates versions where new wires are added as
        controls to ALL gates. Example: NOT→CNOT→Toffoli→4-controlled-X.
        Only works for NCT (not ECA57, which has fixed 2 controls).
        """
        extensions = self._full_line_extensions()
        self.join(extensions)
        return self

    def remove_reducibles(self) -> "Collection":
        """Remove circuits containing smaller identity templates as subcircuits.
        
        For each (width, gc), uses templates at (width, smaller_gc) as reductors.
        A circuit is reducible if it contains a smaller identity - meaning
        it's not a minimal/irreducible representative.
        """
        for width, reducing_gc in copy(self._group_ids_iter):
            print(f"  -- RMD({width}, {reducing_gc})")
            reducing_dg = self[width][reducing_gc]
            for reducted_gc in range(reducing_gc + 1, self._max_gate_count + 1):
                reducted_dg = self[width][reducted_gc]
                reducted_dg.remove_reducibles(reducing_dg)
        return self

    def remove_duplicates(self) -> "Collection":
        """Remove duplicate circuits from all DimGroups."""
        for width, gc in copy(self._group_ids_iter):
            print(f"  -- RMD({width}, {gc})")
            self[width][gc].remove_duplicates()
        return self

    def _empty_line_extensions(self) -> "Collection":
        """Internal: compute all empty-line extensions without joining."""
        extensions = Collection(self._max_width, self._max_gate_count)
        for width, gc in copy(self._group_ids_iter):
            print(f"  -- FEL({width}, {gc})")
            dimgroup = self[width][gc]
            for circ in dimgroup:
                for target_width in range(width + 1, self._max_width + 1):
                    new_extensions = circ.empty_line_extensions(target_width)
                    extensions[target_width][gc].extend(new_extensions)
        return extensions

    def _full_line_extensions(self) -> "Collection":
        """Internal: compute all full-line extensions without joining."""
        extensions = Collection(self._max_width, self._max_gate_count)
        for width, gc in copy(self._group_ids_iter):
            print(f"  -- FFL({width}, {gc})")
            dimgroup = self[width][gc]
            for circ in dimgroup:
                for target_width in range(width + 1, self._max_width + 1):
                    new_extensions = circ.full_line_extensions(target_width)
                    extensions[target_width][gc].extend(new_extensions)
        return extensions

    def _validate_collection(self, other: "Collection") -> None:
        assert (self._max_width, self._max_gate_count) == (
            other._max_width,
            other._max_gate_count,
        )

    def join(self, other: "Collection") -> None:
        """Merge another Collection's circuits into this one."""
        self._validate_collection(other)
        for width, gc in copy(self._group_ids_iter):
            self[width][gc].join(other[width][gc])

    def from_file(self, file_name: str):
        """Load circuits from file and add to this Collection."""
        with open(file_name, 'r') as file:
            for line in file:
                parts = line.strip().split(' ')
                if not parts or parts == ['']:
                    continue
                
                cmd = parts[0]
                if cmd == "h" and len(parts) == 3:
                    _, max_width, max_gc = parts
                    assert int(max_width) == self._max_width
                    assert int(max_gc) == self._max_gate_count
                elif cmd == "c" and len(parts) == 3:
                    _, width, gc = parts
                    width = int(width)
                    gc = int(gc)
                    assert width <= self._max_width
                    assert gc <= self._max_gate_count
                    circuit = Circuit(width)
                    for _ in range(gc):
                        target, *controls = file.readline().strip().split(' ')
                        circuit.mcx([int(c) for c in controls], int(target))
                    self[width][gc].append(circuit)
                else:
                    pass
        return self
