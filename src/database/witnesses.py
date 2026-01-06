"""Witness storage and prefilter for LMDB database.

Witnesses are shortened prefixes of templates used for:
1. SAT speedups: exclude witness patterns from candidate solutions
2. Reducer speedups: quickly detect candidate windows before canonical matching
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional, Iterator, List

import blake3

from database.lmdb_env import TemplateDBEnv
from database.basis import GateBasis, ECA57Basis, BASIS_ECA57
from database.templates import TemplateRecord, decode_gates_eca57


@dataclass
class WitnessRecord:
    """Record for a stored witness.
    
    Attributes:
        witness_id: Unique monotonic ID
        basis_id: Gate basis
        width: Number of wires
        witness_len: Number of gates in witness
        witness_hash: 32-byte canonical hash
        gates_encoded: Packed gate bytes
        source_template_id: One representative source template
    """
    witness_id: int
    basis_id: int
    width: int
    witness_len: int
    witness_hash: bytes
    gates_encoded: bytes
    source_template_id: int
    
    def to_bytes(self) -> bytes:
        """Serialize to bytes for storage.
        
        Format:
            witness_id: u64
            basis_id: u8
            width: u8
            witness_len: u16
            witness_hash: 32 bytes
            source_template_id: u64
            gates_len: u16
            gates_encoded: variable
        """
        header = struct.pack(
            "<QBBH32sQH",
            self.witness_id,
            self.basis_id,
            self.width,
            self.witness_len,
            self.witness_hash,
            self.source_template_id,
            len(self.gates_encoded),
        )
        return header + self.gates_encoded
    
    @classmethod
    def from_bytes(cls, data: bytes) -> "WitnessRecord":
        """Deserialize from bytes."""
        header_size = 8 + 1 + 1 + 2 + 32 + 8 + 2  # = 54 bytes
        
        (witness_id, basis_id, width, witness_len,
         witness_hash, source_template_id, gates_len) = struct.unpack(
            "<QBBH32sQH", data[:header_size]
        )
        
        gates_encoded = data[header_size:header_size + gates_len]
        
        return cls(
            witness_id=witness_id,
            basis_id=basis_id,
            width=width,
            witness_len=witness_len,
            witness_hash=witness_hash,
            gates_encoded=gates_encoded,
            source_template_id=source_template_id,
        )


def compute_witness_length(gate_count: int) -> int:
    """Compute witness length from template gate count.
    
    witness_len = floor(GC / 2) + 1
    """
    return (gate_count // 2) + 1


def compute_kgram_tokens(gates: list, k: int, basis: GateBasis, width: int) -> List[int]:
    """Compute k-gram token hashes for prefilter.
    
    Each token is a 64-bit hash of a sliding window of k gates.
    
    Args:
        gates: Gate list.
        k: Window size (typically 2-4).
        basis: Gate basis.
        width: Circuit width.
        
    Returns:
        List of 64-bit token hashes.
    """
    if len(gates) < k:
        return []
    
    tokens = []
    for i in range(len(gates) - k + 1):
        window = gates[i:i + k]
        
        # Canonicalize window (local wire relabeling)
        _, window_hash = basis.canonicalize(window, width)
        
        # Take first 8 bytes as 64-bit token
        token = struct.unpack("<Q", window_hash[:8])[0]
        tokens.append(token)
    
    return tokens


class WitnessStore:
    """High-level witness storage API.
    
    Usage:
        store = WitnessStore(env, ECA57Basis())
        
        # Extract witnesses from templates
        store.build_witnesses_for_dims(template_store, width=4, gate_count=6)
        
        # Lookup by token
        witness_ids = store.lookup_by_token(width=4, token_hash=12345)
    """
    
    def __init__(self, env: TemplateDBEnv, basis: GateBasis, k_gram_sizes: List[int] = None):
        self.env = env
        self.basis = basis
        self.k_gram_sizes = k_gram_sizes or [2, 3]  # Default: 2-grams and 3-grams
    
    def insert_witness(
        self,
        gates: list,
        width: int,
        source_template_id: int,
    ) -> Optional[WitnessRecord]:
        """Insert a witness into the database.
        
        Args:
            gates: Witness gate list.
            width: Circuit width.
            source_template_id: Source template ID.
            
        Returns:
            WitnessRecord if inserted, None if duplicate.
        """
        witness_len = len(gates)
        
        # Canonicalize
        canonical_gates, witness_hash = self.basis.canonicalize(gates, width)
        
        # Encode gates
        if self.basis.basis_id == BASIS_ECA57:
            gates_encoded = b""
            for g in canonical_gates:
                if isinstance(g, tuple):
                    gates_encoded += bytes([g[0], g[1], g[2]])
                else:
                    gates_encoded += bytes([g.target, g.ctrl1, g.ctrl2])
        else:
            raise NotImplementedError(f"Witness encoding for basis {self.basis.basis_id}")
        
        with self.env.write_txn() as txn:
            # Check for duplicate
            existing = self.env.get_witness(
                txn, self.basis.basis_id, width, witness_len, witness_hash
            )
            if existing is not None:
                return None
            
            # Get new witness ID
            witness_id = self.env.increment_witness_count(txn)
            
            # Create record
            record = WitnessRecord(
                witness_id=witness_id,
                basis_id=self.basis.basis_id,
                width=width,
                witness_len=witness_len,
                witness_hash=witness_hash,
                gates_encoded=gates_encoded,
                source_template_id=source_template_id,
            )
            
            # Store
            self.env.put_witness(
                txn, self.basis.basis_id, width, witness_len,
                witness_hash, record.to_bytes()
            )
            
            # Add to prefilter
            for k in self.k_gram_sizes:
                tokens = compute_kgram_tokens(canonical_gates, k, self.basis, width)
                for token in tokens:
                    self.env.add_to_prefilter(
                        txn, self.basis.basis_id, width, token, witness_id
                    )
            
            return record
    
    def build_witnesses_from_template(
        self,
        template: TemplateRecord,
    ) -> Optional[WitnessRecord]:
        """Extract and insert witness from a template.
        
        Args:
            template: Template record.
            
        Returns:
            WitnessRecord if inserted, None if duplicate.
        """
        # Decode gates
        if template.basis_id == BASIS_ECA57:
            gates = decode_gates_eca57(template.gates_encoded)
        else:
            raise NotImplementedError(f"Gate decoding for basis {template.basis_id}")
        
        # Compute witness length
        witness_len = compute_witness_length(len(gates))
        
        # Extract witness (first witness_len gates)
        witness_gates = gates[:witness_len]
        
        return self.insert_witness(
            witness_gates,
            template.width,
            template.template_id,
        )
    
    def lookup_by_token(self, width: int, token_hash: int) -> List[int]:
        """Lookup witness IDs by prefilter token."""
        with self.env.read_txn() as txn:
            return self.env.lookup_prefilter(
                txn, self.basis.basis_id, width, token_hash
            )
    
    def get_by_hash(
        self, width: int, witness_len: int, witness_hash: bytes
    ) -> Optional[WitnessRecord]:
        """Get witness by hash."""
        with self.env.read_txn() as txn:
            data = self.env.get_witness(
                txn, self.basis.basis_id, width, witness_len, witness_hash
            )
            if data is None:
                return None
            return WitnessRecord.from_bytes(data)
