#!/usr/bin/env python3
"""Enumerate ECA57 swap-with-flip gadgets via SAT.

Finds distinct 3-wire circuits that swap wires 0 and 1 while preserving wire 2,
with optional bit-flips on the output. This supports Style B integration
(swap-with-flip gadgets) for the wire shuffle + bit-flip obfuscation.

For each flip mask s = (s0, s1) in {00, 01, 10, 11}:
    output[0] = input[1] XOR s0
    output[1] = input[0] XOR s1
    output[2] = input[2]  (aux wire preserved)

Outputs a JSON library suitable for gadget sampling in shuffle generators.

Features:
- Signal handling: saves progress on SIGINT/SIGTERM (Ctrl+C)
- Incremental saving: saves after each flip mask completes
- SAT racer support: race multiple solvers in parallel (--racer)
"""
from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union

import sys
from pathlib import Path as _Path

# Add src to path
sys.path.insert(0, str(_Path(__file__).parent.parent / "src"))

from truth_table.truth_table import TruthTable
from sat.solver import Solver
from sat.solver_racer import SolverRacer
from synthesizers.eca57_synthesizer import ECA57Synthesizer
from gates.eca57 import ECA57Circuit


# Global state for signal handling
_global_state = {
    "all_circuits": [],
    "all_counts": {},
    "output_path": None,
    "interrupted": False,
}


def save_progress(reason: str = "checkpoint") -> None:
    """Save current progress to output file."""
    if _global_state["output_path"] is None:
        return

    all_circuits = _global_state["all_circuits"]
    all_counts = _global_state["all_counts"]
    output_path = _global_state["output_path"]

    if not all_circuits:
        print(f"\n[{reason}] No circuits to save yet.")
        return

    payload = {
        "width": 3,
        "description": "Swap-with-flip gadgets: swap(wire0, wire1) with optional bit-flips",
        "flip_masks": {
            FLIP_MASK_NAMES[fm]: list(fm) for fm in FLIP_MASKS
        },
        "counts_by_flip": all_counts,
        "total_circuits": len(all_circuits),
        "circuits": all_circuits,
        "partial": reason != "complete",
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"\n[{reason}] Saved {len(all_circuits)} circuits to {output_path}")


def signal_handler(signum, _frame):
    """Handle SIGINT/SIGTERM by saving progress and exiting."""
    sig_name = signal.Signals(signum).name
    print(f"\n\nReceived {sig_name}, saving progress...")
    _global_state["interrupted"] = True
    save_progress(reason=f"interrupted-{sig_name}")
    sys.exit(0)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# Flip mask definitions: (s0, s1) meaning flip output wire 0 by s0, wire 1 by s1
FLIP_MASKS = [
    (0, 0),  # No flip
    (1, 0),  # Flip wire 0 only
    (0, 1),  # Flip wire 1 only
    (1, 1),  # Flip both wires
]

FLIP_MASK_NAMES = {
    (0, 0): "no_flip",
    (1, 0): "flip_wire0",
    (0, 1): "flip_wire1",
    (1, 1): "flip_both",
}


def swap_flip_truth_table(width: int, flip_mask: Tuple[int, int]) -> TruthTable:
    """Build truth table for swap(0,1) with flip mask applied.

    Args:
        width: Circuit width (typically 3).
        flip_mask: (s0, s1) tuple indicating which output wires to flip.

    Returns:
        TruthTable for the swap-with-flip function.
    """
    s0, s1 = flip_mask
    values = []
    for i in range(2**width):
        bits = [(i >> b) & 1 for b in range(width)]
        # Swap wires 0 and 1, apply flip mask
        out0 = bits[1] ^ s0  # output wire 0 = input wire 1 XOR s0
        out1 = bits[0] ^ s1  # output wire 1 = input wire 0 XOR s1
        out2 = bits[2]       # aux wire preserved
        output = out0 | (out1 << 1) | (out2 << 2)
        # Handle higher wires if width > 3
        for b in range(3, width):
            output |= bits[b] << b
        values.append(output)
    return TruthTable(width, values=values)


