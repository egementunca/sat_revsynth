#!/usr/bin/env python3
"""Submit parameter sweep jobs to BU SCC cluster for Table II enumeration.

This script submits jobs to enumerate all identity templates matching
Table II from the paper (widths 2-7, gates 1-6).

Usage:
    python submit_table2_bu.py              # Submit all jobs from Table II
    python submit_table2_bu.py --dry-run    # Preview without submitting
    python submit_table2_bu.py --small      # Small test (w=2-3, g=2-3)
"""
from __future__ import annotations

import argparse
import subprocess
import os
from pathlib import Path


# Table II from paper: (width, max_gates) pairs where meaningful circuits exist
# Width 1: no identity templates (trivial)
# Width 2: gates 2-6 produce circuits
# Width 3-7: gates 1-6 produce circuits
TABLE_II_PARAMS = []
for width in range(2, 8):  # widths 2-7
    for gates in range(1, 7):  # gates 1-6
        # Skip combinations that produce 0 circuits per Table II
        if width == 2 and gates == 1:
            continue  # 0 circuits
        if width == 3 and gates in [1, 2, 3, 4, 5, 6]:
            if gates == 1:
                continue  # 0 circuits
        TABLE_II_PARAMS.append((width, gates))


def submit_job(
    width: int,
    gates: int,
    solver: str = "cadical153",
    gate_set: str = "mct",
    output_dir: str = "results",
    walltime: str = "24:00:00",
    mem_per_core: str = "2G",
    cores: int = 8,
    dry_run: bool = False
) -> str | None:
    """Submit a single SGE job to BU SCC.
    
    Returns:
        Job ID if submitted, None if dry run.
    """
    script_dir = Path(__file__).parent
    sge_script = script_dir / "run_synthesis_bu.sh"
    
    # Build qsub command with variable overrides
    cmd = [
        "qsub",
        "-v", f"WIDTH={width},GATES={gates},SOLVER={solver},GATE_SET={gate_set},OUTPUT_DIR={output_dir}",
        "-l", f"h_rt={walltime}",
        "-l", f"mem_per_core={mem_per_core}",
        "-pe", "omp", str(cores),
        "-N", f"sat_w{width}g{gates}",
        str(sge_script)
    ]
    
    if dry_run:
        print(f"[DRY RUN] {' '.join(cmd)}")
        return None
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        job_id = result.stdout.strip()
        print(f"Submitted: width={width}, gates={gates} -> {job_id}")
        return job_id
    else:
        print(f"ERROR submitting width={width}, gates={gates}: {result.stderr}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Submit SAT RevSynth jobs for Table II enumeration on BU SCC"
    )
    parser.add_argument("--dry-run", action="store_true",
                       help="Print commands without submitting")
    parser.add_argument("--small", action="store_true",
                       help="Small test: only widths 2-3, gates 2-3")
    parser.add_argument("--solver", type=str, default="cadical153",
                       choices=["cadical153", "glucose4", "minisat22"],
                       help="SAT solver (default: cadical153, fastest for enumeration)")
    parser.add_argument("--gate-set", type=str, choices=["mct", "eca57"], default="mct")
    parser.add_argument("--output-dir", type=str, default="results")
    parser.add_argument("--walltime", type=str, default="48:00:00",
                       help="Job walltime (default: 48h for large enumerations)")
    
    args = parser.parse_args()
    
    # Select parameter set
    if args.small:
        params = [(w, g) for w, g in TABLE_II_PARAMS if w <= 3 and g <= 3]
    else:
        params = TABLE_II_PARAMS
    
    print(f"SAT RevSynth Table II Enumeration - BU SCC")
    print(f"==========================================")
    print(f"Solver: {args.solver}")
    print(f"Gate set: {args.gate_set}")
    print(f"Jobs to submit: {len(params)}")
    print(f"Walltime: {args.walltime}")
    print()
    
    # Estimate total circuits based on Table II
    print("Expected circuits per (width, gates):")
    paper_counts = {
        (2, 2): 1, (2, 3): 4, (2, 4): 24, (2, 5): 176, (2, 6): 1540,
        (3, 2): 0, (3, 3): 0, (3, 4): 0, (3, 5): 0, (3, 6): 0,
        (4, 2): 1, (4, 3): 34, (4, 4): 348, (4, 5): 3296, (4, 6): 33220,
        (5, 2): 0, (5, 3): 20, (5, 4): 240, (5, 5): 2400, (5, 6): 24800,
        (6, 2): 1, (6, 3): 360, (6, 4): 13104, (6, 5): 269744, (6, 6): 4626800,
        (7, 2): 0, (7, 3): 504, (7, 4): 28644, (7, 5): 674352, (7, 6): 12343240,
    }
    for w, g in params:
        count = paper_counts.get((w, g), "?")
        print(f"  w={w}, g={g}: {count} circuits")
    print()
    
    # Submit jobs
    jobs = []
    for width, gates in params:
        job_id = submit_job(
            width=width,
            gates=gates,
            solver=args.solver,
            gate_set=args.gate_set,
            output_dir=args.output_dir,
            walltime=args.walltime,
            dry_run=args.dry_run
        )
        if job_id:
            jobs.append(job_id)
    
    print()
    if args.dry_run:
        print(f"[DRY RUN] Would submit {len(params)} jobs")
    else:
        print(f"Submitted {len(jobs)} jobs")
        print(f"\nMonitor with: qstat")
        print(f"Results will be in: {args.output_dir}/")


if __name__ == "__main__":
    main()
