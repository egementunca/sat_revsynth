# SAT RevSynth

## Framework for Synthesis of Reversible Logic using SAT-Solvers

![Tests](https://github.com/M4D-A/sat_revsynth/actions/workflows/pytest.yml/badge.svg) ![pep8](https://github.com/M4D-A/sat_revsynth/actions/workflows/flake8.yml/badge.svg)

A Python framework for **exhaustive synthesis** of reversible logic circuits and **identity templates** using SAT-solver technology. Based on the procedural generation technique from our research paper.

## Features

- **SAT-based Circuit Synthesis**: Encode circuit constraints as CNF formulas
- **Multiple Gate Sets**: MCT (Multiple-Control Toffoli), ECA Rule 57
- **Identity Template Enumeration**: Find all circuits that implement the identity function
- **Equivalence Class Support**: Group circuits by swap/rotation/permutation equivalence
- **Multiple SAT Solvers**: Support for 13+ builtin solvers and external solvers (kissat, CaDiCaL)
- **Canonicalization & Database**: Store and query enumerated circuits

## Installation

```bash
# Clone the repository
git clone https://github.com/M4D-A/sat_revsynth.git
cd sat_revsynth

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Optional: Install External SAT Solvers

For best performance, install modern SAT solvers:

```bash
# kissat (SAT Competition 2024 winner)
git clone https://github.com/arminbiere/kissat.git
cd kissat && ./configure && make
sudo cp build/kissat /usr/local/bin/

# CaDiCaL 2.0
git clone https://github.com/arminbiere/cadical.git
cd cadical && ./configure && make
sudo cp build/cadical /usr/local/bin/
```

## Quick Start

### Synthesize a Circuit

```python
from truth_table.truth_table import TruthTable
from synthesizers.circuit_synthesizer import CircuitSynthesizer
from sat.solver import Solver

# Create target truth table (e.g., CNOT gate on 2 wires)
tt = TruthTable(2).cx(0, 1)

# Synthesize with 1 gate
solver = Solver("glucose4")
synth = CircuitSynthesizer(tt, gate_count=1, solver=solver)
circuit = synth.solve()

print(circuit)
```

### Enumerate Identity Templates

```python
from truth_table.truth_table import TruthTable
from synthesizers.circuit_synthesizer import CircuitSynthesizer
from sat.solver import Solver

# Find identity circuits of width=3, gate_count=4
identity_tt = TruthTable(3)
solver = Solver("cadical153")

synth = CircuitSynthesizer(identity_tt, gate_count=4, solver=solver)
synth.disable_empty_lines()  # Only circuits using all wires

circuits = []
while True:
    circuit = synth.solve()
    if circuit is None:
        break
    circuits.append(circuit)
    synth.exclude_solution(circuit)

print(f"Found {len(circuits)} identity templates")
```

## Project Structure

```
sat_revsynth/
├── src/
│   ├── circuit/          # Circuit representation
│   │   ├── circuit.py    # Circuit class with MCT gates
│   │   ├── collection.py # Circuit collections
│   │   └── dim_group.py  # Dimension groups
│   ├── sat/              # SAT encoding and solving
│   │   ├── cnf.py        # CNF formula builder
│   │   └── solver.py     # Solver interface
│   ├── synthesizers/     # Synthesis algorithms
│   │   └── circuit_synthesizer.py
│   ├── truth_table/      # Truth table utilities
│   ├── database/         # Canonicalization & storage
│   └── gates/            # Gate set definitions
├── cpp/                  # C++ performance implementation
├── cluster/              # PBS/qsub job scripts
└── requirements.txt
```

## Gate Sets

### MCT (Multiple-Control Toffoli)
The standard reversible gate: `target ^= AND(controls)`

### ECA Rule 57
Elementary Cellular Automaton gate: `target ^= (ctrl1 OR NOT ctrl2)`

## Running Tests

```bash
cd src
pytest -v
```

## Supported SAT Solvers

**Builtin** (via python-sat):
- cadical103, cadical153
- glucose3, glucose4, glucose42
- lingeling, maplechrono, maplecm, maplesat
- mergesat3, minisat22, minisat-gh
- minicard, gluecard3, gluecard4

**External** (command-line):
- kissat, kissat-sc2024
- cadical (2.0)
- sbva-cadical

## Citation

If you use this code in your research, please cite:

```bibtex
@article{satrevsynth2024,
  title={Procedural Generation of Identity Templates for Reversible Logic},
  author={...},
  journal={...},
  year={2024}
}
```

## License

See [LICENSE](LICENSE) for details.
