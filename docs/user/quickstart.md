# Quick Start

This guide will walk you through synthesizing reversible circuits using the **ECA Rule 57** gate set, which is the primary focus of this framework.

## 1. Using the CLI (Recommended)

The easiest way to use `sat_revsynth` is through the `eca57_cli.py` command-line tool.

### Synthesize a Single Identity

To find an identity circuit (a sequence of gates that simplifies to identity) for a specific width and gate count:

```bash
# Synthesize an identity circuit with 3 wires and 4 gates
python src/eca57_cli.py synth 3 4
```

Example Output:
```text
Synthesizing ECA57 identity circuits: width=3, gc=4
Solver: glucose4
============================================================
  Iteration 1: found 1 circuits (0.02s)
============================================================
Found 1 identity circuits in 0.02s
All circuits verified as identities ✓

Sample circuits:

--- Circuit 1 ---
ECA57 Circuit (width=3, gates=4)
  [0] target=2, ctrl1=0, ctrl2=1
  [1] target=1, ctrl1=0, ctrl2=2
  [2] target=1, ctrl1=0, ctrl2=2
  [3] target=2, ctrl1=0, ctrl2=1
```

### Benchmark Solvers

Not sure which SAT solver is fastest on your machine? Run the benchmark tool:

```bash
python src/eca57_cli.py benchmark --width 4 --gc 5
```

## 2. Python API

You can also use the Python API for more control.

### Synthesizing ECA57 Circuits

```python
from truth_table.truth_table import TruthTable
from synthesizers.eca57_synthesizer import ECA57Synthesizer
from sat.solver import Solver

# 1. Define the target function
# For identity synthesis, we start with an identity truth table.
width = 3
gate_count = 4
tt = TruthTable(width)

# 2. Initialize Solver and Synthesizer
solver = Solver("glucose4")
synth = ECA57Synthesizer(tt, gate_count, solver)

# 3. Solve
circuit = synth.solve()

if circuit:
    print("Found circuit:")
    print(circuit)
else:
    print("No solution found.")
```

### Creating Gates Manually

If you want to build circuits manually or define custom truth tables:

```python
from gates.eca57 import ECA57Circuit

# Create a circuit with 3 wires
circ = ECA57Circuit(3)

# Add gates: target, ctrl1 (active high), ctrl2 (active low)
# Rule 57 logic: target ^= (ctrl1 OR NOT ctrl2)
circ.add_gate(target=2, ctrl1=0, ctrl2=1)
circ.add_gate(target=1, ctrl1=2, ctrl2=0)

print(circ)

# Check if it implements Identity
print(f"Is Identity? {circ.is_identity()}")
```
