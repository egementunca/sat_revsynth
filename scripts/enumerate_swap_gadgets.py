#!/usr/bin/env python3
"""Enumerate ECA57 swap gadgets via SAT.

Finds distinct 3-wire circuits that swap wire 0 and 1 while preserving wire 2.
Outputs a JSON library suitable for swap gadget sampling.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import sys
from pathlib import Path as _Path

# Add src to path
sys.path.insert(0, str(_Path(__file__).parent.parent / "src"))

from truth_table.truth_table import TruthTable
from sat.solver import Solver
from synthesizers.eca57_synthesizer import ECA57Synthesizer
from synthesizers.waksman import ECA57SwapMacro


def swap_truth_table(width: int = 3) -> TruthTable:
    values = []
    for i in range(2**width):
        bits = [(i >> b) & 1 for b in range(width)]
        bits[0], bits[1] = bits[1], bits[0]
        output = sum(b << idx for idx, b in enumerate(bits))
        values.append(output)
    return TruthTable(width, values=values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Enumerate SAT swap gadgets (3 wires).")
    parser.add_argument("--min-gates", type=int, default=6, help="Minimum gate count")
    parser.add_argument("--max-gates", type=int, default=20, help="Maximum gate count")
    parser.add_argument("--max-solutions", type=int, default=0,
                        help="Max solutions per gate count (0 = no cap)")
    parser.add_argument("--solver", type=str, default="glucose4", help="SAT solver name")
    parser.add_argument("--output", "-o", type=str, required=True, help="Output JSON path")
    parser.add_argument("--verify", action="store_true", help="Verify swap correctness")
    args = parser.parse_args()

    if args.min_gates < 1 or args.max_gates < args.min_gates:
        parser.error("Invalid gate count range")

    tt = swap_truth_table(3)

    circuits: List[Dict] = []
    counts: Dict[str, int] = {}

    for gates in range(args.min_gates, args.max_gates + 1):
        synth = ECA57Synthesizer(tt, gate_count=gates, solver=Solver(args.solver))
        found = 0
        while True:
            circuit = synth.solve()
            if circuit is None:
                break
            if args.verify and not ECA57SwapMacro.verify_swap(circuit, 0, 1, 2):
                synth.exclude_solution(circuit)
                continue
            circuits.append({
                "gate_count": len(circuit),
                "gates": [g.to_tuple() for g in circuit.gates()],
            })
            found += 1
            synth.exclude_solution(circuit)
            if args.max_solutions and found >= args.max_solutions:
                break
        if found:
            counts[str(gates)] = found

    payload = {
        "width": 3,
        "swap": "wire0<->wire1, wire2 preserved",
        "counts": counts,
        "circuits": circuits,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"Wrote {len(circuits)} circuits to {output_path}")


if __name__ == "__main__":
    main()
