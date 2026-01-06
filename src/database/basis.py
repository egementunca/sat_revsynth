"""Gate basis abstraction for template database.

Provides a protocol-based design for different gate types (ECA57, MCT, etc.)
with a concrete implementation for ECA57.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, TypeVar, Generic, Any, runtime_checkable
from dataclasses import dataclass

import blake3


# Basis IDs (unique per gate family)
BASIS_ECA57 = 1
BASIS_MCT = 2  # Placeholder for future


@runtime_checkable
class Gate(Protocol):
    """Protocol for gate types."""
    pass


@runtime_checkable
class GateBasis(Protocol):
    """Protocol for gate basis implementations.
    
    A gate basis defines:
    - How gates are represented
    - How to check commutativity
    - How to serialize gates for hashing
    - How to canonicalize circuits
    """
    
    @property
    def basis_id(self) -> int:
        """Unique identifier for this basis."""
        ...
    
    @property
    def name(self) -> str:
        """Human-readable name."""
        ...
    
    def invert(self, gate: Any) -> Any:
        """Return the inverse of a gate (for mirroring)."""
        ...
    
    def commutes(self, g1: Any, g2: Any) -> bool:
        """Check if two gates commute (can be swapped)."""
        ...
    
    def touched_wires(self, gate: Any) -> list[int]:
        """Return list of wires that this gate touches."""
        ...
    
    def serialize_gate(self, gate: Any) -> bytes:
        """Serialize a gate to bytes (stable, deterministic)."""
        ...
    
    def canonicalize(self, gates: list[Any], width: int) -> tuple[list[Any], bytes]:
        """Canonicalize a circuit and return (canonical_gates, hash).
        
        Canonicalization must be:
        - Deterministic
        - Invariant under wire relabeling
        - Stable across versions (bump canonicalization_version if changed)
        
        Returns:
            Tuple of (canonicalized gate list, 32-byte BLAKE3 hash)
        """
        ...


class ECA57Basis:
    """ECA57 gate basis implementation.
    
    ECA57 gates have:
    - target wire
    - ctrl1 (positive control)
    - ctrl2 (negative control)
    
    Two ECA57 gates commute iff they share no wires.
    """
    
    @property
    def basis_id(self) -> int:
        return BASIS_ECA57
    
    @property
    def name(self) -> str:
        return "eca57"
    
    def invert(self, gate) -> Any:
        """ECA57 gates are self-inverse."""
        return gate
    
    def commutes(self, g1, g2) -> bool:
        """Two ECA57 gates commute iff they share no wires."""
        wires1 = set(self.touched_wires(g1))
        wires2 = set(self.touched_wires(g2))
        return wires1.isdisjoint(wires2)
    
    def touched_wires(self, gate) -> list[int]:
        """Return [target, ctrl1, ctrl2]."""
        # Handle both tuple format and object format
        if isinstance(gate, tuple):
            return list(gate[:3])
        elif hasattr(gate, 'target'):
            return [gate.target, gate.ctrl1, gate.ctrl2]
        else:
            raise TypeError(f"Unknown gate format: {type(gate)}")
    
    def serialize_gate(self, gate) -> bytes:
        """Serialize ECA57 gate to 3 bytes (target, ctrl1, ctrl2)."""
        if isinstance(gate, tuple):
            t, c1, c2 = gate[:3]
        elif hasattr(gate, 'target'):
            t, c1, c2 = gate.target, gate.ctrl1, gate.ctrl2
        else:
            raise TypeError(f"Unknown gate format: {type(gate)}")
        
        # Pack as 3 bytes (supports up to 256 wires)
        return bytes([t, c1, c2])
    
    def canonicalize(self, gates: list, width: int) -> tuple[list, bytes]:
        """Canonicalize ECA57 circuit.
        
        Wire relabeling: first-occurrence order.
        1. Scan gates left-to-right
        2. Map first new wire seen to 0, next to 1, etc.
        3. Rewrite all gates under this mapping
        4. Hash with BLAKE3
        """
        if not gates:
            # Empty circuit
            hasher = blake3.blake3()
            hasher.update(b"eca57:0:")
            return [], hasher.digest()
        
        # Build wire relabeling based on first occurrence
        wire_map = {}
        next_wire = 0
        
        for gate in gates:
            for wire in self.touched_wires(gate):
                if wire not in wire_map:
                    wire_map[wire] = next_wire
                    next_wire += 1
        
        # Remap gates
        canonical_gates = []
        for gate in gates:
            wires = self.touched_wires(gate)
            new_t = wire_map[wires[0]]
            new_c1 = wire_map[wires[1]]
            new_c2 = wire_map[wires[2]]
            
            # Create canonical tuple representation
            canonical_gates.append((new_t, new_c1, new_c2))
        
        # Build hash
        hasher = blake3.blake3()
        hasher.update(f"eca57:{width}:{len(gates)}:".encode())
        
        for g in canonical_gates:
            hasher.update(self.serialize_gate(g))
        
        return canonical_gates, hasher.digest()


class MCTBasis:
    """Placeholder for MCT (Toffoli) gate basis.
    
    TODO: Implement when needed.
    """
    
    @property
    def basis_id(self) -> int:
        return BASIS_MCT
    
    @property
    def name(self) -> str:
        return "mct"
    
    def invert(self, gate) -> Any:
        raise NotImplementedError("MCT basis not yet implemented")
    
    def commutes(self, g1, g2) -> bool:
        raise NotImplementedError("MCT basis not yet implemented")
    
    def touched_wires(self, gate) -> list[int]:
        raise NotImplementedError("MCT basis not yet implemented")
    
    def serialize_gate(self, gate) -> bytes:
        raise NotImplementedError("MCT basis not yet implemented")
    
    def canonicalize(self, gates: list, width: int) -> tuple[list, bytes]:
        raise NotImplementedError("MCT basis not yet implemented")


def get_basis(name: str) -> GateBasis:
    """Get basis implementation by name."""
    if name == "eca57":
        return ECA57Basis()
    elif name == "mct":
        return MCTBasis()
    else:
        raise ValueError(f"Unknown basis: {name}")


def canonical_hash_256(gates: list, width: int, basis: GateBasis) -> bytes:
    """Convenience function to get canonical hash of a circuit.
    
    Args:
        gates: List of gates in circuit order.
        width: Number of wires in circuit.
        basis: Gate basis implementation.
        
    Returns:
        32-byte canonical hash.
    """
    _, hash_bytes = basis.canonicalize(gates, width)
    return hash_bytes
