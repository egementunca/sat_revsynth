"""Staggered exploration of ECA57 identity circuits.

Automates the discovery of identity templates for increasing widths and depths.
Strategy:
- Starts at small width (W=3), traverses up to MAX_GC.
- Increments width, traverses up to newly defined MAX_GC.
- For each (W, GC):
  1. Synthesize all base templates via SAT.
  2. Unroll them immediately to find variants.
  3. Extract witnesses to populate the database.
  
Usage:
    python scripts/explore_staggered.py --db data/collection.lmdb --max-width 9
"""
import argparse
import sys
import os
import time
from pathlib import Path
from typing import List, Optional

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src"))

from database.lmdb_env import TemplateDBEnv
from database.basis import ECA57Basis
from database.templates import TemplateStore, OriginKind, decode_gates_eca57
from database.unroll import unroll_template, UnrollConfig, unroll_and_insert
from database.witnesses import WitnessStore
from synthesizers.eca57_dimgroup_synthesizer import ECA57DimGroupSynthesizer

# Parallel handling
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing


# Define depth limits per width
MAX_GC_BY_WIDTH = {
    3: 12,
    4: 10,
    5: 8,
    6: 7, 
    7: 6,
    8: 6,
    9: 6
}

def get_default_workers():
    """Get default worker count (all cores - 1)."""
    return max(1, multiprocessing.cpu_count() - 1)


def run_unroll_job(gates, width, basis, config):
    """Worker function to run unrolling. Must be top-level for pickling."""
    # Convert generator to list so it can be returned across process boundaries
    return list(unroll_template(gates, width, basis, config))


