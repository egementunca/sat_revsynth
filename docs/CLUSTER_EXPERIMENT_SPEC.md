# Cluster Experiment Specification: Separate Template Generation & Distillation

## Pre-Reading Requirements

Read these files before implementing:

### Core Documentation
1. [CLUSTER.md](file:///Users/egementunca/research-group/sat_revsynth/cluster/CLUSTER.md) - Existing cluster setup guide
2. [DATABASES.md](file:///Users/egementunca/research-group/local_mixing/docs/DATABASES.md) - Database schema reference
3. [explore_staggered.py](file:///Users/egementunca/research-group/sat_revsynth/scripts/explore_staggered.py) - Main exploration script (has MIN/MAX GC limits)

### Existing Cluster Scripts
4. [explore_single.sh](file:///Users/egementunca/research-group/sat_revsynth/cluster/explore_single.sh) - Template generation job
5. [submit_exploration.py](file:///Users/egementunca/research-group/sat_revsynth/cluster/submit_exploration.py) - Job submission script
6. [merge_jobs.py](file:///Users/egementunca/research-group/sat_revsynth/cluster/merge_jobs.py) - Database merge script

### Witness Implementation
7. [witnesses.py](file:///Users/egementunca/research-group/sat_revsynth/src/database/witnesses.py) - WitnessStore class
8. [eca57_cli.py](file:///Users/egementunca/research-group/sat_revsynth/src/eca57_cli.py) - CLI `build-witnesses` command

---

## Gate Count Limits (from explore_staggered.py)

**These must be kept in sync in `submit_exploration.py`!**

```python
# Minimum GC where identity circuits exist
MIN_GC_BY_WIDTH = {
    3: 2,   # w3g2 first identity
    4: 4,   # w4g2, w4g3 = UNSAT
    5: 4,   # w5g2, w5g3 = UNSAT  
    6: 4,   # w6g2, w6g3 = UNSAT
    7: 6,   # w7g2-g5 = UNSAT
    8: 6,   # Estimated
    9: 6    # Estimated
}

# Maximum GC to explore (increase these as needed)
MAX_GC_BY_WIDTH = {
    3: 12,
    4: 10,
    5: 8,
    6: 7, 
    7: 6,
    8: 6,
    9: 6
}
```

> **IMPORTANT**: If you add new widths or want bigger maxes, update BOTH `explore_staggered.py` AND `submit_exploration.py`.

---

## CRITICAL: NO TIME LIMITS

> **DO NOT set any `h_rt`, `walltime`, or `time_limit` parameters for cluster jobs.**
> 
> The cluster can run indefinitely. Let all SAT synthesis and exploration jobs complete naturally without timeouts.

---

## REQUIRED: SAT Solver Racing

Always use multiple SAT solvers in parallel (racing). The default is:

```bash
--solver "kissat-sc2024+glucose4+cadical153+maplesat"
```

This runs 4 solvers simultaneously and uses whichever finishes first. Use `+` as separator (not `,`) for safe passing through `qsub`.

---

## Implementation Task

### Goal
Create a separate cluster job script for witness distillation so template generation runs independently.

### Current Flow (Blocking)
```
explore_single.sh → generates templates → [waits for distillation]
```

### Target Flow (Non-Blocking)
```
Job 1: explore_single.sh → generates templates (--skip-witnesses)
Job 2: merge_jobs.py → merges per-job LMDBs
Job 3: distill_witnesses.sh → distills witnesses from merged DB
```

---

## Implementation Spec

### Task 1: Create `cluster/distill_witnesses.sh`

```bash
#!/bin/bash
#$ -N eca57_distill
#$ -pe omp 4
#$ -l mem_per_core=16G
#$ -j y
#$ -V
#$ -cwd
#$ -o logs/$JOB_NAME.$JOB_ID.log
# NOTE: NO h_rt set - job runs until completion

set -e

PROJECT_DIR="${SGE_O_WORKDIR:-$(cd "$(dirname "$0")/.." && pwd)}"
DB_PATH="${DB_PATH:-data/collection.lmdb}"

echo "=============================================="
echo "ECA57 Witness Distillation"
echo "=============================================="
echo "DB: $DB_PATH"
echo "Started: $(date)"

cd "$PROJECT_DIR"

# Load GCC for pysat
module load gcc/12.2.0

# Activate venv
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Run distillation
python3 -m src.eca57_cli build-witnesses --db "$DB_PATH"

echo "=============================================="
echo "Distillation completed: $(date)"
echo "=============================================="
```

### Task 2: Add Submit Helper (Optional)

Add to `submit_exploration.py` or create `submit_distillation.py`:

```python
def submit_distillation(db_path: str = "data/collection.lmdb", dry_run: bool = False):
    """Submit distillation job after merge. NO time limit."""
    cmd = [
        "qsub",
        "-v", f"DB_PATH={db_path}",
        "-l", "mem_per_core=16G",
        "-pe", "omp", "4",
        "-N", "eca57_distill",
        "cluster/distill_witnesses.sh"
    ]
    if dry_run:
        print(f"[DRY RUN] {' '.join(cmd)}")
    else:
        subprocess.run(cmd)
```

---

## Usage Commands

```bash
# Step 1: Submit template generation jobs (no witness wait)
python cluster/submit_exploration.py --skip-witnesses

# Step 2: After all jobs complete, merge databases
python cluster/merge_jobs.py

# Step 3: Submit distillation job
qsub cluster/distill_witnesses.sh
# OR with custom DB path:
qsub -v DB_PATH=data/custom.lmdb cluster/distill_witnesses.sh
```

---

## Resource Estimates

| Job Type | Cores | Memory |
|----------|-------|--------|
| Template Gen (w4g8) | 8 | 64GB |
| Template Gen (w5g7) | 8 | 64GB |
| Merge | 1 | 16GB |
| Distillation | 4 | 64GB |

---

## Verification

1. Run single template job: `qsub -v WIDTH=4,GC=6 cluster/explore_single.sh`
2. Check output: `ls data/jobs/w4_gc6.lmdb/`
3. Run distillation: `qsub cluster/distill_witnesses.sh`
4. Verify witnesses: `python -c "from src.database.lmdb_env import TemplateDBEnv; e=TemplateDBEnv('data/collection.lmdb'); print(e.stats())"`
