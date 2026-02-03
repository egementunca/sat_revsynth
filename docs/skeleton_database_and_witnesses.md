# Skeleton Database and Witness System

## Overview

This document describes two complementary systems for working with identity circuits:

1. **Skeleton Database** (`skeleton_db.py`) - LMDB storage indexed by GatePair taxonomy for RAC mixing
2. **Witness System** (`witnesses.py`) - Half-circuits with k-gram prefilter for fast identity detection

Both systems are used in circuit obfuscation and simplification workflows.

---

## Part 1: Skeleton Database

### What is the Skeleton Database?

The skeleton database stores **identity circuits** (skeleton chains) indexed by **GatePair taxonomy**. This enables the RAC mixing scheme to quickly look up identity circuits that match specific gate pair patterns.

### Database Structure

```
LMDB Environment: skeleton_identity_db/
├── ids_n3    # 3-wire circuits
├── ids_n4    # 4-wire circuits
├── ids_n5    # 5-wire circuits
...
├── ids_n12   # 12-wire circuits
└── (up to ids_n16)
```

### Key Format: GatePair Taxonomy

Each key is a 12-byte **GatePair** that describes how two adjacent gates relate:

```python
class CollisionType(IntEnum):
    OnActive = 0   # Wire hits gate1's target
    OnCtrl1 = 1    # Wire hits gate1's ctrl1
    OnCtrl2 = 2    # Wire hits gate1's ctrl2
    OnNew = 3      # Wire doesn't touch gate1

@dataclass
class GatePair:
    a: CollisionType    # Where gate2's target lands on gate1
    c1: CollisionType   # Where gate2's ctrl1 lands on gate1
    c2: CollisionType   # Where gate2's ctrl2 lands on gate1
```

**Serialization**: 12 bytes (3 × u32 little-endian)

```python
def to_bytes(self) -> bytes:
    return struct.pack("<III", int(self.a), int(self.c1), int(self.c2))
```

### Value Format: Circuit List

Each value is a **Vec<Vec<u8>>** (bincode format) containing multiple circuit blobs:

```python
def serialize_circuit_list(circuits: list[bytes]) -> bytes:
    result = bytearray()
    result.extend(struct.pack("<Q", len(circuits)))  # Count as u64
    for blob in circuits:
        result.extend(struct.pack("<Q", len(blob)))  # Blob length as u64
        result.extend(blob)                           # Blob data
    return bytes(result)
```

**Circuit Blob Format**: Each gate is 3 bytes `[target, ctrl1, ctrl2]`

### Usage in RAC Mixing

The RAC (Replace And Compress) mixing scheme uses the skeleton database for pair replacement:

```rust
// In local_mixing/src/algorithms/butterfly/replace.rs
fn get_random_identity(n: usize, gate_pair: GatePair, env: &lmdb::Environment) {
    let db_name = format!("ids_n{}", n);
    let key = bincode::serialize(&gate_pair)?;
    let circuits: Vec<Vec<u8>> = bincode::deserialize(txn.get(db, &key)?)?;
    let blob = circuits.choose(&mut rng)?;
    CircuitSeq::from_blob(blob)
}
```

### Building the Database

```bash
# Generate skeletons for a specific width
python scripts/generate_skeletons_batch.py 8 --taxonomies 50 --variants 100

# Or use the builder programmatically
from database.skeleton_db import SkeletonDBBuilder

with SkeletonDBBuilder("skeleton_identity_db") as builder:
    stats = builder.build(min_wires=4, max_wires=12, target_taxonomies=50)
```

### Post-Processing

Remove consecutive identical gates (simplify):

```bash
# Dry run
python scripts/postprocess_simplify_circuits.py skeleton_identity_db --dry-run

# Apply changes
python scripts/postprocess_simplify_circuits.py skeleton_identity_db
```

---

## Part 2: Witness System

### What are Witnesses?

Witnesses are **half-circuits** extracted from identity circuits. They enable fast detection of identity patterns even when the exact full circuit isn't found.

**Formula**: `witness_length = floor(gate_count / 2) + 1`

| Identity GC | Witness Length |
|-------------|----------------|
| 6 | 4 |
| 8 | 5 |
| 10 | 6 |
| 12 | 7 |

### How Witnesses Enable Simplification

Given an identity circuit `I = [G1, G2, G3, G4, G5, G6]`:
- Witness = `[G1, G2, G3, G4]` (first half + 1)
- Complement = `[G4, G5, G6]` (second half)

If we find the witness pattern in a circuit, we know:
1. The next `(GC - witness_len)` gates might complete the identity
2. If they match the complement, the entire pattern can be removed

### K-gram Token Prefilter

For fast witness detection, the system uses k-gram token hashing:

```python
def compute_kgram_tokens(gates: list, k: int) -> List[int]:
    """Compute k-gram token hashes for prefilter."""
    tokens = []
    for i in range(len(gates) - k + 1):
        window = gates[i:i + k]
        # Canonicalize window (local wire relabeling)
        _, window_hash = basis.canonicalize(window, width)
        # Take first 8 bytes as 64-bit token
        token = struct.unpack("<Q", window_hash[:8])[0]
        tokens.append(token)
    return tokens
```

### Database Structure

```
LMDB Environment: collection.lmdb/
├── witnesses_by_hash    # Deduplicated witness storage
│   Key: [basis_id(1B)] [width(1B)] [witness_len(2B)] [canonical_hash(32B)]
│   Value: WitnessRecord bytes
│
└── witness_prefilter    # K-gram token → witness_id mapping
    Key: [basis_id(1B)] [width(1B)] [token_hash(8B)]
    Value: List of witness_ids
```

