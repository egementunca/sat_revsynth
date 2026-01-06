# Cluster Deployment Guide - Boston University SCC

Guide for running SAT RevSynth ECA57 template exploration on Boston University's Shared Computing Cluster (SCC).

## Quick Start: Template Exploration

```bash
# On BU SCC
cd sat_revsynth
source venv/bin/activate

# Preview all jobs (dry run)
python cluster/submit_exploration.py --dry-run

# Submit single test job first
qsub -v WIDTH=4,GC=4 cluster/explore_single.sh

# If test passes, submit all jobs
python cluster/submit_exploration.py
```

## Setup

```bash
# On SCC login node
cd ~/sat_revsynth

# Create virtual environment (use Python 3.10+)
module load python3/3.11.4
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create logs and data directories
mkdir -p logs data
```

## Submitting Jobs

### Full Exploration (Width 4-8)
```bash
python cluster/submit_exploration.py              # Submit all
python cluster/submit_exploration.py --dry-run    # Preview only
python cluster/submit_exploration.py --width 4    # All GCs for width 4
python cluster/submit_exploration.py --width 4 --gc 8   # Single job
```

### Single Job (Manual)
```bash
qsub -v WIDTH=4,GC=8,SOLVER=glucose4 cluster/explore_single.sh
```

### Monitor Jobs
```bash
qstat -u $USER                    # List your jobs
qstat -j <JOB_ID>                 # Job details
tail -f logs/eca57_w4g8.*.log     # Follow log
```

## Resource Estimates

| Width | GC | Memory (est.) | Walltime |
|-------|----|---------------|----------|
| 4 | 4-6 | 16-32 GB | 4-12h |
| 4 | 7-8 | 48-64 GB | 24-48h |
| 4 | 9-10 | 80-96 GB | 72-96h |
| 5 | 6-8 | 48-96 GB | 24-72h |
| 6-8 | 4-6 | 32-96 GB | 24-96h |

## Solver Selection

**Default: `glucose4`** - Good balance of speed and memory.

| Solver | Type | Notes |
|--------|------|-------|
| `glucose4` | Builtin | **Recommended** - good for large enumerations |
| `cadical153` | Builtin | Fast but higher memory |
| `minisat22` | Builtin | Lightweight |

## Results

Results are written to `data/collection.lmdb` (LMDB database).

```bash
# Check database stats
python -c "from src.database.lmdb_env import TemplateDBEnv; print(TemplateDBEnv('data/collection.lmdb').stats())"
```

## Troubleshooting

### Job runs out of memory
Increase `mem_per_core` in `submit_exploration.py` RESOURCE_ESTIMATES.

### Job times out
Increase walltime in RESOURCE_ESTIMATES or submit with `--walltime`.

### Results not saved
Check that `/scratch/$USER` exists and has space. Results copy back on job completion.
