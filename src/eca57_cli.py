#!/usr/bin/env python3
"""CLI for ECA57 identity circuit synthesis.

Usage:
    python eca57_cli.py benchmark              # Benchmark SAT solvers
    python eca57_cli.py synth 3 4              # Synthesize width=3, gc=4
    python eca57_cli.py synth-skeleton 4 8     # One circuit w/ skeleton constraints
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


def cmd_synth_skeleton(args):
    """Synthesize a single identity circuit with skeleton constraints."""
    from truth_table.truth_table import TruthTable
    from sat.solver import Solver
    from synthesizers.eca57_skeleton_synthesizer import ECA57SkeletonSynthesizer

    print(
        "Synthesizing ECA57 identity circuit with skeleton constraints: "
        f"width={args.width}, gc={args.gc}"
    )
    print(f"Solver: {args.solver}")
    if args.chain_length is not None:
        print(f"Min adjacent collision edges: {args.chain_length}")
    if args.allow_adjacent_identical:
        print("Adjacent identical gates allowed")

    tt = TruthTable(args.width)
    solver = Solver(args.solver)
    synth = ECA57SkeletonSynthesizer(
        tt,
        gate_count=args.gc,
        solver=solver,
        chain_length=args.chain_length,
        avoid_adjacent_identical=not args.allow_adjacent_identical,
    )
    circuit = synth.solve()

    if circuit is None:
        print("UNSAT: no circuit found with the requested constraints")
        return

    print(circuit)


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


def cmd_skeleton_chain(args):
    """Synthesize skeleton chain and optionally unroll with limits."""
    from synthesizers.skeleton_chain_api import (
        synthesize_skeleton_chain,
        limited_unroll,
        verify_skeleton_chain,
        estimate_unroll_size,
    )

    print("=" * 70)
    print(f"Skeleton Chain Synthesis: width={args.width}, gates={args.gates}")
    print(f"Solver: {args.solver}")
    if args.chain_length:
        print(f"Chain length constraint: {args.chain_length}")
    print("=" * 70)

    # Synthesize skeleton chain
    print("\n[1/3] Synthesizing skeleton chain...")
    start = time.time()
    skeleton = synthesize_skeleton_chain(
        wires=args.width,
        gates=args.gates,
        chain_length=args.chain_length,
        solver_name=args.solver,
        avoid_adjacent_identical=not args.allow_adjacent_identical,
    )
    synth_time = time.time() - start

    if skeleton is None:
        print(f"❌ UNSAT: No skeleton chain found ({synth_time:.2f}s)")
        return

    print(f"✓ Found skeleton chain ({synth_time:.2f}s)")

    # Verify it's a skeleton
    print("\n[2/3] Verifying skeleton properties...")
    is_skeleton = verify_skeleton_chain(skeleton)
    is_identity = skeleton.is_identity()

    if is_skeleton and is_identity:
        print("✓ Verified: All adjacent gates collide")
        print("✓ Verified: Circuit implements identity")
    else:
        if not is_skeleton:
            print("❌ WARNING: Not all adjacent gates collide")
        if not is_identity:
            print("❌ WARNING: Circuit does not implement identity")

    # Show circuit
    if args.show_circuit:
        print("\nSkeleton circuit:")
        print(skeleton)

    # Estimate unroll size
    if args.estimate or args.unroll:
        print("\n[3/3] Analyzing equivalence class size...")
        est = estimate_unroll_size(args.width, args.gates, is_skeleton=True)
        print(f"  Rotations: ~{est['rotations']}")
        print(f"  Mirror: {est['mirror']}×")
        print(f"  Total permutations: {est['permutations']:,}")
        print(f"  Estimated total (full unroll): {est['total_estimate']:,}")
        print(f"  Recommended max_permutations: {est['recommended_max_permutations']}")

        if not est['is_feasible_full_unroll']:
            print("  ⚠ Warning: Full unroll would generate too many circuits!")

    # Perform limited unroll if requested
    if args.unroll:
        print(f"\nGenerating up to {args.max_circuits} equivalent circuits...")
        start = time.time()

        variants = limited_unroll(
            skeleton,
            max_circuits=args.max_circuits,
            max_permutations=args.max_permutations,
            use_skeleton_mode=True,  # Fast path for skeletons
        )

        unroll_time = time.time() - start
        print(f"✓ Generated {len(variants):,} circuits ({unroll_time:.2f}s)")

        # Save if output specified
        if args.output:
            from pathlib import Path
            import json

            output_path = Path(args.output)

            # Save circuits as JSON
            data = {
                "width": args.width,
                "gates": args.gates,
                "skeleton": {
                    "gates": [
                        {"target": g.target, "ctrl1": g.ctrl1, "ctrl2": g.ctrl2}
                        for g in skeleton.gates()
                    ]
                },
                "variants_count": len(variants),
                "variants": [
                    {
                        "gates": [
                            {"target": g.target, "ctrl1": g.ctrl1, "ctrl2": g.ctrl2}
                            for g in v.gates()
                        ]
                    }
                    for v in variants[:args.save_limit]  # Limit saved variants
                ],
            }

            with open(output_path, "w") as f:
                json.dump(data, f, indent=2)

            print(f"Saved {min(len(variants), args.save_limit)} circuits to {output_path}")

    print("\n" + "=" * 70)
    print("Done!")


def cmd_build_skeleton_db(args):
    """Build skeleton chain database indexed by taxonomy."""
    from database.skeleton_db import (
        SkeletonDBBuilder,
        SkeletonDBConfig,
        count_collision_taxonomies,
    )

    print("=" * 70)
    print("SKELETON CHAIN DATABASE BUILDER")
    print("=" * 70)

    print(f"\nConfiguration:")
    print(f"  Output: {args.output}")
    print(f"  Wires: {args.min_wires} - {args.max_wires}")
    print(f"  Target taxonomies per width: {args.target_taxonomies}")
    print(f"  Max variants per skeleton: {args.max_variants}")
    print(f"  Solver: {args.solver}")
    print(f"  Map size: {args.map_size / (1024**3):.1f} GB")

    total_collision_taxonomies = count_collision_taxonomies()
    print(f"\n  Total possible collision taxonomies: {total_collision_taxonomies}")

    config = SkeletonDBConfig(
        map_size=args.map_size,
        min_wires=args.min_wires,
        max_wires=args.max_wires,
        target_taxonomies_per_width=args.target_taxonomies,
        max_synthesis_attempts=args.max_attempts,
    )

    print("\n" + "=" * 70)
    print("Building database...\n")

    def progress(width, attempt, found):
        print(f"  Width {width}: attempt {attempt:3d}, {found:3d} taxonomies", end="\r")

    start_time = time.time()

    with SkeletonDBBuilder(args.output, config) as builder:
        stats = builder.build(
            max_variants=args.max_variants,
            solver_name=args.solver,
            progress_callback=progress if not args.quiet else None,
        )

        final_stats = builder.get_stats()

    elapsed = time.time() - start_time

    print("\n\n" + "=" * 70)
    print("BUILD COMPLETE")
    print("=" * 70)

    print(f"\nSummary:")
    print(f"  Total circuits added: {stats['circuits_added']:,}")
    print(f"  Total taxonomies found: {stats['taxonomies_found']:,}")
    print(f"  Synthesis calls: {stats['synthesis_calls']:,}")
    print(f"  Elapsed time: {elapsed:.1f}s")

    print(f"\nPer-width breakdown:")
    for width in sorted(final_stats.get("taxonomies_per_width", {}).keys()):
        tax_count = final_stats["taxonomies_per_width"][width]
        circ_count = final_stats["circuits_per_width"].get(width, 0)
        print(f"  Width {width}: {tax_count} taxonomies, {circ_count:,} circuits")

    print(f"\nDatabase saved to: {args.output}")


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

    synth_skel = subparsers.add_parser(
        "synth-skeleton",
        help="Synthesize one circuit with skeleton constraints",
    )
    synth_skel.add_argument("width", type=int, help="Number of wires")
    synth_skel.add_argument("gc", type=int, help="Number of gates")
    synth_skel.add_argument("-s", "--solver", default="glucose4", help="SAT solver")
    synth_skel.add_argument(
        "--chain-length",
        type=int,
        help="Minimum adjacent collision edges (default: all)",
    )
    synth_skel.add_argument(
        "--allow-adjacent-identical",
        action="store_true",
        help="Allow adjacent identical gates (enables immediate cancellation)",
    )

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

    # Skeleton-chain command (NEW)
    skel_chain = subparsers.add_parser(
        "skeleton-chain",
        help="Synthesize skeleton chain with limited unrolling",
    )
    skel_chain.add_argument("width", type=int, help="Number of wires")
    skel_chain.add_argument("gates", type=int, help="Number of gates")
    skel_chain.add_argument("-s", "--solver", default="glucose4", help="SAT solver (default: glucose4)")
    skel_chain.add_argument(
        "--chain-length",
        type=int,
        help="Minimum collision chain length (default: all gates)",
    )
    skel_chain.add_argument(
        "--allow-adjacent-identical",
        action="store_true",
        help="Allow adjacent identical gates",
    )
    skel_chain.add_argument(
        "--unroll",
        action="store_true",
        help="Generate equivalent circuits via limited unrolling",
    )
    skel_chain.add_argument(
        "--max-circuits",
        type=int,
        default=1000,
        help="Maximum circuits to generate (default: 1000)",
    )
    skel_chain.add_argument(
        "--max-permutations",
        type=int,
        default=None,
        help="Maximum permutations to sample (default: auto)",
    )
    skel_chain.add_argument(
        "--estimate",
        action="store_true",
        help="Show estimated equivalence class size",
    )
    skel_chain.add_argument(
        "--show-circuit",
        action="store_true",
        help="Display the synthesized circuit",
    )
    skel_chain.add_argument(
        "-o",
        "--output",
        help="Output file path (JSON)",
    )
    skel_chain.add_argument(
        "--save-limit",
        type=int,
        default=100,
        help="Maximum circuits to save to file (default: 100)",
    )

    # Build-skeleton-db command (NEW)
    build_skel_db = subparsers.add_parser(
        "build-skeleton-db",
        help="Build skeleton chain database indexed by taxonomy",
    )
    build_skel_db.add_argument(
        "-o", "--output",
        required=True,
        help="Output LMDB directory path",
    )
    build_skel_db.add_argument(
        "--min-wires",
        type=int,
        default=4,
        help="Minimum wire count (default: 4)",
    )
    build_skel_db.add_argument(
        "--max-wires",
        type=int,
        default=12,
        help="Maximum wire count (default: 12)",
    )
    build_skel_db.add_argument(
        "--target-taxonomies",
        type=int,
        default=50,
        help="Target distinct taxonomies per wire count (default: 50)",
    )
    build_skel_db.add_argument(
        "--max-variants",
        type=int,
        default=100,
        help="Maximum variants per skeleton (default: 100)",
    )
    build_skel_db.add_argument(
        "--max-attempts",
        type=int,
        default=100,
        help="Maximum synthesis attempts per width (default: 100)",
    )
    build_skel_db.add_argument(
        "-s", "--solver",
        default="glucose4",
        help="SAT solver (default: glucose4)",
    )
    build_skel_db.add_argument(
        "--map-size",
        type=int,
        default=50 * 1024 * 1024 * 1024,  # 50 GB
        help="LMDB map size in bytes (default: 50GB)",
    )
    build_skel_db.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress progress output",
    )

    args = parser.parse_args()

    if args.command == "benchmark":
        cmd_benchmark(args)
    elif args.command == "synth":
        cmd_synth(args)
    elif args.command == "synth-skeleton":
        cmd_synth_skeleton(args)
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
    elif args.command == "skeleton-chain":
        cmd_skeleton_chain(args)
    elif args.command == "build-skeleton-db":
        cmd_build_skeleton_db(args)


if __name__ == "__main__":
    main()
