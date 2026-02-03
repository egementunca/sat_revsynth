"""Skeleton Chain Database Builder.

This module creates LMDB databases of skeleton chain identity circuits
indexed by GatePair taxonomy for use with local_mixing's pair replacement.

Database format (compatible with local_mixing/Rust):
- Database name: ids_n{n} where n is the circuit width
- Key: bincode-serialized GatePair (12 bytes)
- Value: bincode-serialized Vec<Vec<u8>> (list of circuit blobs)

Each circuit blob is a flat array: [t0, c1_0, c2_0, t1, c1_1, c2_1, ...]
where each gate is 3 bytes [target, ctrl1, ctrl2].
"""
from __future__ import annotations

import struct
import random
import time
from enum import IntEnum
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

import lmdb

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from gates.eca57 import ECA57Circuit
from synthesizers.skeleton_chain_api import (
    synthesize_skeleton_chain,
    limited_unroll,
    verify_skeleton_chain,
)


# -----------------------------------------------------------------------------
# CollisionType and GatePair (matches Rust definitions in replace.rs)
# -----------------------------------------------------------------------------

class CollisionType(IntEnum):
    """How a wire of gate2 relates to gate1.

    Must match Rust enum order for bincode compatibility:
    - OnActive = 0: wire hits gate1's target
    - OnCtrl1 = 1: wire hits gate1's ctrl1
    - OnCtrl2 = 2: wire hits gate1's ctrl2
    - OnNew = 3: wire doesn't touch any of gate1's wires
    """
    OnActive = 0
    OnCtrl1 = 1
    OnCtrl2 = 2
    OnNew = 3


@dataclass(frozen=True)
class GatePair:
    """Taxonomy of two adjacent gates.

    Describes how gate2's wires relate to gate1:
    - a: where gate2's target lands on gate1
    - c1: where gate2's ctrl1 lands on gate1
    - c2: where gate2's ctrl2 lands on gate1

    For skeleton chains, at least one of (a, c1, c2) must be non-OnNew
    (the gates must collide/not commute).
    """
    a: CollisionType   # gate2's target -> gate1
    c1: CollisionType  # gate2's ctrl1 -> gate1
    c2: CollisionType  # gate2's ctrl2 -> gate1

    def is_collision(self) -> bool:
        """Returns True if the gates collide (don't commute)."""
        # Gates collide if target of one hits control of other
        # For gate2's target hitting gate1's controls: a in {OnCtrl1, OnCtrl2}
        # For gate1's target hitting gate2's controls: c1 == OnActive or c2 == OnActive
        return (
            self.a == CollisionType.OnCtrl1 or
            self.a == CollisionType.OnCtrl2 or
            self.c1 == CollisionType.OnActive or
            self.c2 == CollisionType.OnActive
        )

    def is_none(self) -> bool:
        """Returns True if all collision types are OnNew (no collision)."""
        return (
            self.a == CollisionType.OnNew and
            self.c1 == CollisionType.OnNew and
            self.c2 == CollisionType.OnNew
        )

    def to_bytes(self) -> bytes:
        """Serialize to bincode format (12 bytes).

        Rust bincode serializes each enum variant as a u32 (4 bytes, little-endian).
        Total: 3 * 4 = 12 bytes.
        """
        return struct.pack("<III", int(self.a), int(self.c1), int(self.c2))

    @classmethod
    def from_bytes(cls, data: bytes) -> "GatePair":
        """Deserialize from bincode format."""
        a, c1, c2 = struct.unpack("<III", data[:12])
        return cls(CollisionType(a), CollisionType(c1), CollisionType(c2))

    def __repr__(self) -> str:
        return f"GatePair({self.a.name}, {self.c1.name}, {self.c2.name})"


def get_collision_type(g1: tuple[int, int, int], pin: int) -> CollisionType:
    """Get collision type for a pin relative to gate1.

    Args:
        g1: Gate 1 as (target, ctrl1, ctrl2)
        pin: Wire index to check

    Returns:
        CollisionType indicating where pin lands on g1
    """
    if pin == g1[0]:
        return CollisionType.OnActive
    elif pin == g1[1]:
        return CollisionType.OnCtrl1
    elif pin == g1[2]:
        return CollisionType.OnCtrl2
    else:
        return CollisionType.OnNew


