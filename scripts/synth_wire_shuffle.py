"""Synthesize ECA57 circuits that implement wire shuffles.

Given a wire permutation w on 0..n-1, we target the function:
    y[i] = x[w[i]]

This script builds the corresponding truth table and runs SAT-based
synthesis for small widths.
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
import time
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

sys.path.insert(0, "src")

from truth_table.truth_table import TruthTable
from sat.solver import Solver
from sat.solver_racer import SolverRacer
from synthesizers.eca57_synthesizer import ECA57Synthesizer
from gates.eca57 import ECA57Circuit
from circuit.eca57_dim_group import ECA57DimGroup


def parse_perm(text: str, width: Optional[int] = None) -> List[int]:
    parts = [p.strip() for p in text.split(",") if p.strip()]
    perm = [int(p) for p in parts]
    if width is not None and len(perm) != width:
        raise ValueError(f"Permutation length {len(perm)} != width {width}")
    if sorted(perm) != list(range(len(perm))):
        raise ValueError(f"Not a permutation: {perm}")
    return perm


def wire_shuffle_values(width: int, perm: List[int]) -> List[int]:
    """Return truth table values for y[i] = x[perm[i]]."""
    size = 1 << width
    values = [0] * size
    for x in range(size):
        y = 0
        for out_idx, src_idx in enumerate(perm):
            bit = (x >> src_idx) & 1
            y |= bit << out_idx
        values[x] = y
    return values


def circuit_values(circ: ECA57Circuit) -> List[int]:
    table = circ.compute_truth_table()
    values = []
    for row in table:
        v = 0
        for i, bit in enumerate(row):
            v |= (bit & 1) << i
        values.append(v)
    return values


def draw_eca57_circuit_ascii(width: int, gates: List[Tuple[int, int, int]]) -> str:
    """ASCII drawing for ECA57: target=X, ctrl1=1, ctrl2=0."""
    if not gates:
        return "\n".join([f"q{i}: -" for i in range(width)])
    grid = [["-" for _ in range(len(gates) * 2 + 1)] for _ in range(width)]
    for idx, (target, c1, c2) in enumerate(gates):
        col = idx * 2 + 1
        lo = min(target, c1, c2)
        hi = max(target, c1, c2)
        for w in range(lo, hi + 1):
            grid[w][col] = "|"
        grid[target][col] = "X"
        grid[c1][col] = "1"
        grid[c2][col] = "0"
    return "\n".join([f"q{i}: " + "".join(grid[i]) for i in range(width)])


def synthesize_for_perm(
    width: int,
    perm: List[int],
    min_gates: int,
    max_gates: int,
    solver_name: str,
    solver_names: Optional[List[str]],
    require_all_wires: bool,
    max_solutions: int,
    exclude_swap_space: bool,
    swap_depth: Optional[int],
    swap_max_circuits: Optional[int],
) -> Optional[Tuple[int, List[Tuple[ECA57Circuit, int]]]]:
    values = wire_shuffle_values(width, perm)
    tt = TruthTable(width, values=values)
    for g in range(min_gates, max_gates + 1):
        solver_instance = (
            SolverRacer(solver_names) if solver_names else Solver(solver_name)
        )
        synth = ECA57Synthesizer(
            tt,
            gate_count=g,
            solver=solver_instance,
            disable_empty_lines=require_all_wires,
        )
        solutions: List[Tuple[ECA57Circuit, int]] = []
        while len(solutions) < max_solutions:
            t0 = time.time()
            circ = synth.solve()
            t1 = time.time()
            if circ is None:
                break
            solutions.append((circ, int((t1 - t0) * 1000)))
            synth.exclude_solution(circ)
            if exclude_swap_space:
                if swap_depth is None and swap_max_circuits is None:
                    variants = circ.swap_space_bfs()
                else:
                    variants = circ.swap_space_bfs_limited(
                        max_depth=swap_depth or 10,
                        max_circuits=swap_max_circuits or 1000,
                    )
                seen = set()
                for v in variants:
                    key = tuple(g.to_tuple() for g in v.gates())
                    if key in seen:
                        continue
                    seen.add(key)
                    synth.exclude_solution(v)
            if len(solutions) >= max_solutions:
                break
        if solutions:
            return g, solutions
    return None


def perm_cycles(perm: List[int]) -> List[List[int]]:
    n = len(perm)
    visited = [False] * n
    cycles = []
    for i in range(n):
        if visited[i]:
            continue
        j = i
        cycle = []
        while not visited[j]:
            visited[j] = True
            cycle.append(j)
            j = perm[j]
        cycles.append(cycle)
    return cycles


def perm_stats(perm: List[int]) -> Dict[str, int | str]:
    n = len(perm)
    fixed = sum(1 for i, p in enumerate(perm) if p == i)
    hamming = n - fixed
    cycles_list = perm_cycles(perm)
    cycles = len(cycles_list)
    swap_distance = n - cycles
    cycle_type = "-".join(str(len(c)) for c in sorted(cycles_list, key=len, reverse=True))
    parity = "even" if (swap_distance % 2 == 0) else "odd"
    return {
        "fixed_points": fixed,
        "hamming": hamming,
        "cycles": cycles,
        "swap_distance": swap_distance,
        "cycle_type": cycle_type,
        "parity": parity,
    }


def perm_iterator(
    width: int,
    perms: List[List[int]],
    limit: Optional[int],
    order: str,
    seed: Optional[int],
) -> Iterable[List[int]]:
    if perms:
        for p in perms:
            yield p
        return

    if order == "lex":
        it = itertools.permutations(range(width))
        if limit is not None:
            it = itertools.islice(it, limit)
        for p in it:
            yield list(p)
        return

    all_perms = [list(p) for p in itertools.permutations(range(width))]
    if order == "random":
        rng = random.Random(seed)
        rng.shuffle(all_perms)
    elif order in ("hamming-desc", "hamming-asc", "swap-desc", "swap-asc"):
        reverse = order.endswith("desc")
        key = "hamming" if "hamming" in order else "swap_distance"
        all_perms.sort(key=lambda p: perm_stats(p)[key], reverse=reverse)
    else:
        raise ValueError(f"Unknown order: {order}")

    if limit is not None:
        all_perms = all_perms[:limit]

    for p in all_perms:
        yield p


def integer_partitions(n: int, max_part: Optional[int] = None) -> Iterable[List[int]]:
    if max_part is None or max_part > n:
        max_part = n
    if n == 0:
        yield []
        return
    for k in range(min(max_part, n), 0, -1):
        for rest in integer_partitions(n - k, k):
            yield [k] + rest


def canonical_perm_from_cycle_type(width: int, cycle_type: List[int]) -> List[int]:
    if sum(cycle_type) != width:
        raise ValueError("Cycle type does not sum to width")
    perm = list(range(width))
    cursor = 0
    for length in cycle_type:
        if length == 1:
            cursor += 1
            continue
        cycle = list(range(cursor, cursor + length))
        for i in range(length):
            perm[cycle[i]] = cycle[(i + 1) % length]
        cursor += length
    return perm


def cycle_type_iterator(width: int) -> Iterable[List[int]]:
    for part in integer_partitions(width):
        yield part


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthesize ECA57 wire shuffle circuits")
    parser.add_argument("--width", type=int, help="Number of wires")
    parser.add_argument("--perm", action="append", default=[], help="Permutation like 2,0,1")
    parser.add_argument("--all-perms", action="store_true", help="Synthesize all wire perms")
    parser.add_argument("--limit", type=int, help="Limit number of perms when using --all-perms")
    parser.add_argument(
        "--cycle-types-only",
        action="store_true",
        help="Enumerate one canonical permutation per cycle type",
    )
    parser.add_argument(
        "--order",
        type=str,
        default="lex",
        choices=["lex", "hamming-desc", "hamming-asc", "swap-desc", "swap-asc", "random"],
        help="Order for permutation enumeration",
    )
    parser.add_argument("--seed", type=int, help="Random seed for --order random")
    parser.add_argument("--min-gates", type=int, default=0, help="Min gate count to try")
    parser.add_argument("--max-gates", type=int, default=8, help="Max gate count to try")
    parser.add_argument(
        "--max-solutions",
        type=int,
        default=1,
        help="Max SAT solutions to collect per permutation",
    )
    parser.add_argument(
        "--exclude-swap-space",
        dest="exclude_swap_space",
        action="store_true",
        help="Exclude swap-space variants before next SAT solve (default: enabled)",
    )
    parser.add_argument(
        "--no-exclude-swap-space",
        dest="exclude_swap_space",
        action="store_false",
        help="Disable swap-space exclusion",
    )
    parser.add_argument("--swap-depth", type=int, help="Swap-space BFS depth (optional)")
    parser.add_argument(
        "--swap-max-circuits",
        type=int,
        help="Swap-space max circuits (optional)",
    )
    parser.add_argument("--solver", type=str, default="cadical153", help="SAT solver name")
    parser.add_argument(
        "--solvers",
        type=str,
        help="Comma-separated SAT solver names to race (uses SolverRacer)",
    )
    parser.add_argument(
        "--require-all-wires",
        action="store_true",
        help="Require every wire to appear in some gate",
    )
    parser.add_argument("--no-ascii", action="store_true", help="Disable ASCII drawings")
    parser.add_argument("--out-json", type=str, help="Write results to JSON")
    parser.add_argument(
        "--out-dimgroup-dir",
        type=str,
        help="Write per-gate-count dimgroup JSON files",
    )
    parser.add_argument("--verify", action="store_true", help="Verify truth table")
    parser.add_argument("--summary", action="store_true", help="Print summary by distance")
    parser.add_argument("--run-notes", type=str, help="Freeform run notes")

    parser.set_defaults(exclude_swap_space=True)
    args = parser.parse_args()
    solver_names = [s.strip() for s in args.solvers.split(",")] if args.solvers else None
    if args.require_all_wires and args.min_gates == 0:
        args.min_gates = 1

    perms: List[List[int]] = []
    if args.perm:
        for p in args.perm:
            perms.append(parse_perm(p, args.width))

    if args.cycle_types_only and (args.all_perms or perms):
        raise ValueError("Use --cycle-types-only alone (no --perm or --all-perms)")

    if args.all_perms and perms:
        raise ValueError("Use either --perm or --all-perms, not both")

    if (args.all_perms or args.cycle_types_only) and args.width is None:
        raise ValueError("--width required when using --all-perms or --cycle-types-only")

    if not args.all_perms and not perms and not args.cycle_types_only:
        raise ValueError("Provide --perm or use --all-perms or --cycle-types-only")

    if args.width is None and perms:
        args.width = len(perms[0])

    width = args.width
    if width is None:
        raise ValueError("Missing width")

    results = []
    dimgroups = {}
    start = time.time()
    run_started = datetime.utcnow().isoformat()
    total = 0
    found = 0

    if args.cycle_types_only:
        perm_iter = (
            canonical_perm_from_cycle_type(width, ct) for ct in cycle_type_iterator(width)
        )
    else:
        perm_iter = perm_iterator(width, perms, args.limit, args.order, args.seed)

    for perm in perm_iter:
        total += 1
        label = ",".join(str(x) for x in perm)
        print(f"perm [{label}] ...")
        stats = perm_stats(perm)
        sol = synthesize_for_perm(
            width,
            perm,
            args.min_gates,
            args.max_gates,
            args.solver,
            solver_names,
            args.require_all_wires,
            args.max_solutions,
            args.exclude_swap_space,
            args.swap_depth,
            args.swap_max_circuits,
        )
        if sol is None:
            print("  UNSAT within gate bound")
            results.append({"perm": perm, "found": False, "stats": stats})
            continue

        gate_count, solutions = sol
        for idx, (circ, solve_ms) in enumerate(solutions):
            gates = [g.to_tuple() for g in circ.gates()]
            found += 1

            if args.verify:
                target_vals = wire_shuffle_values(width, perm)
                actual_vals = circuit_values(circ)
                if actual_vals != target_vals:
                    raise RuntimeError("Verification failed for perm " + str(perm))

            print(f"  gates: {gate_count} (solution {idx + 1})")
            print(f"  gate_list: {gates}")
            if not args.no_ascii:
                print(draw_eca57_circuit_ascii(width, gates))

            results.append(
                {
                    "perm": perm,
                    "found": True,
                    "gate_count": gate_count,
                    "gates": gates,
                    "stats": stats,
                    "solution_index": idx,
                    "synth_time_ms": solve_ms,
                }
            )

            if args.out_dimgroup_dir:
                dg = dimgroups.get(gate_count)
                if dg is None:
                    dg = ECA57DimGroup(width, gate_count)
                    dimgroups[gate_count] = dg
                dg.append(circ)

    elapsed = time.time() - start
    print(f"Done. perms={total}, found={found}, elapsed={elapsed:.2f}s")

    if args.summary:
        by_hamming = {}
        by_swap = {}
        for r in results:
            h = r["stats"]["hamming"]
            s = r["stats"]["swap_distance"]
            by_hamming[h] = by_hamming.get(h, 0) + 1
            by_swap[s] = by_swap.get(s, 0) + 1
        print("Hamming distance counts:", dict(sorted(by_hamming.items())))
        print("Swap distance counts:", dict(sorted(by_swap.items())))

    if args.out_json:
        run_meta = {
            "width": width,
            "min_gates": args.min_gates,
            "max_gates": args.max_gates,
            "solver": f"racer:{','.join(solver_names)}" if solver_names else args.solver,
            "order": args.order,
            "seed": args.seed,
            "cycle_types_only": args.cycle_types_only,
            "max_solutions": args.max_solutions,
            "exclude_swap_space": args.exclude_swap_space,
            "swap_depth": args.swap_depth,
            "swap_max_circuits": args.swap_max_circuits,
            "require_all_wires": args.require_all_wires,
            "run_notes": args.run_notes,
            "started_at": run_started,
            "elapsed_sec": elapsed,
        }
        with open(args.out_json, "w", encoding="utf-8") as f:
            json.dump({"width": width, "run": run_meta, "results": results}, f, indent=2)

    if args.out_dimgroup_dir:
        import os

        os.makedirs(args.out_dimgroup_dir, exist_ok=True)
        for gate_count, dg in dimgroups.items():
            path = os.path.join(
                args.out_dimgroup_dir, f"dimgroup_w{width}_g{gate_count}.json"
            )
            with open(path, "w", encoding="utf-8") as f:
                json.dump(dg.to_dict(), f, indent=2)


if __name__ == "__main__":
    main()
