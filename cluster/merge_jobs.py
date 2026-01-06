#!/usr/bin/env python3
"""Merge per-job LMDB files into a single collection.

After cluster jobs complete, each writes to data/jobs/w{W}_gc{GC}.lmdb.
This script merges them into data/collection.lmdb.

Usage:
    python cluster/merge_jobs.py                    # Merge all
    python cluster/merge_jobs.py --dry-run          # Preview only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from database.lmdb_env import TemplateDBEnv
from database.basis import ECA57Basis
from database.templates import TemplateStore


def merge_databases(jobs_dir: Path, output_db: Path, dry_run: bool = False) -> int:
    """Merge all per-job LMDB files into a single database."""
    
    job_dbs = sorted(jobs_dir.glob("w*_gc*.lmdb"))
    
    if not job_dbs:
        print(f"No job databases found in {jobs_dir}")
        return 0
    
    print(f"Found {len(job_dbs)} job databases to merge:")
    for db in job_dbs:
        print(f"  - {db.name}")
    
    if dry_run:
        print(f"\n[DRY RUN] Would merge into: {output_db}")
        return len(job_dbs)
    
    print(f"\nMerging into: {output_db}")
    
    # Open output database
    basis = ECA57Basis()
    output_env = TemplateDBEnv(str(output_db))
    output_store = TemplateStore(output_env, basis)
    
    total_inserted = 0
    total_skipped = 0
    
    for job_db in job_dbs:
        print(f"  Merging {job_db.name}...", end=" ", flush=True)
        
        try:
            job_env = TemplateDBEnv(str(job_db))
            job_store = TemplateStore(job_env, basis)
            
            inserted = 0
            skipped = 0
            
            # Iterate all templates in job database
            for record in job_store.iter_all():
                # Try to insert into output (deduplicates by hash)
                result = output_store.insert_template(
                    gates=record.gates,
                    width=record.width,
                    origin=record.origin,
                    origin_template_id=None,  # Don't preserve origin links
                    unroll_ops=record.unroll_ops,
                    family_hash=record.family_hash
                )
                if result:
                    inserted += 1
                else:
                    skipped += 1
            
            job_env.close()
            print(f"{inserted} new, {skipped} duplicates")
            total_inserted += inserted
            total_skipped += skipped
            
        except Exception as e:
            print(f"ERROR: {e}")
    
    output_env.close()
    
    print(f"\n{'=' * 50}")
    print(f"Merge complete!")
    print(f"  Total inserted: {total_inserted}")
    print(f"  Total skipped (duplicates): {total_skipped}")
    print(f"  Output: {output_db}")
    
    return total_inserted


def main():
    parser = argparse.ArgumentParser(description="Merge per-job LMDB files")
    parser.add_argument("--jobs-dir", type=str, default="data/jobs",
                       help="Directory containing per-job LMDB files")
    parser.add_argument("--output", type=str, default="data/collection.lmdb",
                       help="Output merged database path")
    parser.add_argument("--dry-run", action="store_true",
                       help="Preview without merging")
    
    args = parser.parse_args()
    
    project_dir = Path(__file__).parent.parent
    jobs_dir = project_dir / args.jobs_dir
    output_db = project_dir / args.output
    
    merge_databases(jobs_dir, output_db, args.dry_run)


if __name__ == "__main__":
    main()
