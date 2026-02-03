#!/usr/bin/env python3
"""Generate skeleton chains for a specific width and add to database.

Usage:
    python scripts/generate_skeletons_batch.py <width> [--gates MIN MAX] [--taxonomies N] [--variants N]

Example:
    python scripts/generate_skeletons_batch.py 10 --gates 16 24 --taxonomies 50 --variants 100
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from database.skeleton_db import (
    SkeletonDBBuilder,
    SkeletonDBConfig,
    gate_pair_taxonomy,
)
from synthesizers.skeleton_chain_api import (
    synthesize_skeleton_chain,
    limited_unroll,
    verify_skeleton_chain,
)


def generate_for_width(
    db_path: str,
    width: int,
    min_gates: int,
    max_gates: int,
    target_taxonomies: int,
    max_variants: int,
    max_attempts: int,
    solver_name: str = "glucose4",
):
    """Generate skeleton chains for a specific width."""

    print(f"Generating skeletons for width={width}")
    print(f"  Gate range: {min_gates}-{max_gates}")
    print(f"  Target taxonomies: {target_taxonomies}")
    print(f"  Max variants per skeleton: {max_variants}")
    print(f"  Max attempts: {max_attempts}")
    print()

    config = SkeletonDBConfig(
        max_circuits_per_taxonomy=max_variants * 2,  # Allow some room
        max_permutations=100,
    )

    start_time = time.time()

    with SkeletonDBBuilder(db_path, config) as builder:
        taxonomies_found = set()
        attempts = 0
        circuits_added = 0

        # Cycle through gate counts
        gate_counts = list(range(min_gates, max_gates + 1, 2))  # Even numbers
        gate_idx = 0

        while attempts < max_attempts and len(taxonomies_found) < target_taxonomies:
            gates = gate_counts[gate_idx % len(gate_counts)]
            gate_idx += 1
            attempts += 1

            # Synthesize
            skeleton = synthesize_skeleton_chain(
                wires=width,
                gates=gates,
                solver_name=solver_name,
            )

            if skeleton is None:
                print(f"  [{attempts}] gates={gates}: UNSAT")
                continue

            # Verify
            if not verify_skeleton_chain(skeleton):
                print(f"  [{attempts}] gates={gates}: Not a valid skeleton chain")
                continue

            if not skeleton.is_identity():
                print(f"  [{attempts}] gates={gates}: Not an identity circuit")
                continue

            # Get taxonomy
            gates_list = list(skeleton.gates())
            g1 = (gates_list[0].target, gates_list[0].ctrl1, gates_list[0].ctrl2)
            g2 = (gates_list[1].target, gates_list[1].ctrl1, gates_list[1].ctrl2)
            taxonomy = gate_pair_taxonomy(g1, g2)

            is_new = taxonomy not in taxonomies_found
            taxonomies_found.add(taxonomy)

            # Add variants
            added = builder.add_skeleton_variants(skeleton, width, max_variants)
            circuits_added += added

            status = "NEW" if is_new else "existing"
            print(f"  [{attempts}] gates={gates}: {taxonomy} ({status}), +{added} circuits")

            # Progress update every 10 attempts
            if attempts % 10 == 0:
                elapsed = time.time() - start_time
                print(f"  --- Progress: {len(taxonomies_found)}/{target_taxonomies} taxonomies, "
                      f"{circuits_added} circuits, {elapsed:.1f}s ---")

        elapsed = time.time() - start_time

        print()
        print("=" * 60)
        print(f"DONE: width={width}")
        print(f"  Taxonomies found: {len(taxonomies_found)}")
        print(f"  Circuits added: {circuits_added}")
        print(f"  Attempts: {attempts}")
        print(f"  Time: {elapsed:.1f}s")
        print("=" * 60)

        return {
            "width": width,
            "taxonomies": len(taxonomies_found),
            "circuits": circuits_added,
            "attempts": attempts,
            "elapsed": elapsed,
        }


def main():
    parser = argparse.ArgumentParser(
        description="Generate skeleton chains for a specific width"
    )
    parser.add_argument("width", type=int, help="Circuit width (number of wires)")
    parser.add_argument(
        "--gates",
        nargs=2,
        type=int,
        metavar=("MIN", "MAX"),
        help="Gate count range (default: width*2 to width*3)"
    )
    parser.add_argument(
        "--taxonomies",
        type=int,
        default=50,
        help="Target number of distinct taxonomies (default: 50)"
    )
    parser.add_argument(
        "--variants",
        type=int,
        default=100,
        help="Max variants per skeleton (default: 100)"
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=200,
        help="Max synthesis attempts (default: 200)"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="skeleton_identity_db",
        help="Database path (default: skeleton_identity_db)"
    )
    parser.add_argument(
        "--solver",
        type=str,
        default="glucose4",
        help="SAT solver (default: glucose4)"
    )

    args = parser.parse_args()

    # Default gate range based on width
    if args.gates:
        min_gates, max_gates = args.gates
    else:
        min_gates = args.width * 2
        max_gates = args.width * 3

    # Ensure even numbers
    min_gates = min_gates if min_gates % 2 == 0 else min_gates + 1
    max_gates = max_gates if max_gates % 2 == 0 else max_gates - 1

    generate_for_width(
        db_path=args.db,
        width=args.width,
        min_gates=min_gates,
        max_gates=max_gates,
        target_taxonomies=args.taxonomies,
        max_variants=args.variants,
        max_attempts=args.attempts,
        solver_name=args.solver,
    )


if __name__ == "__main__":
    main()
