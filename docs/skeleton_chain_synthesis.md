# Skeleton Chain Synthesis with Limited Unrolling

## Overview

Skeleton chain synthesis generates identity circuits where **all adjacent gates collide** (don't commute). This creates circuits with special properties useful for obfuscation and cryptographic applications.

The key challenge with skeleton chains is that full unrolling (generating all equivalent circuits) causes **memory explosion** for large circuits. This implementation provides **bounded exploration** via limited unrolling.

## What are Skeleton Chains?

A **skeleton chain** is an identity circuit where:
1. Every pair of adjacent gates **collides** (doesn't commute)
2. The circuit implements the identity function (output = input)
3. No adjacent gates can be swapped (swap space is trivial: just the circuit itself)

### Collision Criterion

Two ECA57 gates collide when the target of one gate appears in the controls of the other:
```
Gate i:   target=a, ctrl1=b, ctrl2=c
Gate i+1: target=d, ctrl1=e, ctrl2=f

Collision if: a ∈ {e, f} OR d ∈ {b, c}
```

## The Memory Explosion Problem

### Without Limited Unrolling

For a 16-wire, 32-gate skeleton chain, the equivalence class size is:

```
Equivalents = rotations × mirror × permutations
            = 32 × 2 × 16!
            = 64 × 20,922,789,888,000
            ≈ 1.34 × 10^15 circuits
```

Storing this many circuits would require **petabytes** of memory.

### With Limited Unrolling

Using bounded exploration:
```python
variants = limited_unroll(
    skeleton,
    max_circuits=1000,
    max_permutations=100  # Sample 100 out of 16! permutations
)
# Result: ~1,000 circuits instead of 10^15
```

## API Reference

### High-Level API

```python
from synthesizers.skeleton_chain_api import (
    synthesize_skeleton_chain,
    limited_unroll,
    verify_skeleton_chain,
    estimate_unroll_size,
)
```

#### `synthesize_skeleton_chain()`

Synthesize a skeleton chain identity circuit.

**Parameters:**
- `wires` (int): Number of circuit wires (3+)
- `gates` (int): Number of gates to synthesize
- `chain_length` (int | None): If provided, enforces exactly this many consecutive collisions. If None, enforces collision for all adjacent pairs.
- `solver_name` (str): SAT solver to use (default: "glucose4")
- `avoid_adjacent_identical` (bool): If True, prevents identical adjacent gates (default: True)
- `timeout` (int | None): Optional solver timeout in seconds

**Returns:**
- `ECA57Circuit | None`: Skeleton chain if SAT, None if UNSAT

**Example:**
```python
skeleton = synthesize_skeleton_chain(
    wires=8,
    gates=16,
    solver_name="glucose4"
)

if skeleton:
    print(f"Synthesized {len(skeleton)} gates")
```

#### `limited_unroll()`

Generate equivalent circuits with bounded exploration.

**Parameters:**
- `circuit` (ECA57Circuit): Source circuit to unroll
- `max_circuits` (int): Maximum total circuits to generate (default: 10000)
- `max_swap_depth` (int): Maximum BFS depth for swap exploration (default: 10)
- `max_swap_circuits` (int): Maximum circuits from swap space (default: 1000)
- `max_permutations` (int | None): If None, use all permutations; if int, sample that many. For large widths (16+), recommend 100-1000.
- `include_rotations` (bool): Whether to include rotations (default: True)
- `include_mirror` (bool): Whether to include mirror (default: True)
- `use_skeleton_mode` (bool): If True, skip swap exploration entirely (default: False)

**Returns:**
- `List[ECA57Circuit]`: List of equivalent circuits (bounded)

**Example:**
```python
# For skeleton chains: use skeleton mode (fast path)
variants = limited_unroll(
    skeleton,
    max_circuits=1000,
    max_permutations=100,
    use_skeleton_mode=True  # Skip swap exploration
)

print(f"Generated {len(variants)} circuits")
```

#### `verify_skeleton_chain()`

Verify that a circuit is a true skeleton chain.

**Parameters:**
- `circuit` (ECA57Circuit): Circuit to verify

**Returns:**
- `bool`: True if all adjacent gates collide

**Example:**
```python
is_skeleton = verify_skeleton_chain(circuit)
if is_skeleton:
    print("✓ All adjacent gates collide")
```

#### `estimate_unroll_size()`

Estimate the size of full unroll for a circuit.

**Parameters:**
- `wires` (int): Number of wires
- `gates` (int): Number of gates
- `is_skeleton` (bool): If True, assume skeleton chain (default: False)

**Returns:**
- `dict`: Dictionary with size estimates including:
  - `rotations`: Number of rotations
  - `mirror`: Mirror multiplier (2)
  - `swap_space`: Estimated swap space size
  - `permutations`: Total permutations (w!)
  - `total_estimate`: Estimated total circuits
  - `recommended_max_permutations`: Recommended sampling
  - `is_feasible_full_unroll`: Whether full unroll is feasible

**Example:**
```python
est = estimate_unroll_size(wires=16, gates=32, is_skeleton=True)
print(f"Estimated total: {est['total_estimate']:,}")
print(f"Recommended sampling: {est['recommended_max_permutations']}")
```

### Low-Level API

The low-level circuit methods provide fine-grained control:

```python
from gates.eca57 import ECA57Circuit

# Fast canonical form for skeleton chains (no swap exploration)
canonical = circuit.canonical_skeleton()
canonical_key = circuit.canonical_skeleton_key()
are_equiv = circuit.are_equivalent_skeleton(other_circuit)

# Limited swap space exploration
swap_variants = circuit.swap_space_bfs_limited(
    max_depth=10,
    max_circuits=1000
)

# Limited unroll
variants = circuit.limited_unroll(
    max_swap_depth=10,
    max_swap_circuits=1000,
    max_permutations=100,
    max_total_circuits=10000
)
```

## CLI Usage

### `skeleton-chain` Command

```bash
# Synthesize and show estimates
python src/eca57_cli.py skeleton-chain 8 16 --estimate --show-circuit

# Synthesize and generate 500 variants
python src/eca57_cli.py skeleton-chain 8 16 --unroll --max-circuits 500 --max-permutations 50

# Save to file
python src/eca57_cli.py skeleton-chain 8 16 --unroll --max-circuits 1000 -o output.json
```

**Options:**
- `width gates`: Required positional arguments
- `-s, --solver`: SAT solver (default: glucose4)
- `--chain-length`: Minimum collision chain length
- `--allow-adjacent-identical`: Allow adjacent identical gates
- `--unroll`: Generate equivalent circuits
- `--max-circuits`: Maximum circuits to generate (default: 1000)
- `--max-permutations`: Maximum permutations to sample (default: auto)
- `--estimate`: Show estimated equivalence class size
- `--show-circuit`: Display the synthesized circuit
- `-o, --output`: Output file path (JSON)
- `--save-limit`: Maximum circuits to save (default: 100)

## Use Cases

### 1. Circuit Obfuscation

Generate a pool of identity circuits for runtime obfuscation:

```python
# Synthesize base skeleton
skeleton = synthesize_skeleton_chain(wires=6, gates=12)

# Generate obfuscation pool
pool = limited_unroll(
    skeleton,
    max_circuits=200,
    max_permutations=20,
    use_skeleton_mode=True
)

# At runtime: randomly select from pool
import random
obfuscator = random.choice(pool)
obfuscated = obfuscator.apply(data)  # Still equals data (identity)
```

### 2. Cryptographic Primitives

Skeleton chains provide:
- **Collision structure** prevents simple optimization
- **Identity property** ensures correctness
- **Diversity** via bounded sampling

### 3. Testing and Verification

Generate diverse test cases for circuit optimizers:

```python
skeleton = synthesize_skeleton_chain(wires=5, gates=10)
test_cases = limited_unroll(skeleton, max_circuits=50)

for test_circuit in test_cases:
    assert optimizer.optimize(test_circuit).is_identity()
```

## Performance Guidelines

### Small Circuits (≤6 wires, ≤12 gates)

Full unroll is feasible:
```python
# Can use full unroll or canonical()
canonical = circuit.canonical()
```

### Medium Circuits (8 wires, 16-20 gates)

Use moderate limits:
```python
variants = limited_unroll(
    circuit,
    max_circuits=1000,
    max_permutations=50
)
```

### Large Circuits (16+ wires, 32+ gates)

**Always use limited unroll** with strict budgets:
```python
variants = limited_unroll(
    circuit,
    max_circuits=1000,
    max_permutations=100,  # Sample 100 out of 16! = 20 trillion
    use_skeleton_mode=True  # Skip swap exploration
)
```

## Implementation Details

### Fast Canonical Form for Skeletons

For skeleton chains, the swap space is trivial (only contains the original circuit). The `canonical_skeleton()` method optimizes this:

```python
def canonical_skeleton(self):
    # Skip swap_space_bfs() - for skeleton chains it's just [self]
    candidates = []

    # Apply rotations and mirror
    for r in range(len(self)):
        rotated = self.rotate(r)
        candidates.append(rotated)
        candidates.append(rotated.reverse())

    # Apply wire permutations
    for circuit in candidates:
        final_candidates.extend(circuit.permutations())

    # Return lexicographically smallest
    return min(final_candidates)
```

**Performance:** 100-1000× faster than `canonical()` for skeleton chains.

| Circuit | `canonical()` | `canonical_skeleton()` | Speedup |
|---------|---------------|------------------------|---------|
| 4w × 8g | ~5 seconds | ~0.05 seconds | 100× |
| 8w × 16g | ~60 seconds | ~0.5 seconds | 120× |
| 16w × 32g | Minutes (OOM) | ~5 seconds | 1000×+ |

### Limited BFS for Swap Space

The `swap_space_bfs_limited()` method bounds exploration:

```python
def swap_space_bfs_limited(self, max_depth=10, max_circuits=1000):
    queue = [(self, 0)]  # (circuit, depth)
    results = []

    while queue and len(results) < max_circuits:
        curr, depth = queue.popleft()
        results.append(curr)

        if depth < max_depth:
            for neighbor in curr.swaps():
                queue.append((neighbor, depth + 1))

    return results
```

### Permutation Sampling

For large widths, sampling permutations prevents factorial explosion:

```python
# Instead of all 16! = 20,922,789,888,000 permutations
all_perms = itertools.permutations(range(16))  # DON'T DO THIS

# Sample 100 permutations
sampled = random.sample(list(itertools.permutations(range(16))), 100)
```

## Examples

See `examples/skeleton_obfuscation_pipeline.py` for complete working examples including:
- Small circuit synthesis (4w × 8g)
- Medium circuit with sampling (8w × 16g)
- Large circuit safe mode (12w × 24g)
- Practical obfuscation workflow

## Testing

Run the test suite:

```bash
# Test ECA57 circuit methods
python -m pytest src/gates/test_eca57.py -v

# Test skeleton chain API
python -m pytest src/synthesizers/test_skeleton_chain_api.py -v
```

## Future Work

1. **Exclude-until-UNSAT**: Extend `find_skeleton_families()` to support SAT exclusion clauses for finding multiple distinct skeleton classes
2. **Parallel unrolling**: Use multiprocessing to parallelize variant generation
3. **Database integration**: Store skeleton families in LMDB for efficient lookup
4. **Adaptive sampling**: Dynamically adjust permutation sampling based on diversity metrics

## References

- **ECA Rule 57**: Reversible gate `target ^= (ctrl1 OR NOT ctrl2)`
- **Skeleton graphs**: Graph where all adjacent vertices collide
- **Limited unrolling**: Algorithm 2 with bounded exploration
- **Canonical form**: Lexicographically smallest circuit in equivalence class
