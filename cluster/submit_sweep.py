#!/usr/bin/env python3
"""Submit parameter sweep jobs to PBS/qsub cluster."""
from __future__ import annotations

import argparse
import subprocess
import os
from pathlib import Path
from itertools import product


def submit_job(
    width: int,
    gates: int,
    solver: str = "cadical153",
    gate_set: str = "mct",
    output_dir: str = "results",
    walltime: str = "24:00:00",
    mem: str = "16gb",
    ppn: int = 8,
    dry_run: bool = False
) -> str | None:
    """Submit a single PBS job.
    
    Returns:
        Job ID if submitted, None if dry run.
    """
    script_dir = Path(__file__).parent
    pbs_script = script_dir / "run_synthesis.pbs"
    
    # Build qsub command with variable overrides
    vars_str = f"WIDTH={width},GATES={gates},SOLVER={solver},GATE_SET={gate_set},OUTPUT_DIR={output_dir}"
    
    cmd = [
        "qsub",
        "-v", vars_str,
        "-l", f"walltime={walltime}",
        "-l", f"mem={mem}",
        "-l", f"nodes=1:ppn={ppn}",
        "-N", f"sat_{gate_set}_w{width}g{gates}",
        str(pbs_script)
    ]
    
    if dry_run:
        print(f"[DRY RUN] {' '.join(cmd)}")
        return None
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        job_id = result.stdout.strip()
        print(f"Submitted: width={width}, gates={gates}, solver={solver}, gate_set={gate_set} -> {job_id}")
        return job_id
    else:
        print(f"ERROR: {result.stderr}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Submit SAT RevSynth parameter sweep jobs")
    parser.add_argument("--widths", type=int, nargs="+", default=[3, 4, 5],
                       help="Circuit widths to enumerate")
    parser.add_argument("--gates", type=int, nargs="+", default=[2, 3, 4, 5],
                       help="Gate counts to enumerate")
    parser.add_argument("--solvers", type=str, nargs="+", default=["cadical153"],
                       help="SAT solvers to use")
    parser.add_argument("--gate-set", type=str, choices=["mct", "eca57"], default="mct",
                       help="Gate set type")
    parser.add_argument("--output-dir", type=str, default="results",
                       help="Output directory for results")
    parser.add_argument("--walltime", type=str, default="24:00:00",
                       help="Job walltime")
    parser.add_argument("--mem", type=str, default="16gb",
                       help="Memory per job")
    parser.add_argument("--ppn", type=int, default=8,
                       help="Processors per node")
    parser.add_argument("--dry-run", action="store_true",
                       help="Print commands without submitting")
    
    args = parser.parse_args()
    
    # Generate all parameter combinations
    combinations = list(product(args.widths, args.gates, args.solvers))
    
    print(f"Submitting {len(combinations)} jobs...")
    print(f"Gate set: {args.gate_set}")
    print(f"Output dir: {args.output_dir}")
    print()
    
    jobs = []
    for width, gates, solver in combinations:
        job_id = submit_job(
            width=width,
            gates=gates,
            solver=solver,
            gate_set=args.gate_set,
            output_dir=args.output_dir,
            walltime=args.walltime,
            mem=args.mem,
            ppn=args.ppn,
            dry_run=args.dry_run
        )
        if job_id:
            jobs.append(job_id)
    
    print()
    print(f"Submitted {len(jobs)} jobs")


if __name__ == "__main__":
    main()
