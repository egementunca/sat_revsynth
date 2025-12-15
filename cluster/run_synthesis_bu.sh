#!/bin/bash
#$ -N sat_revsynth
#$ -pe omp 8
#$ -l h_rt=48:00:00
#$ -l mem_per_core=4G
#$ -j y
#$ -V
#$ -cwd

# SAT RevSynth - Enumerate UNIQUE identity templates (Table II)
# Uses canonicalization to count equivalence class representatives only

cd "${SGE_O_WORKDIR:-$(dirname $0)/..}"

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

WIDTH="${WIDTH:-3}"
GATES="${GATES:-4}"
SOLVER="${SOLVER:-cadical153}"
OUTPUT_DIR="${OUTPUT_DIR:-results}"
GATE_SET="${GATE_SET:-mct}"

mkdir -p "$OUTPUT_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="$OUTPUT_DIR/${GATE_SET}_w${WIDTH}_g${GATES}_${SOLVER}_${TIMESTAMP}.json"

echo "SAT RevSynth - UNIQUE Templates (Table II)"
echo "==========================================="
echo "Width: $WIDTH, Gates: $GATES, Solver: $SOLVER"
echo "Output: $OUTPUT_FILE"
echo "Started: $(date)"

python3 << 'PYTHON_SCRIPT'
import sys
import os
sys.path.insert(0, 'src')

import json
import time
from truth_table.truth_table import TruthTable
from sat.solver import Solver
from database.equivalence import canonical_repr

WIDTH = int(os.environ.get('WIDTH', 3))
GATES = int(os.environ.get('GATES', 4))
SOLVER_NAME = os.environ.get('SOLVER', 'cadical153')
GATE_SET = os.environ.get('GATE_SET', 'mct')
OUTPUT_FILE = os.environ.get('OUTPUT_FILE', 'results/output.json')

# Fix OUTPUT_FILE from shell
import subprocess
result = subprocess.run(['echo', os.environ.get('OUTPUT_FILE', '')], capture_output=True, text=True)

solver = Solver(SOLVER_NAME)
identity_tt = TruthTable(WIDTH)

# Track UNIQUE circuits by canonical representation
unique_circuits = {}  # canonical_repr -> circuit gates
total_found = 0
start_time = time.time()

if GATE_SET == 'mct':
    from synthesizers.circuit_synthesizer import CircuitSynthesizer
    from circuit.circuit import Circuit
    
    synth = CircuitSynthesizer(identity_tt, GATES, solver)
    synth.disable_empty_lines()
    
    while True:
        circuit = synth.solve()
        if circuit is None:
            break
        
        total_found += 1
        
        # Get canonical form to deduplicate
        try:
            canon = canonical_repr(circuit)
            if canon not in unique_circuits:
                unique_circuits[canon] = [list(g) for g in circuit.gates()]
        except Exception as e:
            # If canonicalization fails, use raw representation
            raw = str([(list(c), t) for c, t in circuit.gates()])
            if raw not in unique_circuits:
                unique_circuits[raw] = [list(g) for g in circuit.gates()]
        
        synth.exclude_solution(circuit)
        
        if total_found % 1000 == 0:
            print(f'Processed {total_found}, unique: {len(unique_circuits)}...', flush=True)

elif GATE_SET == 'eca57':
    from synthesizers.eca57_synthesizer import ECA57Synthesizer
    
    synth = ECA57Synthesizer(identity_tt, GATES, solver)
    
    while True:
        circuit = synth.solve()
        if circuit is None:
            break
            
        total_found += 1
        
        # Simple string-based deduplication for ECA57 (no canonicalizer yet)
        # Use tuple representation of gates: (target, ctrl1, ctrl2)
        gates_data = [g.to_tuple() for g in circuit.gates()]
        raw = str(gates_data)
        
        if raw not in unique_circuits:
            unique_circuits[raw] = gates_data
            
        synth.exclude_solution(circuit)
        
        if total_found % 1000 == 0:
            print(f'Processed {total_found} (ECA57), unique: {len(unique_circuits)}...', flush=True)

elapsed = time.time() - start_time

result = {
    'width': WIDTH,
    'gates': GATES,
    'solver': SOLVER_NAME,
    'gate_set': GATE_SET,
    'total_enumerated': total_found,
    'unique_templates': len(unique_circuits),
    'elapsed_seconds': elapsed,
    'circuits': list(unique_circuits.values())
}

output_file = f"results/{GATE_SET}_w{WIDTH}_g{GATES}_{SOLVER_NAME}.json"
with open(output_file, 'w') as f:
    json.dump(result, f, indent=2)

print(f'\nCompleted!')
print(f'Total enumerated: {total_found}')
print(f'Unique templates: {len(unique_circuits)}')
print(f'Time: {elapsed:.2f}s')
print(f'Saved to: {output_file}')
PYTHON_SCRIPT

echo "Job completed: $(date)"
