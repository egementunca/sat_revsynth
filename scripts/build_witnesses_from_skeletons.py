#!/usr/bin/env python3
"""Build witness database from skeleton identity circuits.

Extracts witnesses (first half + 1 gates) from skeleton circuits and stores them
with k-gram prefilter for fast identity detection.

Usage:
    python scripts/build_witnesses_from_skeletons.py <skeleton_db> <witness_db> [--dry-run]

Example:
    python scripts/build_witnesses_from_skeletons.py skeleton_identity_db data/witnesses.lmdb
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, List

import lmdb
import blake3

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from database.skeleton_db import deserialize_circuit_list


@dataclass
class WitnessStats:
    """Statistics from witness building."""
    circuits_processed: int = 0
    witnesses_created: int = 0
    witnesses_deduplicated: int = 0
    tokens_indexed: int = 0


def compute_witness_length(gate_count: int) -> int:
    """Compute witness length from identity circuit gate count.

    witness_len = floor(GC / 2) + 1
    """
    return (gate_count // 2) + 1


def blob_to_gates(blob: bytes) -> List[tuple]:
    """Convert blob to list of (target, ctrl1, ctrl2) tuples."""
    gates = []
    for i in range(0, len(blob), 3):
        gates.append((blob[i], blob[i+1], blob[i+2]))
    return gates


def canonicalize_gates(gates: List[tuple], width: int) -> tuple:
    """Canonicalize gates via local wire relabeling.

    Returns (canonical_gates, hash_bytes).
    """
    # Simple canonicalization: sort by first occurrence of wires
    wire_map = {}
    next_wire = 0

    canonical = []
    for t, c1, c2 in gates:
        for w in [t, c1, c2]:
            if w not in wire_map:
                wire_map[w] = next_wire
                next_wire += 1
        canonical.append((wire_map[t], wire_map[c1], wire_map[c2]))

    # Compute hash
    hasher = blake3.blake3()
    for t, c1, c2 in canonical:
        hasher.update(bytes([t, c1, c2]))

    return tuple(canonical), hasher.digest()


def compute_kgram_tokens(gates: List[tuple], k: int, width: int) -> List[int]:
    """Compute k-gram token hashes for prefilter."""
    if len(gates) < k:
        return []

    tokens = []
    for i in range(len(gates) - k + 1):
        window = gates[i:i + k]
        _, window_hash = canonicalize_gates(window, width)
        # Take first 8 bytes as 64-bit token
        token = struct.unpack("<Q", window_hash[:8])[0]
        tokens.append(token)

    return tokens


def build_witnesses(
    skeleton_db_path: str,
    witness_db_path: str,
    k_gram_sizes: List[int] = None,
    dry_run: bool = False,
    verbose: bool = True,
) -> WitnessStats:
    """Build witness database from skeleton circuits.

    Args:
        skeleton_db_path: Path to skeleton LMDB database.
        witness_db_path: Path for output witness LMDB database.
        k_gram_sizes: K-gram sizes for prefilter (default: [2, 3]).
        dry_run: If True, don't write to database.
        verbose: Print progress.

    Returns:
        Statistics about witness building.
    """
    k_gram_sizes = k_gram_sizes or [2, 3]
    stats = WitnessStats()

    # Track seen witness hashes for deduplication
    seen_hashes = set()  # (width, witness_len, hash_bytes)

    # Collect all witnesses first
    witnesses_by_dims = defaultdict(list)  # (width, witness_len) -> [(gates, hash)]
    prefilter_entries = defaultdict(set)   # (width, token) -> set of witness indices

    # Open skeleton database
    skeleton_env = lmdb.open(skeleton_db_path, max_dbs=20, readonly=True)

    for width in range(3, 20):
        db_name = f"ids_n{width}"
        try:
            db = skeleton_env.open_db(db_name.encode())
        except lmdb.NotFoundError:
            continue

        if verbose:
            print(f"Processing {db_name}...")

        with skeleton_env.begin() as txn:
            cursor = txn.cursor(db=db)

            for key, value in cursor:
                circuits = deserialize_circuit_list(value)

                for blob in circuits:
                    stats.circuits_processed += 1
                    gates = blob_to_gates(blob)
                    gc = len(gates)

                    # Compute witness
                    witness_len = compute_witness_length(gc)
                    witness_gates = gates[:witness_len]

                    # Canonicalize
                    canonical_gates, witness_hash = canonicalize_gates(witness_gates, width)

                    # Check for duplicate
                    key_tuple = (width, witness_len, witness_hash)
                    if key_tuple in seen_hashes:
                        stats.witnesses_deduplicated += 1
                        continue

                    seen_hashes.add(key_tuple)
                    stats.witnesses_created += 1

                    # Store witness
                    witness_idx = len(witnesses_by_dims[(width, witness_len)])
                    witnesses_by_dims[(width, witness_len)].append((canonical_gates, witness_hash))

                    # Compute k-gram tokens for prefilter
                    for k in k_gram_sizes:
                        tokens = compute_kgram_tokens(list(canonical_gates), k, width)
                        for token in tokens:
                            prefilter_entries[(width, token)].add(witness_idx)
                            stats.tokens_indexed += 1

    skeleton_env.close()

    if verbose:
        print(f"\nWitnesses by dimensions:")
        for (width, wlen), witnesses in sorted(witnesses_by_dims.items()):
            print(f"  Width {width}, WitnessLen {wlen}: {len(witnesses)} witnesses")

    # Write to witness database
    if not dry_run:
        Path(witness_db_path).mkdir(parents=True, exist_ok=True)

        witness_env = lmdb.open(
            witness_db_path,
            map_size=10 * 1024 * 1024 * 1024,  # 10 GB
            max_dbs=10,
        )

        # Create databases
        witnesses_db = witness_env.open_db(b"witnesses")
        prefilter_db = witness_env.open_db(b"prefilter")
        meta_db = witness_env.open_db(b"meta")

        with witness_env.begin(write=True) as txn:
            # Store witnesses
            for (width, witness_len), witnesses in witnesses_by_dims.items():
                for idx, (canonical_gates, witness_hash) in enumerate(witnesses):
                    # Key: width(1B) + witness_len(2B) + hash(32B)
                    key = struct.pack("<BH", width, witness_len) + witness_hash

                    # Value: encoded gates
                    gates_blob = b"".join(bytes(g) for g in canonical_gates)
                    txn.put(key, gates_blob, db=witnesses_db)

            # Store prefilter entries
            for (width, token), witness_indices in prefilter_entries.items():
                # Key: width(1B) + token(8B)
                key = struct.pack("<BQ", width, token)

                # Value: list of witness indices as u32
                value = struct.pack(f"<{len(witness_indices)}I", *sorted(witness_indices))
                txn.put(key, value, db=prefilter_db)

            # Store metadata
            txn.put(b"witness_count", struct.pack("<Q", stats.witnesses_created), db=meta_db)
            txn.put(b"circuit_count", struct.pack("<Q", stats.circuits_processed), db=meta_db)

        witness_env.close()

        if verbose:
            print(f"\nWrote witness database to {witness_db_path}")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Build witness database from skeleton identity circuits"
    )
    parser.add_argument(
        "skeleton_db",
        help="Path to skeleton LMDB database",
    )
    parser.add_argument(
        "witness_db",
        help="Path for output witness LMDB database",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually write to database",
    )
    parser.add_argument(
        "--k-grams",
        nargs="+",
        type=int,
        default=[2, 3],
        help="K-gram sizes for prefilter (default: 2 3)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose output",
    )

    args = parser.parse_args()

    if not Path(args.skeleton_db).exists():
        print(f"Error: Skeleton database not found: {args.skeleton_db}")
        sys.exit(1)

    print(f"Building witnesses from: {args.skeleton_db}")
    print(f"Output database: {args.witness_db}")
    print(f"K-gram sizes: {args.k_grams}")
    if args.dry_run:
        print("[DRY RUN]")
    print("=" * 60)

    stats = build_witnesses(
        args.skeleton_db,
        args.witness_db,
        k_gram_sizes=args.k_grams,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )

    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Circuits processed:      {stats.circuits_processed}")
    print(f"  Witnesses created:       {stats.witnesses_created}")
    print(f"  Witnesses deduplicated:  {stats.witnesses_deduplicated}")
    print(f"  Tokens indexed:          {stats.tokens_indexed}")

    if args.dry_run:
        print("\n[DRY RUN] No changes were made.")


if __name__ == "__main__":
    main()
