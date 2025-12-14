# Cluster Deployment Guide - Boston University SCC

Guide for running SAT RevSynth on Boston University's Shared Computing Cluster (SCC).

## Quick Start: Enumerate Table II

```bash
# On BU SCC
cd sat_revsynth
source venv/bin/activate

# Submit ALL Table II jobs (widths 2-7, gates 1-6)
python cluster/submit_table2_bu.py

# Or test with small subset first
python cluster/submit_table2_bu.py --small --dry-run
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
```

## Submitting Jobs

### Table II Enumeration (All Circuits from Paper)
```bash
python cluster/submit_table2_bu.py              # Submit all
python cluster/submit_table2_bu.py --dry-run    # Preview only
python cluster/submit_table2_bu.py --small      # Small test (w=2-3)
```

### Single Job
```bash
qsub -v WIDTH=3,GATES=4,SOLVER=cadical153 cluster/run_synthesis_bu.sh
```

### Monitor Jobs
```bash
qstat -u $USER
```

## Solver Selection

**Default: `cadical153`** - Best performance for enumeration tasks.

| Solver | Type | Notes |
|--------|------|-------|
| `cadical153` | Builtin | **Recommended** - fastest for SAT enumeration |
| `glucose4` | Builtin | Good alternative |
| `minisat22` | Builtin | Lightweight |

## Expected Results (Table II)

| Width | Gates | Circuits |
|-------|-------|----------|
| 2 | 2-6 | 1 to 1,540 |
| 4 | 2-6 | 1 to 33,220 |
| 6 | 2-6 | 1 to 4,626,800 |
| 7 | 3-6 | 504 to 12,343,240 |

## Collect Results

```bash
python cluster/collect_results.py results/ --summary
python cluster/collect_results.py results/ --populate-db circuits.db
```