def verify_swap_flip(
    circuit: ECA57Circuit,
    wire_a: int,
    wire_b: int,
    aux: int,
    flip_mask: Tuple[int, int]
) -> bool:
    """Verify the circuit correctly performs swap-with-flip.

    Args:
        circuit: ECA57Circuit to verify.
        wire_a: First swap wire (typically 0).
        wire_b: Second swap wire (typically 1).
        aux: Auxiliary wire (typically 2).
        flip_mask: (s0, s1) flip mask applied to swapped outputs.

    Returns:
        True if circuit correctly implements swap-with-flip.
    """
    width = circuit.width()
    s0, s1 = flip_mask

    for i in range(2**width):
        input_state = [(i >> bit) & 1 for bit in range(width)]
        output_state = circuit.apply(input_state)

        # Check swap with flip on wires a and b
        expected_a = input_state[wire_b] ^ s0
        expected_b = input_state[wire_a] ^ s1

        if output_state[wire_a] != expected_a:
            return False
        if output_state[wire_b] != expected_b:
            return False
        # Aux wire must be preserved
        if output_state[aux] != input_state[aux]:
            return False
        # All other wires preserved
        for w in range(width):
            if w not in (wire_a, wire_b):
                if output_state[w] != input_state[w]:
                    return False
    return True


def create_solver(solver_names: List[str]) -> Union[Solver, SolverRacer]:
    """Create a solver or racer based on the number of solver names.

    Args:
        solver_names: List of solver names. If >1, uses SolverRacer.

    Returns:
        Solver or SolverRacer instance.
    """
    if len(solver_names) == 1:
        return Solver(solver_names[0])
    else:
        return SolverRacer(solver_names)