def explore_staggered(db_path: str, max_width_limit: int, solver_inputs: str, skip_witnesses: bool = False, parallel_unroll: bool = True, min_width_limit: int = 3, num_workers: Optional[int] = None, single_gc: Optional[int] = None):
    """Run staggered exploration loop.
    
    Args:
        single_gc: If provided, only explore this specific gate count (for cluster jobs).
    """
    
    # Determined effective workers
    if num_workers is None:
        effective_workers = get_default_workers()
    else:
        effective_workers = num_workers

    # Parse solver input: "glucose4,cadical153" -> ["glucose4", "cadical153"] or "glucose4"
    # Parse solver input: "glucose4+cadical153" or "glucose4,cadical153"
    if "+" in solver_inputs:
        solver_arg = solver_inputs.split("+")
        print(f"Solver Racer Enabled: {solver_arg}")
    elif "," in solver_inputs:
        solver_arg = solver_inputs.split(",")
        print(f"Solver Racer Enabled: {solver_arg}")
    else:
        solver_arg = solver_inputs
        print(f"Solver: {solver_arg}")

    print(f"Starting staggered exploration -> {db_path}")
    print(f"Width Range: {min_width_limit} - {max_width_limit}")
    print(f"Skip Witnesses: {skip_witnesses}")
    print(f"Parallel Unroll: {parallel_unroll} (Workers: {effective_workers})")
    print("=" * 60)
    
    env = TemplateDBEnv(db_path)
    basis = ECA57Basis()
    store = TemplateStore(env, basis)
    witness_store = WitnessStore(env, basis)
    
    # Unroll config
    unroll_config = UnrollConfig(
        swap_dfs_budget=1000,
        do_mirror=True,
        do_permute=True,
        do_rotate=True,
        do_swap_dfs=True
    )
    
    start_total = time.time()
    
    for width in range(min_width_limit, max_width_limit + 1):
        # Determine depth limit for this width
        max_gc = MAX_GC_BY_WIDTH.get(width, 6)
        
        # If single_gc is specified, only run that gc
        if single_gc is not None:
            gc_range = [single_gc] if 2 <= single_gc <= max_gc else []
        else:
            gc_range = range(2, max_gc + 1)
        
        print(f"\n>>> Exploring Width {width} (GC range: {list(gc_range)})")
        
        for gc in gc_range:
            print(f"  [{width},{gc}] Synthesizing...", end=" ", flush=True)
            step_start = time.time()
            
            # 1. Synthesize
            # Pass list of solvers if racing
            synth = ECA57DimGroupSynthesizer(width, gc, solver_arg)
            dimgroup = synth.synthesize()
            
            synth_count = len(dimgroup)
            synth_time = time.time() - step_start
            print(f"Found {synth_count} in {synth_time:.1f}s.", end=" ")
            
            if synth_count == 0:
                print("Done.")
                continue
            
            # 2. Store & Unroll
            print("Unrolling...", end=" ", flush=True)
            new_templates = 0
            new_variants = 0
            
            # Helper for unrolling result processing
            def process_unroll_result(source_gates, source_record, variants_iter):
                count = 0
                for variant_gates, unroll_ops in variants_iter:
                    # Insert variant
                    rec = store.insert_template(
                        gates=variant_gates,
                        width=width,
                        origin=OriginKind.UNROLL,
                        origin_template_id=source_record.template_id,
                        unroll_ops=unroll_ops,
                        family_hash=source_record.family_hash
                    )
                    if rec:
                        count += 1
                return count

            if parallel_unroll and synth_count > 1:
                # Parallel unrolling (use effective_workers)
                with ProcessPoolExecutor(max_workers=effective_workers) as executor:
                    futures = {}
                    
                    # 1. Insert base templates first (need IDs for linking)
                    base_records = []
                    for circuit in dimgroup:
                        # Fix: use method call
                        gates = [(g.target, g.ctrl1, g.ctrl2) for g in circuit.gates()]
                        rec = store.insert_template(gates, width, OriginKind.SAT)
                        if rec:
                            new_templates += 1
                            base_records.append((rec, gates))
                    
                    # 2. Submit unroll tasks
                    for record, gates in base_records:
                        # Submit task using top-level helper function
                        fut = executor.submit(run_unroll_job, gates, width, basis, unroll_config)
                        futures[fut] = record

                    # 3. Collect results
                    for fut in as_completed(futures):
                        record = futures[fut]
                        try:
                            variants = fut.result()
                            inserted = process_unroll_result(None, record, variants)
                            new_variants += inserted
                        except Exception as e:
                            print(f"[ERR: {e}]", end="")
            else:
                # Sequential unrolling
                for circuit in dimgroup:
                    gates = [(g.target, g.ctrl1, g.ctrl2) for g in circuit.gates()]
                    
                    # Insert base template
                    record = store.insert_template(
                        gates=gates,
                        width=width,
                        origin=OriginKind.SAT
                    )
                    
                    if record:
                        new_templates += 1
                        # Unroll immediately
                        inserted, _ = unroll_and_insert(store, record, gates, width, unroll_config)
                        new_variants += inserted
            
            print(f"Stored {new_templates} base + {new_variants} variants.", end=" ")
            
            # 3. Witnesses (Optional)
            if not skip_witnesses:
                print("Witnesses...", end=" ", flush=True)
                new_witnesses = 0
                for record in store.iter_by_dims(width, gc):
                    wit = witness_store.build_witnesses_from_template(record)
                    if wit:
                        new_witnesses += 1
                
                print(f"Added {new_witnesses} new.")
            else:
                print("Witnesses skipped.")
            
    print("\n" + "=" * 60)
    elapsed = time.time() - start_total
    stats = env.stats()
    print(f"Exploration Complete in {elapsed:.1f}s")
    print(f"Final DB Stats: {stats}")
    env.close()


def main():
    parser = argparse.ArgumentParser(description="Staggered ECA57 Exploration")
    parser.add_argument("--db", required=True, help="Path to LMDB database")
    parser.add_argument("--max-width", type=int, default=9, help="Maximum width to explore")
    parser.add_argument("--min-width", type=int, default=3, help="Minimum width to start from")
    parser.add_argument("--solver", default="glucose4", help="SAT solver name(s), comma-separated")
    parser.add_argument("--skip-witnesses", action="store_true", help="Skip inline witness extraction")
    parser.add_argument("--no-parallel", action="store_true", help="Disable parallel unrolling")
    parser.add_argument("--workers", type=int, default=None, help="Number of parallel workers (default: all cores - 1)")
    parser.add_argument("--single-gc", type=int, default=None, help="Only explore this specific gate count (for cluster jobs)")
    
    args = parser.parse_args()
    explore_staggered(args.db, args.max_width, args.solver, args.skip_witnesses, not args.no_parallel, args.min_width, args.workers, args.single_gc)


if __name__ == "__main__":
    main()
