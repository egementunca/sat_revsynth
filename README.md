# SAT RevSynth

## Framework for Synthesis of Reversible Logic using SAT-Solvers

![Tests](https://github.com/M4D-A/sat_revsynth/actions/workflows/pytest.yml/badge.svg) ![pep8](https://github.com/M4D-A/sat_revsynth/actions/workflows/flake8.yml/badge.svg)

A Python framework for **exhaustive synthesis** of reversible logic circuits and **identity templates** using SAT-solver technology. The current development focus is the ECA57 (Rule 57) gate set, with legacy support for MCT (multiple-control Toffoli).

---

**📚 [READ THE FULL DOCUMENTATION](docs/README.md)**

---

## Status Snapshot (Current)

- The ECA57 pipeline is the most complete: SAT synthesis, equivalence unrolling, LMDB-backed template storage, witness prefiltering, and cluster workflows.
- MCT synthesis and SQLite-based storage are still present, but do not yet share feature parity with the ECA57 LMDB pipeline.
- Cluster tooling targets BU SCC and is wired for ECA57 exploration runs.
- ECA57 skeleton constraints and visualization tooling are experimental but usable.

## Codebase Map

- `src/gates/`: Gate definitions (`eca57.py`, `gate_set.py`).
- `src/synthesizers/`: SAT encodings and enumerators (MCT + ECA57).
- `src/database/`: LMDB template/witness database for ECA57.
- `src/circuit/`: Circuit containers (MCT + ECA57).
- `scripts/`: Batch workflows, exploration, and utilities.
- `cluster/`: BU SCC job submission and merge tools.
- `docs/`: User/developer documentation.
- `notebooks/`: Visualization and analysis notebooks.
- `cpp/` and `old/`: legacy or experimental code.

## ECA57 Additions (Walkthrough)

### 1) Gate Set and Circuit Model
- `src/gates/eca57.py`: `ECA57Gate` and `ECA57Circuit` with apply, unroll, canonical, and identity checks.
- `src/gates/gate_set.py`: `ECA57GateSet` enumeration helpers.
- `src/circuit/eca57_dim_group.py` and `src/circuit/eca57_collection.py`: grouping for (width, gate_count).

### 2) SAT Synthesis
- `src/synthesizers/eca57_synthesizer.py`: CNF encoding for target/ctrl1/ctrl2 with optional empty-line constraints.
- `src/sat/solver_racer.py`: multi-solver racing to reduce tail latency.
- Supports excluding exact solutions and subcircuits to aid enumeration.

### 3) Exhaustive Enumeration
- `src/synthesizers/eca57_dimgroup_synthesizer.py`: unroll-exclude loop to enumerate identity templates.
- Produces `ECA57DimGroup` and `ECA57Collection` containers.

### 4) Skeleton Constraints (Experimental)
- `src/synthesizers/eca57_skeleton_synthesizer.py`: enforces adjacent-gate collisions (non-commuting chain).
- `skeleton_plan.md`: design notes for future extensions.
- `src/synthesizers/eca57_skeleton_synthesizer_test.py`: property checks.

### 5) LMDB Template Database
- `src/database/lmdb_env.py`: LMDB environment with named DBs for templates and witnesses.
- `src/database/basis.py`: ECA57 canonicalization (wire relabeling + BLAKE3 hash).
- `src/database/templates.py`: `TemplateStore` / `TemplateRecord` storage.
- `src/database/unroll.py`: mirror, rotate, permute, and swap-DFS expansion with op flags.

### 6) Witnesses and Distillation
- `src/database/witnesses.py`: witness extraction and k-gram prefilter.
- `src/excirc_distiller/eca57_excirc_distiller.py`: excircuit distillation pipeline.
- `scripts/test_lmdb_integration.py`: end-to-end LMDB sanity check.

### 7) CLI and Batch Workflows
- `src/eca57_cli.py`: benchmark, synth, collection, distill, build-db, unroll, build-witnesses.
- `scripts/explore_staggered.py`: staged exploration (SAT -> unroll -> witnesses) with optional parallel unrolling.
- `scripts/synthesize_from_tt.py`: JSON IO for "shorter circuit" search.

### 8) Visualization and Analysis
- `src/utils/eca57_viz.py`: ASCII circuit drawing, skeleton graphs, and Matplotlib visuals.
- `src/benchmark_circuits.py`: solver benchmarking with DOT/SVG skeleton output.
- `scripts/visualize_circuits.py` and `notebooks/eca57_visualization_demo.ipynb`: ad-hoc visualization.

### 9) Cluster Support
- `cluster/CLUSTER.md`, `cluster/submit_exploration.py`, `cluster/explore_single.sh`: BU SCC batch exploration.
- `cluster/merge_jobs.py`: merge per-job LMDBs into `data/collection.lmdb`.

## Features

- **SAT-based Circuit Synthesis**: Encode circuit constraints as CNF formulas.
- **Multiple Gate Sets**: MCT (Multiple-Control Toffoli), ECA Rule 57.
- **Identity Template Enumeration**: Find all circuits that implement the identity function.
- **Equivalence Class Support**: Group circuits by swap/rotation/permutation equivalence.
- **Multiple SAT Solvers**: Support for 13+ builtin solvers and external solvers (kissat, CaDiCaL).
- **LMDB Template DB**: Canonicalized template storage with witness prefiltering (ECA57).

## Quick Links

- [Installation Guide](docs/user/installation.md)
- [Quick Start Tutorial](docs/user/quickstart.md)
- [Advanced Usage](docs/user/advanced_usage.md)
- [System Architecture](docs/design/architecture.md)

## Example (ECA57)

```python
from truth_table.truth_table import TruthTable
from synthesizers.eca57_synthesizer import ECA57Synthesizer
from sat.solver import Solver

# Create target truth table (identity on 3 wires)
tt = TruthTable(3)

# Synthesize with 4 gates
solver = Solver("glucose4")
synth = ECA57Synthesizer(tt, gate_count=4, solver=solver)
circuit = synth.solve()

print(circuit)
```

## Testing and Validation

- `pytest` runs unit tests across gates and synthesizers.
- `python scripts/test_lmdb_integration.py` runs an LMDB end-to-end check.

## Known Gaps / Tech Debt

- SQLite `CircuitDatabase` and `cluster/collect_results.py` are MCT-only; ECA57 uses the LMDB pipeline.
- `src/utils/eca57_viz.py` contains a hard-coded `sys.path` for local development.
- Some visualization scripts use exact tuple matching instead of canonicalization for ECA57.
- `src/eca57_cli.py build-db` uses `circuit.gates` instead of `circuit.gates()`.
- `cluster/merge_jobs.py` references `TemplateStore.iter_all` / `TemplateRecord.gates` which are not implemented.
- `cpp/` and `old/` are legacy and not kept in sync with Python.

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
