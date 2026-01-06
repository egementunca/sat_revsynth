"""Cluster Benchmark Script.

Runs a matrix of performance tests to determine optimal parallelization settings.
Targets a fixed workload (W=4, GC=2..10) and varies:
- Solver count (Single vs Race)
- Unroll workers count

Usage:
    python scripts/benchmark_cluster.py
"""
import subprocess
import time
import os
import multiprocessing
import sys

# Configuration
DB_PATH = "/tmp/bench_cluster.lmdb"
SCRIPT = "scripts/explore_staggered.py"
ENV_SETUP = "source .venv/bin/activate && "  # Adjust if needed

# Define Test Matrix
SOLVER_CONFIGS = [
    ("Single (Glucose)", "glucose4"),
    ("Race (2-way)", "glucose4,cadical153"),
    ("Race (4-way)", "glucose4,cadical153,maplechrono,gluecard4")
]

def get_worker_counts():
    """Return list of worker counts to test based on available CPUs."""
    cpu = multiprocessing.cpu_count()
    counts = [1, 4]
    if cpu > 4:
        counts.append(min(8, cpu))
    if cpu > 8:
        counts.append(cpu - 1)
        counts.append(cpu)
    
    # Deduplicate and sort
    return sorted(list(set(counts)))

def run_benchmark():
    worker_counts = get_worker_counts()
    results = []
    
    print(f"Starting Cluster Benchmark on {multiprocessing.cpu_count()} Cores")
    print(f"Workload: Width=4 (GC 2..10)")
    print("=" * 60)
    print(f"{'Solver':<20} | {'Workers':<8} | {'Time (s)':<10} | {'Speedup':<8}")
    print("-" * 60)
    
    baseline = 0
    
    for solver_label, solver_arg in SOLVER_CONFIGS:
        for w in worker_counts:
            # Clean previous run
            if os.path.exists(DB_PATH):
                subprocess.run("rm -rf " + DB_PATH, shell=True)
            
            cmd = [
                sys.executable, SCRIPT,
                "--db", DB_PATH,
                "--min-width", "4",
                "--max-width", "4",
                "--solver", solver_arg,
                "--workers", str(w),
                "--skip-witnesses"
            ]
            
            start = time.time()
            try:
                # Capture output to avoid clutter, print dots
                proc = subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True,
                    cwd=os.getcwd()
                )
                
                if proc.returncode != 0:
                    print(f"{solver_label:<20} | {w:<8} | ERROR      | -")
                    # print(proc.stderr) # debug
                    continue
                    
                elapsed = time.time() - start
                
                # Calculate speedup relative to first successful run
                if baseline == 0:
                    baseline = elapsed
                speedup = baseline / elapsed
                
                print(f"{solver_label:<20} | {w:<8} | {elapsed:10.2f} | {speedup:.2f}x")
                results.append((solver_label, w, elapsed))
                
            except Exception as e:
                print(f"{solver_label:<20} | {w:<8} | EXCEPTION  | -")
                print(e)

    print("-" * 60)
    print("Benchmark Complete.")
    
    # Recommendation
    if results:
        best = min(results, key=lambda x: x[2])
        print(f"\nRecommended Config: {best[0]} with {best[1]} workers ({best[2]:.2f}s)")

if __name__ == "__main__":
    run_benchmark()
