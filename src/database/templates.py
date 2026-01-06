"""Template storage for LMDB database.

Provides TemplateRecord serialization and high-level template operations.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional, Iterator, Any

from database.lmdb_env import TemplateDBEnv
from database.basis import GateBasis, ECA57Basis, BASIS_ECA57


class OriginKind(IntEnum):
    """How a template was generated."""
    SAT = 1
    UNROLL = 2


@dataclass
class TemplateRecord:
    """Record for a stored template.
    
    Attributes:
        template_id: Unique monotonic ID
        basis_id: Gate basis (1=ECA57, 2=MCT, etc.)
        width: Number of wires
        gate_count: Number of gates
        canonical_hash: 32-byte canonical hash
        family_hash: 32-byte family hash (groups variants)
        origin: How this template was generated
        origin_template_id: If unrolled, the source template ID
        unroll_ops: Bitfield of unroll operations applied
        gates_encoded: Packed gate bytes
    """
    template_id: int
    basis_id: int
    width: int
    gate_count: int
    canonical_hash: bytes
    family_hash: bytes
    origin: OriginKind
    origin_template_id: Optional[int] = None
    unroll_ops: int = 0
    gates_encoded: bytes = b""
    
    def to_bytes(self) -> bytes:
        """Serialize to bytes for storage.
        
        Format:
            template_id: u64
            basis_id: u8
            width: u8
            gate_count: u16
            canonical_hash: 32 bytes
            family_hash: 32 bytes
            origin: u8
            origin_template_id: u64 (0 if None)
            unroll_ops: u32
            gates_len: u16
            gates_encoded: variable
        """
        origin_tid = self.origin_template_id or 0
        
        header = struct.pack(
            "<QBBH32s32sBQIH",
            self.template_id,
            self.basis_id,
            self.width,
            self.gate_count,
            self.canonical_hash,
            self.family_hash,
            self.origin.value,
            origin_tid,
            self.unroll_ops,
            len(self.gates_encoded),
        )
        return header + self.gates_encoded
    
    @classmethod
    def from_bytes(cls, data: bytes) -> "TemplateRecord":
        """Deserialize from bytes."""
        # Header is 84 bytes fixed
        header_size = 8 + 1 + 1 + 2 + 32 + 32 + 1 + 8 + 4 + 2  # = 91 bytes
        
        (template_id, basis_id, width, gate_count,
         canonical_hash, family_hash, origin_val,
         origin_tid, unroll_ops, gates_len) = struct.unpack(
            "<QBBH32s32sBQIH", data[:header_size]
        )
        
        gates_encoded = data[header_size:header_size + gates_len]
        
        return cls(
            template_id=template_id,
            basis_id=basis_id,
            width=width,
            gate_count=gate_count,
            canonical_hash=canonical_hash,
            family_hash=family_hash,
            origin=OriginKind(origin_val),
            origin_template_id=origin_tid if origin_tid != 0 else None,
            unroll_ops=unroll_ops,
            gates_encoded=gates_encoded,
        )


def encode_gates_eca57(gates: list) -> bytes:
    """Encode ECA57 gates to packed bytes.
    
    Each gate is 3 bytes: (target, ctrl1, ctrl2)
    """
    result = bytearray()
    for gate in gates:
        if isinstance(gate, tuple):
            t, c1, c2 = gate[:3]
        elif hasattr(gate, 'target'):
            t, c1, c2 = gate.target, gate.ctrl1, gate.ctrl2
        else:
            raise TypeError(f"Unknown gate format: {type(gate)}")
        result.extend([t, c1, c2])
    return bytes(result)


def decode_gates_eca57(data: bytes) -> list[tuple[int, int, int]]:
    """Decode packed ECA57 gates.
    
    Returns list of (target, ctrl1, ctrl2) tuples.
    """
    gates = []
    for i in range(0, len(data), 3):
        t, c1, c2 = data[i], data[i+1], data[i+2]
        gates.append((t, c1, c2))
    return gates


class TemplateStore:
    """High-level template storage API.
    
    Usage:
        store = TemplateStore(env, ECA57Basis())
        
        # Insert template
        record = store.insert_template(gates, width, origin=OriginKind.SAT)
        
        # Lookup
        found = store.get_by_hash(width, gate_count, canonical_hash)
        
        # Enumerate
        for record in store.iter_by_dims(width, gate_count):
            print(record)
    """
    
    def __init__(self, env: TemplateDBEnv, basis: GateBasis):
        self.env = env
        self.basis = basis
    
    def insert_template(
        self,
        gates: list,
        width: int,
        origin: OriginKind = OriginKind.SAT,
        origin_template_id: Optional[int] = None,
        unroll_ops: int = 0,
        family_hash: Optional[bytes] = None,
    ) -> Optional[TemplateRecord]:
        """Insert a template into the database.
        
        Args:
            gates: List of gates in circuit order.
            width: Number of wires.
            origin: How this template was generated.
            origin_template_id: If unrolled, source template ID.
            unroll_ops: Bitfield of unroll operations.
            family_hash: Optional family hash (defaults to canonical hash).
            
        Returns:
            TemplateRecord if inserted, None if duplicate.
        """
        # Canonicalize
        canonical_gates, canonical_hash = self.basis.canonicalize(gates, width)
        gate_count = len(gates)
        
        # Encode gates
        if self.basis.basis_id == BASIS_ECA57:
            gates_encoded = encode_gates_eca57(canonical_gates)
        else:
            raise NotImplementedError(f"Gate encoding for basis {self.basis.basis_id}")
        
        # Use canonical hash as family hash if not provided
        if family_hash is None:
            family_hash = canonical_hash
        
        with self.env.write_txn() as txn:
            # Check for duplicate
            existing = self.env.get_template(
                txn, self.basis.basis_id, width, gate_count, canonical_hash
            )
            if existing is not None:
                return None  # Duplicate
            
            # Get new template ID
            template_id = self.env.increment_template_count(txn)
            
            # Create record
            record = TemplateRecord(
                template_id=template_id,
                basis_id=self.basis.basis_id,
                width=width,
                gate_count=gate_count,
                canonical_hash=canonical_hash,
                family_hash=family_hash,
                origin=origin,
                origin_template_id=origin_template_id,
                unroll_ops=unroll_ops,
                gates_encoded=gates_encoded,
            )
            
            # Store in templates_by_hash
            record_bytes = record.to_bytes()
            self.env.put_template(
                txn, self.basis.basis_id, width, gate_count, 
                canonical_hash, record_bytes
            )
            
            # Add to dims index
            self.env.put_template_dims_index(
                txn, self.basis.basis_id, width, gate_count,
                template_id, canonical_hash
            )
            
            # Add to family
            self.env.add_to_family(txn, self.basis.basis_id, family_hash, template_id)
            
            return record
    
    def get_by_hash(
        self, width: int, gate_count: int, canonical_hash: bytes
    ) -> Optional[TemplateRecord]:
        """Get template by canonical hash."""
        with self.env.read_txn() as txn:
            data = self.env.get_template(
                txn, self.basis.basis_id, width, gate_count, canonical_hash
            )
            if data is None:
                return None
            return TemplateRecord.from_bytes(data)
    
    def iter_by_dims(self, width: int, gate_count: int) -> Iterator[TemplateRecord]:
        """Iterate all templates for given dimensions."""
        with self.env.read_txn() as txn:
            for template_id, canonical_hash in self.env.iter_templates_by_dims(
                txn, self.basis.basis_id, width, gate_count
            ):
                data = self.env.get_template(
                    txn, self.basis.basis_id, width, gate_count, canonical_hash
                )
                if data:
                    yield TemplateRecord.from_bytes(data)
    
    def count_by_dims(self, width: int, gate_count: int) -> int:
        """Count templates for given dimensions."""
        count = 0
        with self.env.read_txn() as txn:
            for _ in self.env.iter_templates_by_dims(
                txn, self.basis.basis_id, width, gate_count
            ):
                count += 1
        return count
    
    def get_family_members(self, family_hash: bytes) -> list[int]:
        """Get all template IDs in a family."""
        with self.env.read_txn() as txn:
            return self.env.get_family_members(txn, self.basis.basis_id, family_hash)
