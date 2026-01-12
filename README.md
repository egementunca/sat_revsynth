# SAT RevSynth

## Framework for Synthesis of Reversible Logic using SAT-Solvers

![Tests](https://github.com/M4D-A/sat_revsynth/actions/workflows/pytest.yml/badge.svg) ![pep8](https://github.com/M4D-A/sat_revsynth/actions/workflows/flake8.yml/badge.svg)

A Python framework for **exhaustive synthesis** of reversible logic circuits and **identity templates** using SAT-solver technology.

---

**📚 [READ THE FULL DOCUMENTATION](docs/README.md)**

---

## Features

- **SAT-based Circuit Synthesis**: Encode circuit constraints as CNF formulas.
- **Multiple Gate Sets**: MCT (Multiple-Control Toffoli), ECA Rule 57.
- **Identity Template Enumeration**: Find all circuits that implement the identity function.
- **Equivalence Class Support**: Group circuits by swap/rotation/permutation equivalence.
- **Multiple SAT Solvers**: Support for 13+ builtin solvers and external solvers (kissat, CaDiCaL).

## Quick Links

- [Installation Guide](docs/user/installation.md)
- [Quick Start Tutorial](docs/user/quickstart.md)
- [Advanced Usage](docs/user/advanced_usage.md)
- [System Architecture](docs/design/architecture.md)

## Example

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