### WitnessRecord Structure

```python
@dataclass
class WitnessRecord:
    witness_id: int           # Unique monotonic ID
    basis_id: int             # Gate basis (ECA57 = 1)
    width: int                # Number of wires
    witness_len: int          # Number of gates in witness
    witness_hash: bytes       # 32-byte canonical BLAKE3 hash
    gates_encoded: bytes      # Packed gate bytes
    source_template_id: int   # Reference to source identity
```

### Building Witnesses

From templates (identity circuits):

```python
from database.witnesses import WitnessStore, compute_witness_length

store = WitnessStore(env, ECA57Basis())

# For each template
for template in templates:
    gates = decode_gates(template.gates_encoded)
    witness_len = compute_witness_length(len(gates))  # GC//2 + 1
    witness_gates = gates[:witness_len]

    store.insert_witness(witness_gates, template.width, template.template_id)
```

### Usage in Simplification

```rust
// In local_mixing/src/infra/sat_witness.rs

// Step 1: Fast prefilter check
if prefilter_hit(db, &subcircuit.gates, width, &[2, 3]) {
    // Step 2: Exact window matching
    remove_identity_window(&mut subcircuit, db, width, max_len=7);
}

fn remove_identity_window(subcircuit: &mut CircuitSeq, ...) -> bool {
    // Try longest windows first (5-7 gates)
    for window_len in (5..=max_len).rev() {
        for start in 0..=(len - window_len) {
            let window = &subcircuit.gates[start..start + window_len];
            if template_contains(db, window, width) {
                subcircuit.gates.drain(start..start + window_len);
                return true;
            }
        }
    }
    false
}
```

---

## Part 3: Complete Pipeline

### 1. Generate Skeleton Chains (SAT Synthesis)

```python
from synthesizers.skeleton_chain_api import synthesize_skeleton_chain

skeleton = synthesize_skeleton_chain(wires=8, gates=16)
```

### 2. Unroll to Generate Variants

```python
from synthesizers.skeleton_chain_api import limited_unroll

variants = limited_unroll(
    skeleton,
    max_circuits=1000,
    max_permutations=100,
    use_skeleton_mode=True
)
```

### 3. Store in Skeleton Database (for RAC)

```python
from database.skeleton_db import SkeletonDBBuilder

with SkeletonDBBuilder("skeleton_identity_db") as builder:
    for circuit in variants:
        builder.add_skeleton(circuit, width=8)
```

### 4. Extract Witnesses (for Simplification)

```python
from database.witnesses import WitnessStore

store = WitnessStore(template_env, ECA57Basis())

for circuit in variants:
    # Store as template first
    template_id = template_store.insert(circuit)

    # Extract and store witness
    witness_gates = circuit.gates()[:len(circuit)//2 + 1]
    store.insert_witness(witness_gates, width, template_id)
```

### 5. Post-Process: Remove Duplicates and Simplify

```bash
# Remove consecutive identical gates
python scripts/postprocess_simplify_circuits.py skeleton_identity_db
```

---

## Deduplication

### In Skeleton Database

Deduplication happens at insert time:

```python
def add_skeleton(self, circuit: ECA57Circuit, width: int):
    blob = circuit_to_blob(circuit)

    with self._env.begin(write=True) as txn:
        existing = txn.get(key, db=db)
        if existing:
            circuits = deserialize_circuit_list(existing)
            if blob in circuits:  # Duplicate check
                return taxonomy
            circuits.append(blob)
        # ...
```

### In Witness Database

Deduplication via canonical hash:

```python
def insert_witness(self, gates, width, source_template_id):
    # Canonicalize
    canonical_gates, witness_hash = self.basis.canonicalize(gates, width)

    # Check for duplicate
    existing = self.env.get_witness(txn, basis_id, width, witness_len, witness_hash)
    if existing is not None:
        return None  # Duplicate
    # ...
```

---

## Integration with local_mixing (Rust)

### Database Names

The Rust code opens these databases in `mixing.rs`:

```rust
let db_names = [
    // ... other databases ...
    "ids_n3", "ids_n4", "ids_n5", "ids_n6", "ids_n7",
    "ids_n8", "ids_n9", "ids_n10", "ids_n11", "ids_n12",
    // Witness databases
    "ids_rev",
    "ids_wit_prefilter",
];
```

### Format Compatibility

Both Python and Rust use the same formats:
- **GatePair**: 12 bytes (3 × u32 LE) via bincode/struct.pack
- **Circuit list**: bincode Vec<Vec<u8>>
- **Witness prefilter**: k-gram tokens as u64

---

## CLI Commands

### Build skeleton database
```bash
python scripts/generate_skeletons_batch.py <width> --taxonomies N --variants M
```

### Build witnesses from templates
```bash
python src/eca57_cli.py build-witnesses --db data/collection.lmdb --max-width 8
```

### Post-process (simplify)
```bash
python scripts/postprocess_simplify_circuits.py <db_path>
```

---

## Summary

| System | Purpose | Key Format | Used By |
|--------|---------|------------|---------|
| Skeleton DB | RAC pair replacement | GatePair (12B) | `replace.rs` |
| Witness DB | Identity detection | k-gram tokens (8B) | `sat_witness.rs` |

Both systems work together:
1. **Skeleton DB** provides diverse identity circuits for obfuscation expansion
2. **Witness DB** enables fast identity detection for compression/simplification
