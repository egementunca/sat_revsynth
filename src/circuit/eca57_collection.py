"""ECA57 Collection Container.

Nested container for ECA57 circuits organized by (width, gate_count).
Collection[width][gate_count] -> ECA57DimGroup
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional
from circuit.eca57_dim_group import ECA57DimGroup


class ECA57Collection:
    """Nested container for ECA57 circuits by dimensions.
    
    Provides 2D indexing: collection[width][gate_count] -> ECA57DimGroup
    
    Example:
        >>> coll = ECA57Collection(max_width=5, max_gate_count=6)
        >>> coll[3][4] = ECA57DimGroup(3, 4)
        >>> circuits = coll[3][4]
    """
    
    def __init__(self, max_width: int, max_gate_count: int):
        """Initialize empty collection with given bounds."""
        assert max_width >= 3, "ECA57 requires at least 3 wires"
        self._max_width = max_width
        self._max_gate_count = max_gate_count
        
        # Initialize nested structure
        self._data: Dict[int, Dict[int, Optional[ECA57DimGroup]]] = {}
        for w in range(3, max_width + 1):
            self._data[w] = {}
            for gc in range(2, max_gate_count + 1):
                self._data[w][gc] = None
    
    def __getitem__(self, width: int) -> Dict[int, Optional[ECA57DimGroup]]:
        """Get subcollection for given width."""
        return self._data[width]
    
    @property
    def max_width(self) -> int:
        return self._max_width
    
    @property
    def max_gate_count(self) -> int:
        return self._max_gate_count
    
    def total_circuits(self) -> int:
        """Count total circuits across all dimensions."""
        total = 0
        for w in self._data:
            for gc in self._data[w]:
                dg = self._data[w][gc]
                if dg:
                    total += len(dg)
        return total
    
    def summary(self) -> str:
        """Return summary string of collection contents."""
        lines = [f"ECA57Collection (max_width={self._max_width}, max_gc={self._max_gate_count})"]
        for w in sorted(self._data.keys()):
            for gc in sorted(self._data[w].keys()):
                dg = self._data[w][gc]
                count = len(dg) if dg else 0
                if count > 0:
                    lines.append(f"  [{w}][{gc}]: {count} circuits")
        lines.append(f"Total: {self.total_circuits()} circuits")
        return "\n".join(lines)
    
    def save_json(self, path: Path) -> None:
        """Save collection to JSON file."""
        data = {
            "max_width": self._max_width,
            "max_gate_count": self._max_gate_count,
            "groups": {}
        }
        
        for w in self._data:
            for gc in self._data[w]:
                dg = self._data[w][gc]
                if dg and len(dg) > 0:
                    key = f"{w}_{gc}"
                    data["groups"][key] = dg.to_dict()
        
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load_json(cls, path: Path) -> "ECA57Collection":
        """Load collection from JSON file."""
        with open(path) as f:
            data = json.load(f)
        
        coll = cls(data["max_width"], data["max_gate_count"])
        
        for key, dg_data in data["groups"].items():
            w, gc = map(int, key.split("_"))
            coll._data[w][gc] = ECA57DimGroup.from_dict(dg_data)
        
        return coll
    
    def save_compact(self, path: Path) -> None:
        """Save collection in compact format (one line per circuit)."""
        with open(path, "w") as f:
            f.write(f"# ECA57Collection max_width={self._max_width} max_gc={self._max_gate_count}\n")
            for w in sorted(self._data.keys()):
                for gc in sorted(self._data[w].keys()):
                    dg = self._data[w][gc]
                    if dg and len(dg) > 0:
                        for circ in dg:
                            gates_str = ";".join(f"{g.target},{g.ctrl1},{g.ctrl2}" 
                                                for g in circ.gates())
                            f.write(f"{w},{gc}:{gates_str}\n")
    
    @classmethod
    def load_compact(cls, path: Path) -> "ECA57Collection":
        """Load collection from compact format."""
        max_w, max_gc = 3, 2
        circuits = []
        
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    # Parse header for max values
                    if "max_width=" in line:
                        parts = line.split()
                        for p in parts:
                            if p.startswith("max_width="):
                                max_w = int(p.split("=")[1])
                            elif p.startswith("max_gc="):
                                max_gc = int(p.split("=")[1])
                    continue
                
                dims, gates_str = line.split(":")
                w, gc = map(int, dims.split(","))
                max_w = max(max_w, w)
                max_gc = max(max_gc, gc)
                
                gates = []
                for g_str in gates_str.split(";"):
                    t, c1, c2 = map(int, g_str.split(","))
                    gates.append((t, c1, c2))
                circuits.append((w, gc, gates))
        
        coll = cls(max_w, max_gc)
        
        for w, gc, gates in circuits:
            if coll._data[w][gc] is None:
                coll._data[w][gc] = ECA57DimGroup(w, gc)
            from gates.eca57 import ECA57Circuit
            circ = ECA57Circuit(w)
            for t, c1, c2 in gates:
                circ.add_gate(t, c1, c2)
            coll._data[w][gc].append(circ)
        
        return coll
    
    def join(self, other: "ECA57Collection") -> None:
        """Merge another Collection's circuits into this one."""
        assert self._max_width == other._max_width
        assert self._max_gate_count == other._max_gate_count
        
        for w in self._data:
            for gc in self._data[w]:
                if other._data[w][gc]:
                    if self._data[w][gc] is None:
                        self._data[w][gc] = ECA57DimGroup(w, gc)
                    self._data[w][gc].join(other._data[w][gc])
    
    def fill_empty_line_extensions(self) -> "ECA57Collection":
        """Extend circuits by adding spectator wires up to max_width.
        
        For each circuit, generates versions with additional wires that
        no gate touches.
        """
        from gates.eca57 import ECA57Circuit
        
        extensions = ECA57Collection(self._max_width, self._max_gate_count)
        
        for w in sorted(self._data.keys()):
            for gc in sorted(self._data[w].keys()):
                dg = self._data[w][gc]
                if not dg:
                    continue
                print(f"  -- FEL({w}, {gc})")
                for circ in dg:
                    for target_width in range(w + 1, self._max_width + 1):
                        new_extensions = circ.empty_line_extensions(target_width)
                        if extensions._data[target_width][gc] is None:
                            extensions._data[target_width][gc] = ECA57DimGroup(target_width, gc)
                        extensions._data[target_width][gc].extend(new_extensions)
        
        self.join(extensions)
        return self
    
    def remove_reducibles(self) -> "ECA57Collection":
        """Remove circuits containing smaller identity templates as subcircuits."""
        for w in sorted(self._data.keys()):
            for reducing_gc in sorted(self._data[w].keys()):
                reducing_dg = self._data[w][reducing_gc]
                if not reducing_dg:
                    continue
                print(f"  -- RMR({w}, {reducing_gc})")
                for reducted_gc in range(reducing_gc + 1, self._max_gate_count + 1):
                    reducted_dg = self._data[w][reducted_gc]
                    if reducted_dg:
                        reducted_dg.remove_reducibles(reducing_dg)
        return self
    
    def remove_duplicates(self) -> "ECA57Collection":
        """Remove duplicate circuits from all DimGroups."""
        for w in sorted(self._data.keys()):
            for gc in sorted(self._data[w].keys()):
                dg = self._data[w][gc]
                if dg:
                    print(f"  -- RMD({w}, {gc})")
                    dg.remove_duplicates()
        return self
