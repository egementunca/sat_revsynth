#!/bin/bash
#$ -N eca57_explore
#$ -pe omp 8
#$ -l h_rt=48:00:00
#$ -l mem_per_core=8G
#$ -j y
#$ -V
#$ -cwd
#$ -o logs/$JOB_NAME.$JOB_ID.log

# ECA57 Template Exploration - Single (Width, GC) Job
# Designed for high-memory exploration of large template spaces
#
# Usage:
#   qsub -v WIDTH=4,GC=8 cluster/explore_single.sh

set -e

# Ensure kissat binaries are in PATH
export PATH="$HOME/bin:$PATH"

# Parameters (passed via qsub -v)
WIDTH="${WIDTH:-4}"
GC="${GC:-4}"
SOLVER="${SOLVER:-kissat-sc2024+glucose4+cadical153+maplesat}"
SKIP_WITNESSES="${SKIP_WITNESSES:-true}"
WORKERS="${WORKERS:-7}"

# Paths
PROJECT_DIR="${SGE_O_WORKDIR:-$(cd "$(dirname "$0")/.." && pwd)}"
SCRATCH_DIR="/scratch/${USER}/eca57_explore_w${WIDTH}_gc${GC}_$$"
FINAL_DB_DIR="${PROJECT_DIR}/data/jobs"
FINAL_DB="${FINAL_DB_DIR}/w${WIDTH}_gc${GC}.lmdb"
LOCAL_DB="${SCRATCH_DIR}/w${WIDTH}_gc${GC}.lmdb"

echo "=============================================="
echo "ECA57 Template Exploration"
echo "=============================================="
echo "Width: $WIDTH, GC: $GC"
echo "Solver: $SOLVER"
echo "Workers: $WORKERS"
echo "Skip Witnesses: $SKIP_WITNESSES"
echo ""
echo "Project Dir: $PROJECT_DIR"
echo "Scratch Dir: $SCRATCH_DIR"
echo "Final DB: $FINAL_DB"
echo "Started: $(date)"
echo "=============================================="

# Setup scratch directory
mkdir -p "$SCRATCH_DIR"
mkdir -p "${PROJECT_DIR}/logs"

# Each job writes to its own LMDB file (no concurrent conflicts)
echo "Writing to per-job LMDB: $LOCAL_DB"

# Load newer GCC to fix GLIBCXX errors (pysat requires newer libstdc++)
module load gcc/12.2.0

# Activate virtual environment
cd "$PROJECT_DIR"
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "Activated venv: $(which python3)"
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo "Activated .venv: $(which python3)"
else
    echo "WARNING: No virtual environment found, using system Python"
fi

# Run exploration for single (width, gc) point
echo ""
echo "Running exploration..."
WITNESS_FLAG=""
if [ "$SKIP_WITNESSES" = "true" ]; then
    WITNESS_FLAG="--skip-witnesses"
fi

python3 scripts/explore_staggered.py \
    --db "$LOCAL_DB" \
    --min-width "$WIDTH" \
    --max-width "$WIDTH" \
    --single-gc "$GC" \
    --solver "$SOLVER" \
    --workers "$WORKERS" \
    $WITNESS_FLAG

EXPLORE_STATUS=$?

echo ""
echo "Exploration finished with status: $EXPLORE_STATUS"

# Copy results back to shared storage
if [ $EXPLORE_STATUS -eq 0 ]; then
    echo "Copying results back to $FINAL_DB..."
    mkdir -p "$FINAL_DB_DIR"
    
    # Use rsync for safe incremental copy
    if command -v rsync &> /dev/null; then
        rsync -av "$LOCAL_DB/" "$FINAL_DB/"
    else
        cp -r "$LOCAL_DB"/* "$FINAL_DB/" 2>/dev/null || cp -r "$LOCAL_DB" "$FINAL_DB"
    fi
    
    echo "Results saved successfully."
else
    echo "ERROR: Exploration failed, not copying results."
fi

# Cleanup scratch
echo "Cleaning up scratch..."
rm -rf "$SCRATCH_DIR"

echo ""
echo "=============================================="
echo "Job completed: $(date)"
echo "Exit status: $EXPLORE_STATUS"
echo "=============================================="

exit $EXPLORE_STATUS
