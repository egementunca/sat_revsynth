#!/usr/bin/env python3
"""Submit ECA57 witness distillation job to BU SCC cluster.

Usage:
    python cluster/submit_distillation.py                  # Submit default
    python cluster/submit_distillation.py --dry-run        # Preview only
    python cluster/submit_distillation.py --db data/custom.lmdb
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def submit_distillation(db_path: str = "data/collection.lmdb", dry_run: bool = False) -> str | None:
    """Submit distillation job after merge. NO time limit."""
    script_dir = Path(__file__).parent
    sge_script = script_dir / "distill_witnesses.sh"

    cmd = [
        "qsub",
        "-v", f"DB_PATH={db_path}",
        "-l", "mem_per_core=16G",
        "-pe", "omp", "4",
        "-N", "eca57_distill",
        str(sge_script)
    ]

    if dry_run:
        print(f"[DRY RUN] {' '.join(cmd)}")
        return None

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        job_id = result.stdout.strip()
        print(f"Submitted distillation -> {job_id}")
        return job_id

    print(f"ERROR: {result.stderr}")
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Submit ECA57 witness distillation job to BU SCC"
    )
    parser.add_argument("--db", default="data/collection.lmdb",
                        help="Merged LMDB path (default: data/collection.lmdb)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview command without submitting")

    args = parser.parse_args()
    submit_distillation(args.db, args.dry_run)


if __name__ == "__main__":
    main()
