#!/usr/bin/env python3
"""Post-process skeleton database to simplify circuits with consecutive identical gates.

This script scans the skeleton database and removes consecutive identical gates,
which cancel out (G*G = Identity for ECA57 gates). This fixes circuits that were
generated before the wrap-around constraint was added to the synthesizer.

Usage:
    python scripts/postprocess_simplify_circuits.py <db_path> [--dry-run]

Example:
    python scripts/postprocess_simplify_circuits.py skeleton_identity_db --dry-run
    python scripts/postprocess_simplify_circuits.py skeleton_identity_db
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import lmdb

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gates.eca57 import ECA57Gate, ECA57Circuit
from database.skeleton_db import (
    GatePair,
    CollisionType,
    gate_pair_taxonomy,
    circuit_to_blob,
    serialize_circuit_list,
    deserialize_circuit_list,
)


def blob_to_circuit(blob: bytes, width: int) -> ECA57Circuit:
    """Convert blob format back to circuit.

    Each gate is 3 bytes: [target, ctrl1, ctrl2]
    """
    circuit = ECA57Circuit(width)
    for i in range(0, len(blob), 3):
        target = blob[i]
        ctrl1 = blob[i + 1]
        ctrl2 = blob[i + 2]
        circuit.add_gate(target, ctrl1, ctrl2)
    return circuit


def find_consecutive_identical_gates(circuit: ECA57Circuit) -> list[int]:
    """Find indices where consecutive identical gates exist.

    Returns list of indices i where gates[i] == gates[i+1].
    """
    indices = []
    gates = circuit.gates()
    for i in range(len(gates) - 1):
        if gates[i] == gates[i + 1]:
            indices.append(i)
    return indices


def simplify_circuit(circuit: ECA57Circuit) -> tuple[ECA57Circuit, int]:
    """Remove consecutive identical gates from a circuit.

    Since G*G = Identity for ECA57 gates, consecutive identical gates
    can be removed without changing the circuit's function.

    Returns:
        (simplified_circuit, num_gates_removed)
    """
    gates = list(circuit.gates())
    removed = 0

    # Keep removing consecutive identical gates until none remain
    # (removing a pair might create a new pair)
    changed = True
    while changed:
        changed = False
        new_gates = []
        i = 0
        while i < len(gates):
            if i + 1 < len(gates) and gates[i] == gates[i + 1]:
                # Skip both gates (they cancel out)
                i += 2
                removed += 2
                changed = True
            else:
                new_gates.append(gates[i])
                i += 1
        gates = new_gates

    # Build new circuit
    new_circuit = ECA57Circuit(circuit.width())
    for g in gates:
        new_circuit.add_gate(g.target, g.ctrl1, g.ctrl2)

    return new_circuit, removed


def infer_width_from_blob(blob: bytes) -> int:
    """Infer circuit width from blob by finding max wire index."""
    max_wire = 0
    for i in range(0, len(blob), 3):
        max_wire = max(max_wire, blob[i], blob[i + 1], blob[i + 2])
    return max_wire + 1


@dataclass
class SimplifyStats:
    """Statistics from simplification."""
    total_circuits: int = 0
    circuits_with_consecutive: int = 0
    circuits_simplified: int = 0
    circuits_removed: int = 0  # Became empty after simplification
    total_gates_removed: int = 0
    taxonomies_processed: int = 0
    taxonomies_modified: int = 0


def process_database(
    db_path: str,
    dry_run: bool = False,
    verbose: bool = True,
) -> SimplifyStats:
    """Process the skeleton database and simplify circuits.

    Args:
        db_path: Path to LMDB database directory.
        dry_run: If True, don't actually modify the database.
        verbose: Print progress.

    Returns:
        Statistics about the simplification.
    """
    stats = SimplifyStats()

    # Open database
    env = lmdb.open(
        db_path,
        map_size=50 * 1024 * 1024 * 1024,  # 50 GB
        max_dbs=20,
    )

    # Find all databases (ids_n{width})
    with env.begin() as txn:
        # Get list of all databases
        cursor = txn.cursor()
        # We can't easily list DBs, so we'll try known widths
        pass

    # Process each width
    for width in range(3, 20):
        db_name = f"ids_n{width}"

        try:
            db = env.open_db(db_name.encode())
        except lmdb.NotFoundError:
            continue

        if verbose:
            print(f"\nProcessing {db_name}...")

        # Collect all modifications needed
        modifications = {}  # key -> new_circuits_list
        deletions = []  # keys to delete

        with env.begin() as txn:
            cursor = txn.cursor(db=db)

            for key, value in cursor:
                stats.taxonomies_processed += 1
                circuits = deserialize_circuit_list(value)

                modified = False
                new_circuits = []

                for blob in circuits:
                    stats.total_circuits += 1

                    # Infer width if needed (should match db width)
                    circuit_width = infer_width_from_blob(blob)
                    if circuit_width < 3:
                        circuit_width = width  # Use db width as fallback

                    circuit = blob_to_circuit(blob, max(circuit_width, width))

                    # Check for consecutive identical gates
                    consec_indices = find_consecutive_identical_gates(circuit)

                    if consec_indices:
                        stats.circuits_with_consecutive += 1

                        # Simplify
                        simplified, gates_removed = simplify_circuit(circuit)
                        stats.total_gates_removed += gates_removed

                        if len(simplified) == 0:
                            # Circuit became empty - remove it
                            stats.circuits_removed += 1
                            modified = True
                            if verbose:
                                print(f"  Circuit removed (was {len(circuit)} gates, all cancelled)")
                        elif len(simplified) < len(circuit):
                            # Circuit was simplified
                            stats.circuits_simplified += 1
                            modified = True
                            new_blob = circuit_to_blob(simplified)

                            # Check if new blob is a duplicate
                            if new_blob not in new_circuits:
                                new_circuits.append(new_blob)

                            if verbose:
                                print(f"  Simplified: {len(circuit)} -> {len(simplified)} gates "
                                      f"(removed {gates_removed})")
                        else:
                            # No change (shouldn't happen if consec_indices was non-empty)
                            new_circuits.append(blob)
                    else:
                        # No consecutive identical gates
                        new_circuits.append(blob)

                if modified:
                    stats.taxonomies_modified += 1
                    if len(new_circuits) == 0:
                        deletions.append(key)
                    else:
                        modifications[key] = new_circuits

        # Apply modifications
        if not dry_run and (modifications or deletions):
            with env.begin(write=True) as txn:
                for key, new_circuits in modifications.items():
                    value = serialize_circuit_list(new_circuits)
                    txn.put(key, value, db=db)

                for key in deletions:
                    txn.delete(key, db=db)

            if verbose:
                print(f"  Applied {len(modifications)} modifications, {len(deletions)} deletions")
        elif dry_run and (modifications or deletions):
            if verbose:
                print(f"  [DRY RUN] Would apply {len(modifications)} modifications, "
                      f"{len(deletions)} deletions")

    env.close()
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Post-process skeleton database to simplify circuits with consecutive identical gates."
    )
    parser.add_argument(
        "db_path",
        help="Path to LMDB database directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually modify the database, just report what would be done",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose output",
    )

    args = parser.parse_args()

    if not Path(args.db_path).exists():
        print(f"Error: Database path does not exist: {args.db_path}")
        sys.exit(1)

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Processing database: {args.db_path}")
    print("=" * 60)

    stats = process_database(
        args.db_path,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )

    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Taxonomies processed:        {stats.taxonomies_processed}")
    print(f"  Taxonomies modified:         {stats.taxonomies_modified}")
    print(f"  Total circuits scanned:      {stats.total_circuits}")
    print(f"  Circuits with consecutive:   {stats.circuits_with_consecutive}")
    print(f"  Circuits simplified:         {stats.circuits_simplified}")
    print(f"  Circuits removed (empty):    {stats.circuits_removed}")
    print(f"  Total gates removed:         {stats.total_gates_removed}")

    if args.dry_run:
        print("\n[DRY RUN] No changes were made. Run without --dry-run to apply changes.")
    else:
        print("\nDone!")


if __name__ == "__main__":
    main()
