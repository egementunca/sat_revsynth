#!/usr/bin/env python3
"""Synthesize wire permutation circuits using Waksman-style networks.

This script generates ECA57 circuits that implement wire permutations using
a swap-based network approach. Each swap is implemented with a 6-gate ECA57
macro.

Usage:
    # Single permutation
    python scripts/synth_waksman.py --width 8 --perm 7,6,5,4,3,2,1,0

    # Random permutation
    python scripts/synth_waksman.py --width 8 --random

    # Multiple random permutations
    python scripts/synth_waksman.py --width 16 --sample 100 --output circuits.json

    # All permutations for small width
    python scripts/synth_waksman.py --width 4 --all-perms --output all_w4.json

    # Verify a permutation circuit
    python scripts/synth_waksman.py --width 4 --perm 3,2,1,0 --verify
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from itertools import permutations as iterperms
from pathlib import Path
from typing import List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from synthesizers.waksman import (
    WaksmanNetwork,
    SimpleSwapNetwork,
    synthesize_waksman,
    synthesize_permutation,
)
from gates.eca57 import ECA57Circuit


def parse_permutation(perm_str: str) -> List[int]:
    """Parse a comma-separated permutation string."""
    return [int(x.strip()) for x in perm_str.split(",")]


def verify_circuit(circuit: ECA57Circuit, perm: List[int], n: int, max_tests: int = 1000) -> bool:
    """Verify that a circuit implements the given permutation."""
    width = circuit.width()

    if n <= 10:
        # Exhaustive test for small n
        test_inputs = range(2**n)
    else:
        # Sample for large n
        random.seed(42)
        test_inputs = [random.randint(0, 2**n - 1) for _ in range(max_tests)]

    for i in test_inputs:
        input_state = [(i >> b) & 1 for b in range(width)]
        output_state = circuit.apply(input_state)

        for k in range(n):
            if output_state[k] != input_state[perm[k]]:
                return False

    return True


def circuit_to_dict(circuit: ECA57Circuit, perm: List[int], metadata: dict = None) -> dict:
    """Convert circuit to JSON-serializable dict."""
    result = {
        "permutation": perm,
        "width": len(perm),
        "circuit_width": circuit.width(),
        "gate_count": len(circuit),
        "gates": [g.to_tuple() for g in circuit.gates()],
    }
    if metadata:
        result.update(metadata)
    return result


def print_circuit_ascii(circuit: ECA57Circuit, perm: List[int]):
    """Print ASCII representation of the circuit."""
    width = circuit.width()
    gates = circuit.gates()

    print(f"Permutation: {perm}")
    print(f"Gate count: {len(gates)}")
    print(f"Circuit width: {width}")
    print()

    if len(gates) == 0:
        print("(Identity - no gates needed)")
        return

    # Simple ASCII representation
    for i, gate in enumerate(gates):
        t, c1, c2 = gate.target, gate.ctrl1, gate.ctrl2
        print(f"  Gate {i}: target={t}, ctrl1={c1} (OR), ctrl2={c2} (NOT)")


def main():
    parser = argparse.ArgumentParser(
        description="Synthesize wire permutation circuits using Waksman-style networks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Width specification
    parser.add_argument(
        "--width", "-w",
        type=int,
        required=True,
        help="Number of wires (must be >= 2, power of 2 for --waksman mode)",
    )

    # Permutation specification (mutually exclusive)
    perm_group = parser.add_mutually_exclusive_group()
    perm_group.add_argument(
        "--perm", "-p",
        type=str,
        help="Comma-separated permutation, e.g., '3,2,1,0' for reverse",
    )
    perm_group.add_argument(
        "--random", "-r",
        action="store_true",
        help="Generate random permutation",
    )
    perm_group.add_argument(
        "--reverse",
        action="store_true",
        help="Generate reverse permutation [n-1, n-2, ..., 0]",
    )
    perm_group.add_argument(
        "--shift",
        type=int,
        metavar="K",
        help="Generate cyclic shift by K positions",
    )
    perm_group.add_argument(
        "--all-perms",
        action="store_true",
        help="Generate circuits for all n! permutations (small n only)",
    )
    perm_group.add_argument(
        "--sample",
        type=int,
        metavar="N",
        help="Generate N random permutations",
    )

    # Output options
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Output JSON file for results",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify circuit correctness after generation",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress ASCII output",
    )

    # Algorithm options
    parser.add_argument(
        "--simple",
        action="store_true",
        help="Use simple swap network (works for any n >= 2)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility",
    )

    args = parser.parse_args()

    # Validate width
    if args.width < 2:
        parser.error("Width must be at least 2")

    # Check power-of-2 for Waksman mode
    if not args.simple and (args.width & (args.width - 1)) != 0:
        print(f"Note: Width {args.width} is not a power of 2, using simple swap network")
        args.simple = True

    # Set random seed
    if args.seed is not None:
        random.seed(args.seed)

    # Determine permutation(s) to synthesize
    perms_to_synthesize: List[List[int]] = []

    if args.perm:
        perms_to_synthesize.append(parse_permutation(args.perm))
    elif args.random:
        perm = list(range(args.width))
        random.shuffle(perm)
        perms_to_synthesize.append(perm)
    elif args.reverse:
        perms_to_synthesize.append(list(range(args.width - 1, -1, -1)))
    elif args.shift is not None:
        k = args.shift % args.width
        perms_to_synthesize.append([(i - k) % args.width for i in range(args.width)])
    elif args.all_perms:
        if args.width > 7:
            parser.error("--all-perms is only practical for width <= 7")
        perms_to_synthesize = [list(p) for p in iterperms(range(args.width))]
    elif args.sample:
        for _ in range(args.sample):
            perm = list(range(args.width))
            random.shuffle(perm)
            perms_to_synthesize.append(perm)
    else:
        # Default: identity permutation
        perms_to_synthesize.append(list(range(args.width)))

    # Synthesize circuits
    results = []
    total_time = 0

    for perm in perms_to_synthesize:
        # Validate permutation
        if len(perm) != args.width:
            print(f"Error: Permutation length {len(perm)} != width {args.width}", file=sys.stderr)
            continue

        if sorted(perm) != list(range(args.width)):
            print(f"Error: Invalid permutation {perm}", file=sys.stderr)
            continue

        # Synthesize
        start = time.time()
        if args.simple:
            circuit = synthesize_permutation(args.width, perm)
        else:
            circuit = synthesize_waksman(args.width, perm)
        elapsed = time.time() - start
        total_time += elapsed

        # Verify if requested
        verified = None
        if args.verify:
            verified = verify_circuit(circuit, perm, args.width)

        # Build result
        metadata = {
            "synthesis_time_ms": round(elapsed * 1000, 2),
            "verified": verified,
            "algorithm": "simple" if args.simple else "waksman",
        }
        result = circuit_to_dict(circuit, perm, metadata)
        results.append(result)

        # Print if not quiet
        if not args.quiet and len(perms_to_synthesize) <= 10:
            print_circuit_ascii(circuit, perm)
            if verified is not None:
                print(f"Verified: {'PASS' if verified else 'FAIL'}")
            print()

    # Summary
    if len(perms_to_synthesize) > 1:
        total_gates = sum(r["gate_count"] for r in results)
        avg_gates = total_gates / len(results)
        print(f"Summary: {len(results)} circuits, total {total_gates} gates, avg {avg_gates:.1f} gates/circuit")
        print(f"Total time: {total_time*1000:.1f}ms, avg {total_time*1000/len(results):.2f}ms/circuit")

        if args.verify:
            passed = sum(1 for r in results if r.get("verified"))
            print(f"Verified: {passed}/{len(results)} passed")

    # Save to JSON if requested
    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            json.dump(results if len(results) > 1 else results[0], f, indent=2)
        print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()