def gate_pair_taxonomy(g1: tuple[int, int, int], g2: tuple[int, int, int]) -> GatePair:
    """Compute taxonomy for a pair of gates.

    Args:
        g1: First gate as (target, ctrl1, ctrl2)
        g2: Second gate as (target, ctrl1, ctrl2)

    Returns:
        GatePair describing how g2's wires relate to g1
    """
    return GatePair(
        a=get_collision_type(g1, g2[0]),
        c1=get_collision_type(g1, g2[1]),
        c2=get_collision_type(g1, g2[2]),
    )


def circuit_to_blob(circuit: ECA57Circuit) -> bytes:
    """Convert circuit to blob format.

    Each gate becomes 3 bytes: [target, ctrl1, ctrl2]
    """
    blob = bytearray()
    for gate in circuit.gates():
        blob.append(gate.target)
        blob.append(gate.ctrl1)
        blob.append(gate.ctrl2)
    return bytes(blob)


def serialize_circuit_list(circuits: list[bytes]) -> bytes:
    """Serialize a list of circuit blobs to bincode Vec<Vec<u8>> format.

    Bincode Vec format:
    - Length as u64 (8 bytes, little-endian)
    - For each element: length as u64 + data bytes
    """
    result = bytearray()
    # Vec length
    result.extend(struct.pack("<Q", len(circuits)))
    # Each circuit blob
    for blob in circuits:
        result.extend(struct.pack("<Q", len(blob)))
        result.extend(blob)
    return bytes(result)


def deserialize_circuit_list(data: bytes) -> list[bytes]:
    """Deserialize bincode Vec<Vec<u8>> format to list of blobs."""
    offset = 0
    # Vec length
    count = struct.unpack("<Q", data[offset:offset+8])[0]
    offset += 8

    circuits = []
    for _ in range(count):
        blob_len = struct.unpack("<Q", data[offset:offset+8])[0]
        offset += 8
        blob = data[offset:offset+blob_len]
        offset += blob_len
        circuits.append(blob)

    return circuits


# -----------------------------------------------------------------------------
# Database Builder
# -----------------------------------------------------------------------------

@dataclass
class SkeletonDBConfig:
    """Configuration for skeleton chain database."""
    map_size: int = 50 * 1024 * 1024 * 1024  # 50 GB default (user said 10s of GB is OK)
    max_dbs: int = 20  # One per wire count

    # Synthesis parameters
    min_wires: int = 4
    max_wires: int = 16
    gates_per_wire: int = 2  # gates = wires * gates_per_wire

    # Unrolling parameters
    max_circuits_per_taxonomy: int = 1000  # Max circuits per GatePair key
    max_permutations: int = 100  # Permutation sampling limit

    # Generation limits
    max_synthesis_attempts: int = 100  # Max attempts per (wires, gates) pair
    target_taxonomies_per_width: int = 50  # Target distinct taxonomies per width


