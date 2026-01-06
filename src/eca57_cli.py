#!/usr/bin/env python3
"""CLI for ECA57 identity circuit synthesis.

Usage:
    python eca57_cli.py benchmark              # Benchmark SAT solvers
    python eca57_cli.py synth 3 4              # Synthesize width=3, gc=4
    python eca57_cli.py collection 4 6 -o out  # Full collection synthesis
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def cmd_benchmark(args):
    """Run solver benchmark."""
    from synthesizers.eca57_dimgroup_synthesizer import benchmark_solvers
    
    print(f"Benchmarking solvers on width={args.width}, gc={args.gc}...")
    print("=" * 60)
    
    results = benchmark_solvers(args.width, args.gc)
    
    # Sort by time
    sorted_results = sorted(
        [(s, r) for s, r in results.items() if r["time"] is not None],
        key=lambda x: x[1]["time"]
    )
    
    print(f"{'Solver':<20} {'Time (s)':<12} {'Found':<8} {'Error'}")
    print("-" * 60)
    
    for solver, result in sorted_results:
        time_str = f"{result['time']:.4f}" if result['time'] else "N/A"
        found_str = "✓" if result['found'] else "✗"
        error_str = result['error'] or ""
        print(f"{solver:<20} {time_str:<12} {found_str:<8} {error_str}")
    
    # Show failed solvers
    failed = [(s, r) for s, r in results.items() if r["time"] is None]
    if failed:
        print("\nFailed solvers:")
        for solver, result in failed:
            print(f"  {solver}: {result['error']}")
    
    # Recommendation
    if sorted_results:
        best_solver = sorted_results[0][0]
        print(f"\nRecommended solver: {best_solver}")


def cmd_synth(args):
    """Synthesize circuits for a single dimension."""
    from synthesizers.eca57_dimgroup_synthesizer import ECA57DimGroupSynthesizer
    from circuit.eca57_dim_group import ECA57DimGroup
    
    print(f"Synthesizing ECA57 identity circuits: width={args.width}, gc={args.gc}")
    print(f"Solver: {args.solver}")
    print("=" * 60)
    
    def progress(iteration, count, elapsed):
        print(f"  Iteration {iteration}: found {count} circuits ({elapsed:.2f}s)")
    
    start = time.time()
    synth = ECA57DimGroupSynthesizer(args.width, args.gc, args.solver)
    dg = synth.synthesize(progress_callback=progress)
    elapsed = time.time() - start
    
    print("=" * 60)
    print(f"Found {len(dg)} identity circuits in {elapsed:.2f}s")
    
    # Verify all are identities
    non_identity = [c for c in dg if not c.is_identity()]
    if non_identity:
        print(f"WARNING: {len(non_identity)} circuits are NOT identities!")
    else:
        print("All circuits verified as identities ✓")
    
    # Save if output specified
    if args.output:
        output_path = Path(args.output)
        data = dg.to_dict()
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Saved to {output_path}")
    
    # Show sample circuits
    if args.verbose and len(dg) > 0:
        print("\nSample circuits:")
        for i, circ in enumerate(list(dg)[:3]):
            print(f"\n--- Circuit {i+1} ---")
            print(circ)


def cmd_collection(args):
    """Synthesize complete collection."""
    from synthesizers.eca57_dimgroup_synthesizer import ECA57CollectionSynthesizer
    
    print(f"Synthesizing ECA57 collection: max_width={args.max_width}, max_gc={args.max_gc}")
    print(f"Solver: {args.solver}")
    print("=" * 60)
    
    def progress(width, gc, group_count, total, elapsed):
        print(f"  [{width},{gc}]: {group_count} circuits (total: {total}, {elapsed:.1f}s)")
    
    output_path = Path(args.output) if args.output else None
    
    start = time.time()
    synth = ECA57CollectionSynthesizer(args.max_width, args.max_gc, args.solver)
    collection = synth.synthesize(
        progress_callback=progress,
        save_path=str(output_path) if output_path else None
    )
    elapsed = time.time() - start
    
    print("=" * 60)
    print(collection.summary())
    print(f"\nCompleted in {elapsed:.1f}s")
    
    if output_path:
        # Also save compact format
        compact_path = output_path.with_suffix(".txt")
        collection.save_compact(compact_path)
        print(f"Saved JSON: {output_path}")
        print(f"Saved compact: {compact_path}")


def cmd_distill(args):
    """Run distillation pipeline on a collection."""
    from excirc_distiller.eca57_excirc_distiller import ECA57ExCircDistiller
    from circuit.eca57_collection import ECA57Collection
    
    print(f"Loading collection from {args.input}...")
    coll = ECA57Collection.load_json(Path(args.input))
    print(f"Loaded: {coll.total_circuits()} identity circuits")
    print("=" * 60)
    
    distiller = ECA57ExCircDistiller(coll)
    witnesses = distiller.distill()
    
    print("=" * 60)
    print(witnesses.summary())
    
    if args.output:
        out = Path(args.output)
        witnesses.save_json(out)
        witnesses.save_compact(out.with_suffix(".txt"))
        print(f"\nSaved to {out} and {out.with_suffix('.txt')}")


def cmd_build_db(args):
    """Build LMDB database from SAT synthesis."""
    from pathlib import Path
    from database.lmdb_env import TemplateDBEnv
    from database.basis import ECA57Basis
    from database.templates import TemplateStore, OriginKind
    from synthesizers.eca57_dimgroup_synthesizer import ECA57DimGroupSynthesizer
    
    print(f"Building LMDB database: {args.output}")
    print(f"Max width: {args.max_width}, Max GC: {args.max_gc}")
    print(f"Solver: {args.solver}")
    print("=" * 60)
    
    # Open LMDB environment
    env = TemplateDBEnv(args.output)
    basis = ECA57Basis()
    store = TemplateStore(env, basis)
    
    total_inserted = 0
    total_duplicates = 0
    start = time.time()
    
    for width in range(3, args.max_width + 1):
        for gc in range(2, args.max_gc + 1):
            print(f"  Synthesizing [{width},{gc}]...", end=" ", flush=True)
            
            synth = ECA57DimGroupSynthesizer(width, gc, args.solver)
            dimgroup = synth.synthesize()
            
            inserted = 0
            for circuit in dimgroup:
                # Convert to gate tuples
                gates = [(g.target, g.ctrl1, g.ctrl2) for g in circuit.gates]
                record = store.insert_template(
                    gates=gates,
                    width=width,
                    origin=OriginKind.SAT,
                )
                if record is not None:
                    inserted += 1
                else:
                    total_duplicates += 1
            
            total_inserted += inserted
            print(f"inserted {inserted} (total: {total_inserted})")
    
    elapsed = time.time() - start
    print("=" * 60)
    print(f"Done in {elapsed:.1f}s")
    print(f"Inserted: {total_inserted}, Duplicates: {total_duplicates}")
    
    stats = env.stats()
    print(f"DB stats: {stats}")
    env.close()


def cmd_unroll(args):
    """Expand templates via unrolling."""
    from database.lmdb_env import TemplateDBEnv
    from database.basis import ECA57Basis
    from database.templates import TemplateStore, decode_gates_eca57
    from database.unroll import unroll_and_insert, UnrollConfig
    
    print(f"Unrolling from database: {args.db}")
    print(f"Seed dimensions: {args.seed_dims}")
    print(f"DFS budget: {args.dfs_budget}")
    print("=" * 60)
    
    env = TemplateDBEnv(args.db)
    basis = ECA57Basis()
    store = TemplateStore(env, basis)
    
    config = UnrollConfig(
        swap_dfs_budget=args.dfs_budget,
        do_mirror=True,
        do_permute=True,
        do_rotate=True,
        do_swap_dfs=True,
    )
    
    # Parse seed dims (e.g., "4x6" -> width=4, gc=6)
    width, gc = map(int, args.seed_dims.split("x"))
    
    total_inserted = 0
    total_duplicates = 0
    seed_count = 0
    
    print(f"Processing seeds from [{width},{gc}]...")
    
    for record in store.iter_by_dims(width, gc):
        seed_count += 1
        gates = decode_gates_eca57(record.gates_encoded)
        
        inserted, dups = unroll_and_insert(
            store, record, gates, width, config
        )
        total_inserted += inserted
        total_duplicates += dups
        
        if seed_count % 10 == 0:
            print(f"  Processed {seed_count} seeds, inserted {total_inserted}...")
    
    print("=" * 60)
    print(f"Processed {seed_count} seed templates")
    print(f"Inserted: {total_inserted}, Duplicates: {total_duplicates}")
    
    env.close()


def cmd_build_witnesses(args):
    """Build witness prefilter from templates."""
    from database.lmdb_env import TemplateDBEnv
    from database.basis import ECA57Basis
    from database.templates import TemplateStore
    from database.witnesses import WitnessStore
    
    print(f"Building witnesses from database: {args.db}")
    print(f"Max width: {args.max_width}, Max GC: {args.max_gc}")
    print("=" * 60)
    
    env = TemplateDBEnv(args.db)
    basis = ECA57Basis()
    template_store = TemplateStore(env, basis)
    witness_store = WitnessStore(env, basis)
    
    total_inserted = 0
    total_duplicates = 0
    
    for width in range(3, args.max_width + 1):
        for gc in range(2, args.max_gc + 1):
            inserted = 0
            for record in template_store.iter_by_dims(width, gc):
                witness = witness_store.build_witnesses_from_template(record)
                if witness is not None:
                    inserted += 1
                else:
                    total_duplicates += 1
            
            total_inserted += inserted
            if inserted > 0:
                print(f"  [{width},{gc}]: {inserted} witnesses")
    
    print("=" * 60)
    print(f"Total witnesses: {total_inserted}")
    print(f"Duplicates skipped: {total_duplicates}")
    
    env.close()


def main():
    parser = argparse.ArgumentParser(
        description="ECA57 Identity Circuit Synthesis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Benchmark command
    bench = subparsers.add_parser("benchmark", help="Benchmark SAT solvers")
    bench.add_argument("--width", type=int, default=3, help="Test width (default: 3)")
    bench.add_argument("--gc", type=int, default=4, help="Test gate count (default: 4)")
    
    # Synth command
    synth = subparsers.add_parser("synth", help="Synthesize single dimension")
    synth.add_argument("width", type=int, help="Number of wires")
    synth.add_argument("gc", type=int, help="Number of gates")
    synth.add_argument("-s", "--solver", default="glucose4", help="SAT solver")
    synth.add_argument("-o", "--output", help="Output file path")
    synth.add_argument("-v", "--verbose", action="store_true", help="Show sample circuits")
    
    # Collection command
    coll = subparsers.add_parser("collection", help="Synthesize full collection")
    coll.add_argument("max_width", type=int, help="Maximum width")
    coll.add_argument("max_gc", type=int, help="Maximum gate count")
    coll.add_argument("-s", "--solver", default="glucose4", help="SAT solver")
    coll.add_argument("-o", "--output", help="Output file path")
    
    # Distill command
    distill = subparsers.add_parser("distill", help="Distill witnesses from collection")
    distill.add_argument("input", help="Input collection JSON path")
    distill.add_argument("-o", "--output", help="Output witness collection path")
    
    # Build-db command (NEW)
    build_db = subparsers.add_parser("build-db", help="Build LMDB database from SAT synthesis")
    build_db.add_argument("--max-width", type=int, required=True, help="Maximum width")
    build_db.add_argument("--max-gc", type=int, required=True, help="Maximum gate count")
    build_db.add_argument("-s", "--solver", default="glucose4", help="SAT solver")
    build_db.add_argument("-o", "--output", required=True, help="Output LMDB directory")
    
    # Unroll command (NEW)
    unroll = subparsers.add_parser("unroll", help="Expand templates via unrolling")
    unroll.add_argument("--db", required=True, help="LMDB database path")
    unroll.add_argument("--seed-dims", required=True, help="Seed dimensions (e.g., 4x6)")
    unroll.add_argument("--dfs-budget", type=int, default=1000, help="DFS budget per seed")
    
    # Build-witnesses command (NEW)
    build_wit = subparsers.add_parser("build-witnesses", help="Build witness prefilter")
    build_wit.add_argument("--db", required=True, help="LMDB database path")
    build_wit.add_argument("--max-width", type=int, required=True, help="Maximum width")
    build_wit.add_argument("--max-gc", type=int, required=True, help="Maximum gate count")
    
    args = parser.parse_args()
    
    if args.command == "benchmark":
        cmd_benchmark(args)
    elif args.command == "synth":
        cmd_synth(args)
    elif args.command == "collection":
        cmd_collection(args)
    elif args.command == "distill":
        cmd_distill(args)
    elif args.command == "build-db":
        cmd_build_db(args)
    elif args.command == "unroll":
        cmd_unroll(args)
    elif args.command == "build-witnesses":
        cmd_build_witnesses(args)


if __name__ == "__main__":
    main()

