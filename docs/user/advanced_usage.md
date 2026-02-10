# Advanced Usage

## Identity Template Enumeration

One of the primary goals of `sat_revsynth` is to exhaustively enumerate **Identity Templates**. These are sequences of gates that reduce to the identity function. They are crucial for optimizing quantum and reversible circuits via peephole optimization.

### Automated Enumeration with Equivalence Classes

Instead of manually solving and excluding one circuit at a time, use `ECA57DimGroupSynthesizer`. This class automatically:
1.  Finds a solution.
2.  Generates all equivalent circuits (swaps, rotations, permutations).
3.  Excludes the entire equivalence class to find fundamentally new solutions.

```python
from synthesizers.eca57_dimgroup_synthesizer import ECA57DimGroupSynthesizer

width = 3
gate_count = 4
solver_name = "glucose4"

# Initialize synthesizer
synth = ECA57DimGroupSynthesizer(width, gate_count, solver_name)

print(f"Enumerating identity templates for {width}x{gate_count}...")

# Synthesize all unique equivalence classes
# Returns a DimGroup containing one canonical representative per class
dim_group = synth.synthesize()

print(f"Found {len(dim_group)} fundamental identity templates.")

for i, circuit in enumerate(dim_group):
    print(f"\nTemplate #{i+1}:")
    print(circuit)
    print(f"  (This represents a class of equivalent circuits)")
```

### Equivalence Expansion (Unroll Operations)

The ECA57 pipeline expands each identity with the same core operations:
- **Reverse/Mirror**: reverse gate order (ECA57 gates are self-inverse).
- **Line permutations**: relabel wires to generate equivalent circuits.
- **Rotations**: cyclically rotate the gate sequence.
- **Swap DFS**: explore commuting gate swaps (budgeted search, can be disabled).

There are two implementations:
- `ECA57Circuit.unroll()` in `src/gates/eca57.py` (used by `ECA57DimGroupSynthesizer`).
- `database/unroll.py` with `UnrollConfig` (used in the LMDB pipeline and cluster exploration).

### Collection Synthesis

If you want a full grid of widths and gate counts, use `ECA57CollectionSynthesizer`:
```python
from synthesizers.eca57_dimgroup_synthesizer import ECA57CollectionSynthesizer

collection = ECA57CollectionSynthesizer(max_width=4, max_gate_count=6).synthesize()
print(collection.summary())
```

## Using the Database (CLI)

We provide a CLI for managing the LMDB database of templates.

### `eca57_cli.py`

Located in `src/eca57_cli.py`, this tool manages the generation and storage of Rule 57 templates.

**Build Database:**
```bash
python src/eca57_cli.py build-db --max-width 4 --max-gc 5 -o data/templates.lmdb
```

**Unroll Templates:**
Generates variants (reverse, permutations, rotations, swap DFS) to populate the family trees.
```bash
python src/eca57_cli.py unroll --db data/templates.lmdb --seed-dims 4x5
```

## Wire Shuffle + Bit-Flip (B_{w,s})

`sat_revsynth` includes a shuffle + bit-flip generator that implements:

```
beta_{w,s}(x_1..x_n) = (x_{w(1)} xor s_1, ..., x_{w(n)} xor s_n)
```

Key files:
- Generator: `sat_revsynth/src/synthesizers/shuffle_bitflip.py`
- Swap-with-flip gadgets: `sat_revsynth/scripts/enumerate_swap_flip_gadgets.py`
- Tests: `sat_revsynth/src/synthesizers/test_shuffle_bitflip.py`

### 1. Generate a swap-with-flip gadget library (Style B)

```bash
python sat_revsynth/scripts/enumerate_swap_flip_gadgets.py \
  --min-gates 6 --max-gates 12 \
  --max-solutions 15 --verify -v \
  -o share/swap_flip_gadgets.json
```

### 2. Use the generator (Style A or Style B)

```python
from synthesizers.shuffle_bitflip import FlipMode, ShuffleBitflipConfig, ShuffleBitflipGenerator
from synthesizers.waksman import ECA57SwapFlipLibrary

# Load gadget library for Style B
swap_flip_lib = ECA57SwapFlipLibrary.from_json("share/swap_flip_gadgets.json")

config = ShuffleBitflipConfig(
    flip_mode=FlipMode.EMBEDDED,
    swap_flip_library=swap_flip_lib,
    rng_seed=42,
)

gen = ShuffleBitflipGenerator(width=8, config=config)
circuit, perm, flip_mask = gen.generate_random(flip_probability=0.5)

print(perm, flip_mask)
print(circuit.gates)
```

Notes:
- `FlipMode.SEPARATE` implements Style A (shuffle then explicit flips).
- `FlipMode.EMBEDDED` implements Style B (swap-with-flip gadgets).
- `FlipMode.NONE` generates shuffle-only circuits.

## Cluster Execution

For large-scale enumeration (e.g., width=4, gates=8), we use a cluster environment.

The `cluster/` directory contains scripts for PBS/qsub job submission.

### `explore_staggered.py`

This script (in `scripts/`) is designed to run on a cluster node. It uses `multiprocessing` to saturate the CPU cores of a node.

- **Solver Racing**: Use `SolverRacer` to run multiple SAT solvers in parallel on the same problem; the first one to finish wins. This mitigates the "heavy tail" behavior of SAT solvers.
- **Outputs**: Each job writes an LMDB environment under `data/jobs/w{W}_gc{GC}.lmdb`. These per-job databases can be merged into `data/collection.lmdb` with `cluster/merge_jobs.py`.