class SkeletonDBBuilder:
    """Builder for skeleton chain databases.

    Creates LMDB databases compatible with local_mixing's pair replacement system.

    Usage:
        builder = SkeletonDBBuilder("path/to/db")
        builder.build(min_wires=4, max_wires=12)
        builder.close()
    """

    def __init__(self, path: str | Path, config: Optional[SkeletonDBConfig] = None):
        """Initialize database builder.

        Args:
            path: Directory path for LMDB files.
            config: Optional configuration.
        """
        self.path = Path(path)
        self.config = config or SkeletonDBConfig()

        # Create directory
        self.path.mkdir(parents=True, exist_ok=True)

        # Open environment
        self._env = lmdb.open(
            str(self.path),
            map_size=self.config.map_size,
            max_dbs=self.config.max_dbs,
        )

        # Cache of opened databases
        self._dbs: dict[str, object] = {}

        # Statistics
        self.stats = {
            "circuits_added": 0,
            "taxonomies_found": 0,
            "synthesis_calls": 0,
        }

    def _get_db(self, width: int):
        """Get or create database for a wire width."""
        db_name = f"ids_n{width}"
        if db_name not in self._dbs:
            self._dbs[db_name] = self._env.open_db(db_name.encode())
        return self._dbs[db_name]

    def close(self):
        """Close the environment."""
        self._env.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def add_skeleton(self, circuit: ECA57Circuit, width: int) -> Optional[GatePair]:
        """Add a skeleton chain to the database.

        Args:
            circuit: Skeleton chain circuit to add.
            width: Circuit width.

        Returns:
            GatePair taxonomy if added, None if circuit has < 2 gates.
        """
        gates = list(circuit.gates())
        if len(gates) < 2:
            return None

        # Compute taxonomy from first two gates
        g1 = (gates[0].target, gates[0].ctrl1, gates[0].ctrl2)
        g2 = (gates[1].target, gates[1].ctrl1, gates[1].ctrl2)
        taxonomy = gate_pair_taxonomy(g1, g2)

        # Convert circuit to blob
        blob = circuit_to_blob(circuit)

        # Add to database
        db = self._get_db(width)
        key = taxonomy.to_bytes()

        with self._env.begin(write=True) as txn:
            # Get existing circuits for this taxonomy
            existing = txn.get(key, db=db)

            if existing:
                circuits = deserialize_circuit_list(existing)
                # Check limit
                if len(circuits) >= self.config.max_circuits_per_taxonomy:
                    return taxonomy  # Already at limit
                # Check for duplicates
                if blob in circuits:
                    return taxonomy
                circuits.append(blob)
            else:
                circuits = [blob]
                self.stats["taxonomies_found"] += 1

            # Serialize and store
            value = serialize_circuit_list(circuits)
            txn.put(key, value, db=db)
            self.stats["circuits_added"] += 1

        return taxonomy

    def add_skeleton_variants(self, skeleton: ECA57Circuit, width: int,
                              max_variants: int = 100) -> int:
        """Add a skeleton chain and its variants to the database.

        Args:
            skeleton: Base skeleton chain.
            width: Circuit width.
            max_variants: Maximum variants to generate.

        Returns:
            Number of circuits added.
        """
        # Generate variants using limited unroll
        variants = limited_unroll(
            skeleton,
            max_circuits=max_variants,
            max_permutations=self.config.max_permutations,
            use_skeleton_mode=True,
        )

        added = 0
        for variant in variants:
            if self.add_skeleton(variant, width):
                added += 1

        return added

    def synthesize_and_add(self, wires: int, gates: int,
                           max_variants: int = 100,
                           solver_name: str = "glucose4") -> tuple[int, Optional[GatePair]]:
        """Synthesize a skeleton chain and add it with variants.

        Args:
            wires: Number of wires.
            gates: Number of gates.
            max_variants: Maximum variants per skeleton.
            solver_name: SAT solver to use.

        Returns:
            (circuits_added, taxonomy) tuple.
        """
        self.stats["synthesis_calls"] += 1

        skeleton = synthesize_skeleton_chain(
            wires=wires,
            gates=gates,
            solver_name=solver_name,
        )

        if skeleton is None:
            return (0, None)

        # Verify it's a valid skeleton
        if not verify_skeleton_chain(skeleton):
            return (0, None)

        if not skeleton.is_identity():
            return (0, None)

        # Get taxonomy
        gates_list = list(skeleton.gates())
        if len(gates_list) < 2:
            return (0, None)

        g1 = (gates_list[0].target, gates_list[0].ctrl1, gates_list[0].ctrl2)
        g2 = (gates_list[1].target, gates_list[1].ctrl1, gates_list[1].ctrl2)
        taxonomy = gate_pair_taxonomy(g1, g2)

        # Add variants
        added = self.add_skeleton_variants(skeleton, wires, max_variants)

        return (added, taxonomy)

    def build(self,
              min_wires: Optional[int] = None,
              max_wires: Optional[int] = None,
              gates_per_wire: Optional[int] = None,
              target_taxonomies: Optional[int] = None,
              max_attempts: Optional[int] = None,
              max_variants: int = 100,
              solver_name: str = "glucose4",
              progress_callback: Optional[callable] = None) -> dict:
        """Build the skeleton chain database.

        Synthesizes skeleton chains for various wire widths and gate counts,
        generating variants and indexing by taxonomy.

        Args:
            min_wires: Minimum wire count (default: config value).
            max_wires: Maximum wire count (default: config value).
            gates_per_wire: Gates multiplier (default: config value).
            target_taxonomies: Target distinct taxonomies per width.
            max_attempts: Maximum synthesis attempts per width.
            max_variants: Maximum variants per skeleton.
            solver_name: SAT solver name.
            progress_callback: Optional callback(width, attempt, taxonomies_found).

        Returns:
            Statistics dictionary.
        """
        min_wires = min_wires or self.config.min_wires
        max_wires = max_wires or self.config.max_wires
        gates_per_wire = gates_per_wire or self.config.gates_per_wire
        target_taxonomies = target_taxonomies or self.config.target_taxonomies_per_width
        max_attempts = max_attempts or self.config.max_synthesis_attempts

        start_time = time.time()

        for width in range(min_wires, max_wires + 1):
            base_gates = width * gates_per_wire
            taxonomies_found: set[GatePair] = set()
            attempts = 0

            # Try different gate counts
            for gate_offset in range(0, 10, 2):  # 0, 2, 4, 6, 8
                gates = base_gates + gate_offset

                while attempts < max_attempts and len(taxonomies_found) < target_taxonomies:
                    added, taxonomy = self.synthesize_and_add(
                        wires=width,
                        gates=gates,
                        max_variants=max_variants,
                        solver_name=solver_name,
                    )

                    if taxonomy:
                        taxonomies_found.add(taxonomy)

                    attempts += 1

                    if progress_callback:
                        progress_callback(width, attempts, len(taxonomies_found))

                    if attempts >= max_attempts:
                        break

                if len(taxonomies_found) >= target_taxonomies:
                    break

            print(f"Width {width}: {len(taxonomies_found)} taxonomies, "
                  f"{attempts} attempts, {self.stats['circuits_added']} total circuits")

        elapsed = time.time() - start_time

        return {
            **self.stats,
            "elapsed_seconds": elapsed,
            "min_wires": min_wires,
            "max_wires": max_wires,
        }

    def get_stats(self) -> dict:
        """Get database statistics."""
        stats = dict(self.stats)

        # Count circuits per width
        circuits_per_width = {}
        taxonomies_per_width = {}

        with self._env.begin() as txn:
            for width in range(3, 20):
                db_name = f"ids_n{width}"
                try:
                    db = self._env.open_db(db_name.encode(), txn=txn)
                    cursor = txn.cursor(db=db)

                    count = 0
                    circuit_count = 0
                    for key, value in cursor:
                        count += 1
                        circuits = deserialize_circuit_list(value)
                        circuit_count += len(circuits)

                    if count > 0:
                        taxonomies_per_width[width] = count
                        circuits_per_width[width] = circuit_count
                except:
                    pass

        stats["taxonomies_per_width"] = taxonomies_per_width
        stats["circuits_per_width"] = circuits_per_width

        return stats

    def lookup(self, width: int, taxonomy: GatePair) -> list[bytes]:
        """Look up circuits by taxonomy.

        Args:
            width: Circuit width.
            taxonomy: GatePair taxonomy to look up.

        Returns:
            List of circuit blobs matching the taxonomy.
        """
        db = self._get_db(width)
        key = taxonomy.to_bytes()

        with self._env.begin() as txn:
            value = txn.get(key, db=db)
            if value:
                return deserialize_circuit_list(value)
            return []

    def get_random_identity(self, width: int, taxonomy: GatePair) -> Optional[bytes]:
        """Get a random identity circuit matching taxonomy.

        This mirrors the Rust get_random_identity function.

        Args:
            width: Circuit width.
            taxonomy: GatePair taxonomy.

        Returns:
            Random circuit blob or None if not found.
        """
        circuits = self.lookup(width, taxonomy)
        if circuits:
            return random.choice(circuits)
        return None