def enumerate_gadgets_for_flip(
    flip_mask: Tuple[int, int],
    min_gates: int,
    max_gates: int,
    max_solutions: int,
    solver_names: List[str],
    verify: bool,
    verbose: bool = False
) -> Tuple[List[Dict], Dict[str, int]]:
    """Enumerate all swap-with-flip gadgets for a specific flip mask.

    Args:
        flip_mask: (s0, s1) flip mask.
        min_gates: Minimum gate count to search.
        max_gates: Maximum gate count to search.
        max_solutions: Max solutions per gate count (0 = no cap).
        solver_names: List of SAT solver names (uses racer if >1).
        verify: Whether to verify each circuit.
        verbose: Whether to print progress.

    Returns:
        Tuple of (list of circuit dicts, gate count distribution dict).
    """
    tt = swap_flip_truth_table(3, flip_mask)
    flip_name = FLIP_MASK_NAMES[flip_mask]

    circuits: List[Dict] = []
    counts: Dict[str, int] = {}

    for gates in range(min_gates, max_gates + 1):
        if _global_state["interrupted"]:
            break

        # Create fresh solver/racer for each gate count
        solver = create_solver(solver_names)
        synth = ECA57Synthesizer(tt, gate_count=gates, solver=solver)
        found = 0

        while True:
            if _global_state["interrupted"]:
                break

            circuit = synth.solve()
            if circuit is None:
                break

            if verify and not verify_swap_flip(circuit, 0, 1, 2, flip_mask):
                synth.exclude_solution(circuit)
                continue

            circuits.append({
                "gate_count": len(circuit),
                "gates": [g.to_tuple() for g in circuit.gates()],
                "flip_mask": list(flip_mask),
                "flip_name": flip_name,
            })
            found += 1
            synth.exclude_solution(circuit)

            if max_solutions and found >= max_solutions:
                break

        if found:
            counts[str(gates)] = found
            if verbose:
                print(f"  {flip_name} @ {gates} gates: {found} circuits")

    return circuits, counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enumerate SAT swap-with-flip gadgets (3 wires).",
        epilog="""
Examples:
  # Single solver (default)
  python enumerate_swap_flip_gadgets.py -o gadgets.json --max-gates 12

  # Race multiple solvers for faster enumeration
  python enumerate_swap_flip_gadgets.py -o gadgets.json --max-gates 20 \\
      --racer glucose4 cadical kissat

  # Ctrl+C saves progress - you won't lose work!
"""
    )
    parser.add_argument(
        "--min-gates", type=int, default=6,
        help="Minimum gate count"
    )
    parser.add_argument(
        "--max-gates", type=int, default=12,
        help="Maximum gate count"
    )
    parser.add_argument(
        "--max-solutions", type=int, default=0,
        help="Max solutions per gate count per flip mask (0 = no cap)"
    )
    parser.add_argument(
        "--solver", type=str, default="glucose4",
        help="SAT solver name (ignored if --racer is used)"
    )
    parser.add_argument(
        "--racer", type=str, nargs="+", metavar="SOLVER",
        help="Race multiple solvers in parallel (e.g., --racer glucose4 cadical kissat)"
    )
    parser.add_argument(
        "--output", "-o", type=str, required=True,
        help="Output JSON path"
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="Verify swap-flip correctness"
    )
    parser.add_argument(
        "--flip-masks", type=str, default="all",
        choices=["all", "no_flip", "flip_wire0", "flip_wire1", "flip_both"],
        help="Which flip masks to enumerate"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print progress"
    )
    parser.add_argument(
        "--load-existing", type=str, metavar="FILE",
        help="Load existing gadgets from JSON file before enumerating (for resuming)"
    )
    args = parser.parse_args()

    if args.min_gates < 1 or args.max_gates < args.min_gates:
        parser.error("Invalid gate count range")

    # Determine solver(s) to use
    if args.racer:
        solver_names = args.racer
        if args.verbose:
            print(f"Using SAT racer with solvers: {', '.join(solver_names)}")
    else:
        solver_names = [args.solver]

    # Select which flip masks to enumerate
    if args.flip_masks == "all":
        flip_masks_to_use = FLIP_MASKS
    else:
        flip_masks_to_use = [
            fm for fm in FLIP_MASKS
            if FLIP_MASK_NAMES[fm] == args.flip_masks
        ]

    # Initialize global state for signal handling
    output_path = Path(args.output)
    _global_state["output_path"] = output_path
    _global_state["all_circuits"] = []
    _global_state["all_counts"] = {}

    # Load existing gadgets if resuming
    if args.load_existing:
        existing_path = Path(args.load_existing)
        if existing_path.exists():
            with open(existing_path) as f:
                existing = json.load(f)
            _global_state["all_circuits"] = existing.get("circuits", [])
            _global_state["all_counts"] = existing.get("counts_by_flip", {})
            if args.verbose:
                print(f"Loaded {len(_global_state['all_circuits'])} existing circuits from {existing_path}")

    for flip_mask in flip_masks_to_use:
        if _global_state["interrupted"]:
            break

        flip_name = FLIP_MASK_NAMES[flip_mask]
        if args.verbose:
            print(f"Enumerating flip mask: {flip_name} {flip_mask}")

        circuits, counts = enumerate_gadgets_for_flip(
            flip_mask=flip_mask,
            min_gates=args.min_gates,
            max_gates=args.max_gates,
            max_solutions=args.max_solutions,
            solver_names=solver_names,
            verify=args.verify,
            verbose=args.verbose
        )

        # Update global state (for signal handler)
        _global_state["all_circuits"].extend(circuits)
        # Merge counts with existing
        if flip_name in _global_state["all_counts"]:
            existing_counts = _global_state["all_counts"][flip_name]
            for g, c in counts.items():
                existing_counts[g] = existing_counts.get(g, 0) + c
        else:
            _global_state["all_counts"][flip_name] = counts

        # Incremental save after each flip mask
        if args.verbose and circuits:
            save_progress(reason=f"after-{flip_name}")

    # Final save
    save_progress(reason="complete")

    # Print summary
    all_counts = _global_state["all_counts"]
    all_circuits = _global_state["all_circuits"]
    print(f"\nTotal: {len(all_circuits)} circuits")
    for flip_name, counts in all_counts.items():
        total = sum(counts.values())
        print(f"  {flip_name}: {total} circuits")


if __name__ == "__main__":
    main()
