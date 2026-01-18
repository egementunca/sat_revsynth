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