# -----------------------------------------------------------------------------
# Utility functions
# -----------------------------------------------------------------------------

def enumerate_all_taxonomies() -> Iterator[GatePair]:
    """Enumerate all possible GatePair taxonomies (4^3 = 64)."""
    for a in CollisionType:
        for c1 in CollisionType:
            for c2 in CollisionType:
                yield GatePair(a, c1, c2)


def enumerate_collision_taxonomies() -> Iterator[GatePair]:
    """Enumerate GatePair taxonomies where gates collide.

    For skeleton chains, adjacent gates must collide.
    """
    for tax in enumerate_all_taxonomies():
        if tax.is_collision():
            yield tax


def count_collision_taxonomies() -> int:
    """Count how many collision taxonomies exist."""
    return sum(1 for _ in enumerate_collision_taxonomies())


# -----------------------------------------------------------------------------
# CLI helpers
# -----------------------------------------------------------------------------

def build_skeleton_database(
    output_path: str,
    min_wires: int = 4,
    max_wires: int = 12,
    target_taxonomies: int = 50,
    max_variants: int = 100,
    verbose: bool = True,
) -> dict:
    """High-level function to build a skeleton chain database.

    Args:
        output_path: Path for the LMDB database.
        min_wires: Minimum wire count.
        max_wires: Maximum wire count.
        target_taxonomies: Target distinct taxonomies per width.
        max_variants: Maximum variants per skeleton.
        verbose: Print progress.

    Returns:
        Statistics dictionary.
    """
    def progress(width, attempt, found):
        if verbose:
            print(f"  Width {width}: attempt {attempt}, {found} taxonomies found", end="\r")

    config = SkeletonDBConfig(
        min_wires=min_wires,
        max_wires=max_wires,
        target_taxonomies_per_width=target_taxonomies,
    )

    with SkeletonDBBuilder(output_path, config) as builder:
        if verbose:
            print(f"Building skeleton chain database at {output_path}")
            print(f"Wires: {min_wires}-{max_wires}, target {target_taxonomies} taxonomies/width")
            print()

        stats = builder.build(
            max_variants=max_variants,
            progress_callback=progress if verbose else None,
        )

        if verbose:
            print()
            print(f"Done! Stats: {stats}")

        return stats


