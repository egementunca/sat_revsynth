"""LMDB environment wrapper for template/witness database.

Provides a unified interface to LMDB with multiple named databases:
- meta: schema version, basis info, canonicalization version
- templates_by_hash: exact lookup by canonical hash
- template_families: group variants by family hash
- templates_by_dims: enumerate by (width, gate_count)
- witnesses_by_hash: witness storage
- witness_prefilter: k-gram token -> witness_id mapping
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Optional, Iterator, Any
from dataclasses import dataclass
from contextlib import contextmanager

import lmdb


# Database names
DB_META = b"meta"
DB_TEMPLATES_BY_HASH = b"templates_by_hash"
DB_TEMPLATE_FAMILIES = b"template_families"
DB_TEMPLATES_BY_DIMS = b"templates_by_dims"
DB_WITNESSES_BY_HASH = b"witnesses_by_hash"
DB_WITNESS_PREFILTER = b"witness_prefilter"

# Schema version
SCHEMA_VERSION = 1
CANONICALIZATION_VERSION = 1


@dataclass
class LMDBConfig:
    """Configuration for LMDB environment."""
    map_size: int = 10 * 1024 * 1024 * 1024  # 10 GB default
    max_dbs: int = 10
    readonly: bool = False


class TemplateDBEnv:
    """LMDB environment for template/witness storage.
    
    Usage:
        env = TemplateDBEnv("path/to/db")
        with env.write_txn() as txn:
            env.put_meta(txn, "key", b"value")
        
        with env.read_txn() as txn:
            value = env.get_meta(txn, "key")
    """
    
    def __init__(self, path: str | Path, config: Optional[LMDBConfig] = None):
        """Initialize LMDB environment.
        
        Args:
            path: Directory path for LMDB files.
            config: Optional configuration.
        """
        self.path = Path(path)
        self.config = config or LMDBConfig()
        
        # Create directory if needed
        self.path.mkdir(parents=True, exist_ok=True)
        
        # Open environment
        self._env = lmdb.open(
            str(self.path),
            map_size=self.config.map_size,
            max_dbs=self.config.max_dbs,
            readonly=self.config.readonly,
        )
        
        # Open named databases
        self._dbs = {}
        if not self.config.readonly:
            with self._env.begin(write=True) as txn:
                for db_name in [
                    DB_META,
                    DB_TEMPLATES_BY_HASH,
                    DB_TEMPLATE_FAMILIES,
                    DB_TEMPLATES_BY_DIMS,
                    DB_WITNESSES_BY_HASH,
                    DB_WITNESS_PREFILTER,
                ]:
                    self._dbs[db_name] = self._env.open_db(db_name, txn=txn)
                
                # Initialize meta if new
                self._init_meta(txn)
        else:
            with self._env.begin() as txn:
                for db_name in [
                    DB_META,
                    DB_TEMPLATES_BY_HASH,
                    DB_TEMPLATE_FAMILIES,
                    DB_TEMPLATES_BY_DIMS,
                    DB_WITNESSES_BY_HASH,
                    DB_WITNESS_PREFILTER,
                ]:
                    self._dbs[db_name] = self._env.open_db(db_name, txn=txn)
    
    def _init_meta(self, txn):
        """Initialize meta database if empty."""
        meta_db = self._dbs[DB_META]
        
        # Check if already initialized
        version = txn.get(b"schema_version", db=meta_db)
        if version is None:
            # First time initialization
            txn.put(b"schema_version", struct.pack("<I", SCHEMA_VERSION), db=meta_db)
            txn.put(b"canonicalization_version", struct.pack("<I", CANONICALIZATION_VERSION), db=meta_db)
            txn.put(b"basis", b"eca57", db=meta_db)
            txn.put(b"template_count", struct.pack("<Q", 0), db=meta_db)
            txn.put(b"witness_count", struct.pack("<Q", 0), db=meta_db)
    
    def close(self):
        """Close the environment."""
        self._env.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    @contextmanager
    def read_txn(self):
        """Context manager for read transaction."""
        with self._env.begin(write=False) as txn:
            yield txn
    
    @contextmanager
    def write_txn(self):
        """Context manager for write transaction."""
        with self._env.begin(write=True) as txn:
            yield txn
    
    # -------------------------------------------------------------------------
    # Meta operations
    # -------------------------------------------------------------------------
    
    def get_meta(self, txn, key: str) -> Optional[bytes]:
        """Get value from meta database."""
        return txn.get(key.encode(), db=self._dbs[DB_META])
    
    def put_meta(self, txn, key: str, value: bytes):
        """Put value in meta database.
        
        Args:
            txn: LMDB write transaction.
            key: Meta key string.
            value: Value bytes.
        """
        txn.put(key.encode(), value, db=self._dbs[DB_META])
    
    def get_schema_version(self, txn) -> int:
        """Get schema version."""
        data = txn.get(b"schema_version", db=self._dbs[DB_META])
        return struct.unpack("<I", data)[0] if data else 0
    
    def get_template_count(self, txn) -> int:
        """Get total template count."""
        data = txn.get(b"template_count", db=self._dbs[DB_META])
        return struct.unpack("<Q", data)[0] if data else 0
    
    def increment_template_count(self, txn) -> int:
        """Increment and return new template count."""
        current = self.get_template_count(txn)
        new_count = current + 1
        txn.put(b"template_count", struct.pack("<Q", new_count), db=self._dbs[DB_META])
        return new_count
    
    def get_witness_count(self, txn) -> int:
        """Get total witness count."""
        data = txn.get(b"witness_count", db=self._dbs[DB_META])
        return struct.unpack("<Q", data)[0] if data else 0
    
    def increment_witness_count(self, txn) -> int:
        """Increment and return new witness count."""
        current = self.get_witness_count(txn)
        new_count = current + 1
        txn.put(b"witness_count", struct.pack("<Q", new_count), db=self._dbs[DB_META])
        return new_count
    
    # -------------------------------------------------------------------------
    # Template operations
    # -------------------------------------------------------------------------
    
    def make_template_key(self, basis_id: int, width: int, gate_count: int, canonical_hash: bytes) -> bytes:
        """Create key for templates_by_hash lookup.
        
        Key format: basis_id (1) + width (1) + gate_count (2) + hash (32) = 36 bytes
        """
        return struct.pack("<BBH", basis_id, width, gate_count) + canonical_hash
    
    def get_template(self, txn, basis_id: int, width: int, gate_count: int, canonical_hash: bytes) -> Optional[bytes]:
        """Get template by canonical hash."""
        key = self.make_template_key(basis_id, width, gate_count, canonical_hash)
        return txn.get(key, db=self._dbs[DB_TEMPLATES_BY_HASH])
    
    def put_template(self, txn, basis_id: int, width: int, gate_count: int, 
                     canonical_hash: bytes, record: bytes) -> bool:
        """Put template record.
        
        Args:
            txn: LMDB write transaction.
            basis_id: Gate basis ID.
            width: Circuit width.
            gate_count: Number of gates.
            canonical_hash: Unique hash of the template.
            record: Serialized TemplateRecord bytes.
            
        Returns:
            True if inserted, False if already exists.
        """
        key = self.make_template_key(basis_id, width, gate_count, canonical_hash)
        db = self._dbs[DB_TEMPLATES_BY_HASH]
        
        # Check if exists
        if txn.get(key, db=db) is not None:
            return False
        
        txn.put(key, record, db=db)
        return True
    
    def make_dims_key(self, basis_id: int, width: int, gate_count: int, template_id: int) -> bytes:
        """Create key for templates_by_dims enumeration.
        
        Key format: basis_id (1) + width (1) + gate_count (2) + template_id (8) = 12 bytes
        """
        return struct.pack("<BBHQ", basis_id, width, gate_count, template_id)
    
    def put_template_dims_index(self, txn, basis_id: int, width: int, gate_count: int,
                                 template_id: int, canonical_hash: bytes):
        """Add template to dims index."""
        key = self.make_dims_key(basis_id, width, gate_count, template_id)
        txn.put(key, canonical_hash, db=self._dbs[DB_TEMPLATES_BY_DIMS])
    
    def iter_templates_by_dims(self, txn, basis_id: int, width: int, gate_count: int) -> Iterator[tuple[int, bytes]]:
        """Iterate templates by dimension (width, gate_count).
        
        Args:
            txn: LMDB read transaction.
            basis_id: Gate basis ID.
            width: Circuit width.
            gate_count: Number of gates.

        Yields:
            (template_id, canonical_hash) tuples
        """
        prefix = struct.pack("<BBH", basis_id, width, gate_count)
        cursor = txn.cursor(db=self._dbs[DB_TEMPLATES_BY_DIMS])
        
        if cursor.set_range(prefix):
            for key, value in cursor:
                if not key.startswith(prefix):
                    break
                # Extract template_id from key
                template_id = struct.unpack("<Q", key[4:12])[0]
                yield (template_id, value)
    
    # -------------------------------------------------------------------------
    # Family operations
    # -------------------------------------------------------------------------
    
    def make_family_key(self, basis_id: int, family_hash: bytes) -> bytes:
        """Create key for template_families lookup."""
        return struct.pack("<B", basis_id) + family_hash
    
    def add_to_family(self, txn, basis_id: int, family_hash: bytes, template_id: int):
        """Add template_id to a family."""
        key = self.make_family_key(basis_id, family_hash)
        db = self._dbs[DB_TEMPLATE_FAMILIES]
        
        # Get existing list
        existing = txn.get(key, db=db)
        if existing:
            # Append new ID
            new_value = existing + struct.pack("<Q", template_id)
        else:
            new_value = struct.pack("<Q", template_id)
        
        txn.put(key, new_value, db=db)
    
    def get_family_members(self, txn, basis_id: int, family_hash: bytes) -> list[int]:
        """Get all template_ids in a family."""
        key = self.make_family_key(basis_id, family_hash)
        data = txn.get(key, db=self._dbs[DB_TEMPLATE_FAMILIES])
        
        if not data:
            return []
        
        # Unpack list of u64
        count = len(data) // 8
        return list(struct.unpack(f"<{count}Q", data))
    
    # -------------------------------------------------------------------------
    #  Witness operations
    # -------------------------------------------------------------------------
    
    def make_witness_key(self, basis_id: int, width: int, witness_len: int, witness_hash: bytes) -> bytes:
        """Create key for witnesses_by_hash lookup.
        
        Key format: basis_id (1) + width (1) + witness_len (2) + hash (32) = 36 bytes
        """
        return struct.pack("<BBH", basis_id, width, witness_len) + witness_hash
    
    def get_witness(self, txn, basis_id: int, width: int, witness_len: int, witness_hash: bytes) -> Optional[bytes]:
        """Get witness by hash."""
        key = self.make_witness_key(basis_id, width, witness_len, witness_hash)
        return txn.get(key, db=self._dbs[DB_WITNESSES_BY_HASH])
    
    def put_witness(self, txn, basis_id: int, width: int, witness_len: int,
                    witness_hash: bytes, record: bytes) -> bool:
        """Put witness record. Returns False if already exists."""
        key = self.make_witness_key(basis_id, width, witness_len, witness_hash)
        db = self._dbs[DB_WITNESSES_BY_HASH]
        
        if txn.get(key, db=db) is not None:
            return False
        
        txn.put(key, record, db=db)
        return True
    
    def make_prefilter_key(self, basis_id: int, width: int, token_hash: int) -> bytes:
        """Create key for witness prefilter.
        
        Key format: basis_id (1) + width (1) + token_hash (8) = 10 bytes
        """
        return struct.pack("<BBQ", basis_id, width, token_hash)
    
    def add_to_prefilter(self, txn, basis_id: int, width: int, token_hash: int, witness_id: int):
        """Add witness_id to prefilter token bucket."""
        key = self.make_prefilter_key(basis_id, width, token_hash)
        db = self._dbs[DB_WITNESS_PREFILTER]
        
        existing = txn.get(key, db=db)
        if existing:
            new_value = existing + struct.pack("<Q", witness_id)
        else:
            new_value = struct.pack("<Q", witness_id)
        
        txn.put(key, new_value, db=db)
    
    def lookup_prefilter(self, txn, basis_id: int, width: int, token_hash: int) -> list[int]:
        """Lookup witness_ids by prefilter token."""
        key = self.make_prefilter_key(basis_id, width, token_hash)
        data = txn.get(key, db=self._dbs[DB_WITNESS_PREFILTER])
        
        if not data:
            return []
        
        count = len(data) // 8
        return list(struct.unpack(f"<{count}Q", data))
    
    # -------------------------------------------------------------------------
    # Stats
    # -------------------------------------------------------------------------
    
    def stats(self) -> dict:
        """Get database statistics."""
        with self.read_txn() as txn:
            return {
                "schema_version": self.get_schema_version(txn),
                "template_count": self.get_template_count(txn),
                "witness_count": self.get_witness_count(txn),
                "basis": self.get_meta(txn, "basis"),
            }
