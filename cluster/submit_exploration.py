#!/usr/bin/env python3
"""Submit ECA57 template exploration jobs to BU SCC cluster.

Submits separate jobs for each (width, gc) combination to enable
high-memory exploration of large template spaces.

Usage:
    python cluster/submit_exploration.py                    # Submit all
    python cluster/submit_exploration.py --dry-run          # Preview only
    python cluster/submit_exploration.py --width 4 --gc 8   # Single job
    python cluster/submit_exploration.py --resume           # Skip completed
"""
from __future__ import annotations

import argparse
import subprocess
import os
from pathlib import Path
from typing import List, Tuple


# Memory requirements per (width, gc) - estimated from empirical runs
# Format: (width, gc): (cores, mem_per_core_gb, walltime_hours)
RESOURCE_ESTIMATES = {
    # Width 4: Moderate memory
    (4, 4): (4, 4, 4),
    (4, 5): (4, 4, 8),
    (4, 6): (8, 4, 12),
    (4, 7): (8, 6, 24),
    (4, 8): (8, 8, 48),     # ~64GB, crashed on MacBook
    (4, 9): (8, 10, 72),    # ~80GB
    (4, 10): (8, 12, 96),   # ~96GB
    
    # Width 5: Higher memory
    (5, 4): (4, 4, 4),
    (5, 5): (8, 4, 8),
    (5, 6): (8, 6, 24),
    (5, 7): (8, 8, 48),
    (5, 8): (8, 12, 72),
    
    # Width 6: Very high memory
    (6, 4): (8, 4, 8),
    (6, 5): (8, 6, 24),
    (6, 6): (8, 8, 48),
    (6, 7): (8, 12, 96),
    
    # Width 7-8: Maximum memory
    (7, 4): (8, 6, 24),
    (7, 5): (8, 8, 48),
    (7, 6): (8, 12, 96),
    (8, 4): (8, 6, 24),
    (8, 5): (8, 8, 48),
    (8, 6): (8, 12, 96),
}

# Default resources for unlisted combinations
DEFAULT_RESOURCES = (8, 8, 48)  # 8 cores, 8GB/core, 48 hours


def get_exploration_targets(min_width: int, max_width: int) -> List[Tuple[int, int]]:
    """Get list of (width, gc) targets to explore."""
    # From explore_staggered.py
    MAX_GC_BY_WIDTH = {
        3: 12, 4: 10, 5: 8, 6: 7, 7: 6, 8: 6, 9: 6
    }
    
    targets = []
    for width in range(min_width, max_width + 1):
        max_gc = MAX_GC_BY_WIDTH.get(width, 6)
        for gc in range(2, max_gc + 1):
            targets.append((width, gc))
    
    return targets


def submit_job(
    width: int,
    gc: int,
    solver: str = "glucose4",
    skip_witnesses: bool = True,
    workers: int = 7,
    dry_run: bool = False
) -> str | None:
    """Submit a single exploration job."""
    
    script_dir = Path(__file__).parent
    sge_script = script_dir / "explore_single.sh"
    
    # Get resource estimates
    cores, mem_gb, hours = RESOURCE_ESTIMATES.get((width, gc), DEFAULT_RESOURCES)
    walltime = f"{hours}:00:00"
    
    # Build qsub command
    env_vars = f"WIDTH={width},GC={gc},SOLVER={solver},SKIP_WITNESSES={'true' if skip_witnesses else 'false'},WORKERS={workers}"
    
    cmd = [
        "qsub",
        "-v", env_vars,
        "-l", f"h_rt={walltime}",
        "-l", f"mem_per_core={mem_gb}G",
        "-pe", "omp", str(cores),
        "-N", f"eca57_w{width}g{gc}",
        str(sge_script)
    ]
    
    if dry_run:
        total_mem = cores * mem_gb
        print(f"[DRY RUN] W={width} GC={gc} | {cores} cores x {mem_gb}GB = {total_mem}GB | {hours}h")
        print(f"          {' '.join(cmd)}")
        return None
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        job_id = result.stdout.strip()
        print(f"Submitted: W={width} GC={gc} -> {job_id}")
        return job_id
    else:
        print(f"ERROR: W={width} GC={gc}: {result.stderr}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Submit ECA57 exploration jobs to BU SCC"
    )
    parser.add_argument("--dry-run", action="store_true",
                       help="Preview commands without submitting")
    parser.add_argument("--min-width", type=int, default=4,
                       help="Minimum width to explore (default: 4)")
    parser.add_argument("--max-width", type=int, default=8,
                       help="Maximum width to explore (default: 8)")
    parser.add_argument("--width", type=int,
                       help="Single width to submit")
    parser.add_argument("--gc", type=int,
                       help="Single gate count to submit (requires --width)")
    parser.add_argument("--solver", default="glucose4",
                       help="SAT solver (default: glucose4)")
    parser.add_argument("--skip-witnesses", action="store_true", default=True,
                       help="Skip witness extraction (default: True)")
    parser.add_argument("--workers", type=int, default=7,
                       help="Parallel workers for unrolling")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("ECA57 Template Exploration - BU SCC Job Submission")
    print("=" * 60)
    
    # Determine targets
    if args.width and args.gc:
        targets = [(args.width, args.gc)]
    elif args.width:
        # All GCs for specified width
        MAX_GC_BY_WIDTH = {3: 12, 4: 10, 5: 8, 6: 7, 7: 6, 8: 6}
        max_gc = MAX_GC_BY_WIDTH.get(args.width, 6)
        targets = [(args.width, gc) for gc in range(2, max_gc + 1)]
    else:
        targets = get_exploration_targets(args.min_width, args.max_width)
    
    print(f"Solver: {args.solver}")
    print(f"Skip Witnesses: {args.skip_witnesses}")
    print(f"Workers: {args.workers}")
    print(f"Jobs to submit: {len(targets)}")
    print()
    
    # Submit jobs
    jobs = []
    for width, gc in targets:
        job_id = submit_job(
            width=width,
            gc=gc,
            solver=args.solver,
            skip_witnesses=args.skip_witnesses,
            workers=args.workers,
            dry_run=args.dry_run
        )
        if job_id:
            jobs.append(job_id)
    
    print()
    if args.dry_run:
        print(f"[DRY RUN] Would submit {len(targets)} jobs")
    else:
        print(f"Submitted {len(jobs)} jobs")
        print("\nMonitor with: qstat -u $USER")
        print("Logs in: logs/")


if __name__ == "__main__":
    main()