# -----------------------------------------------------------------------------
# Integration with local_mixing
# -----------------------------------------------------------------------------

LOCAL_MIXING_DB_PATH = "../local_mixing/db"  # Default path relative to sat_revsynth


def build_for_local_mixing(
    min_wires: int = 4,
    max_wires: int = 12,
    target_taxonomies: int = 50,
    max_variants: int = 100,
    db_path: Optional[str] = None,
) -> dict:
    """Build skeleton chain database in local_mixing's database directory.

    This function creates `ids_n{n}` databases in the same LMDB environment
    that local_mixing uses, enabling seamless integration with the pair
    replacement system.

    Args:
        min_wires: Minimum wire count.
        max_wires: Maximum wire count.
        target_taxonomies: Target distinct taxonomies per width.
        max_variants: Maximum variants per skeleton.
        db_path: Path to local_mixing's database directory (default: ../local_mixing/db)

    Returns:
        Statistics dictionary.

    Usage in local_mixing:
        After running this, the Rust code needs to update `open_all_dbs()` in
        mixing.rs to include `ids_n{n}` databases. Add these entries:

        ```rust
        // In open_all_dbs() db_names array:
        "ids_n4",
        "ids_n5",
        "ids_n6",
        // ... up to max_wires
        "ids_n12",
        ```

        Then `get_random_identity()` in replace.rs can be used to look up
        skeleton chains by taxonomy.

    Example:
        >>> from database.skeleton_db import build_for_local_mixing
        >>> stats = build_for_local_mixing(
        ...     min_wires=4,
        ...     max_wires=10,
        ...     target_taxonomies=30,
        ... )
        >>> print(f"Added {stats['circuits_added']} skeleton chains")
    """
    if db_path is None:
        # Try to find local_mixing/db relative to this file
        this_dir = Path(__file__).parent
        db_path = str(this_dir.parent.parent.parent / "local_mixing" / "db")

    return build_skeleton_database(
        output_path=db_path,
        min_wires=min_wires,
        max_wires=max_wires,
        target_taxonomies=target_taxonomies,
        max_variants=max_variants,
        verbose=True,
    )


if __name__ == "__main__":
    # Simple test
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        print("Testing skeleton database builder...")

        # Test serialization
        tax = GatePair(CollisionType.OnActive, CollisionType.OnCtrl1, CollisionType.OnNew)
        data = tax.to_bytes()
        tax2 = GatePair.from_bytes(data)
        assert tax == tax2, "GatePair serialization failed"
        print(f"  GatePair serialization: OK ({tax})")

        # Test circuit list serialization
        circuits = [b"\x00\x01\x02\x01\x00\x03", b"\x00\x02\x01"]
        data = serialize_circuit_list(circuits)
        circuits2 = deserialize_circuit_list(data)
        assert circuits == circuits2, "Circuit list serialization failed"
        print(f"  Circuit list serialization: OK ({len(circuits)} circuits)")

        # Test database builder (small)
        print("\nBuilding small test database...")
        db_path = Path(tmpdir) / "test_skeleton_db"

        config = SkeletonDBConfig(
            min_wires=4,
            max_wires=4,
            target_taxonomies_per_width=3,
            max_synthesis_attempts=10,
        )

        with SkeletonDBBuilder(db_path, config) as builder:
            stats = builder.build(max_variants=10)
            print(f"  Stats: {stats}")

            # Test lookup
            final_stats = builder.get_stats()
            print(f"  Final stats: {final_stats}")

        print("\nAll tests passed!")
