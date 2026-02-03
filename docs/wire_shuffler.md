# Wire Shuffler (ECA57) - SAT Synthesis Notes

This document describes the small project for synthesizing **wire shuffler**
circuits using **only ECA57 (Rule 57) gates**. It targets *small widths* and is
intended for exhaustive or near-exhaustive enumeration.

The script lives at:

```
sat_revsynth/scripts/synth_wire_shuffle.py
```

---

## 1. Problem Definition

We want a circuit that **permutes wires** (bit positions). Given a permutation
`w` on `0..n-1`, the desired mapping is:

```
y[i] = x[w[i]]
```

This is exactly the definition from the email:

```
P(x1..xn) = (x_{w(1)} .. x_{w(n)})
```

Important: this is a **wire permutation**, not a permutation of gates. The
circuit is a reversible function (a permutation on 2^n basis states) that is
induced by that wire shuffle.

---

## 2. Why SAT

There is no direct "wire shuffler" construction in the repo that emits ECA57
gates for arbitrary `w`. What exists is **wire relabeling** helpers, which do
not create a gate sequence. Therefore:

- For small `n`, we synthesize a circuit from the **truth table** using SAT.
- For large `n`, this quickly becomes infeasible.

---

## 3. Script Overview

The script:

1. Builds the truth table for `y[i] = x[w[i]]`
2. Runs SAT synthesis using `ECA57Synthesizer`
3. Prints the gate list and an ASCII drawing
4. Optionally verifies the mapping
5. Optionally writes results to JSON (and dimgroup buckets)

Run:

```
python sat_revsynth/scripts/synth_wire_shuffle.py --width 3 --perm 2,0,1 --max-gates 6 --verify
```

---

## 4. Truth Table Construction

For width `n` and permutation `w`:

```
for x in 0..(2^n-1):
  y = 0
  for out_idx in 0..n-1:
    src_idx = w[out_idx]
    bit = (x >> src_idx) & 1
    y |= bit << out_idx
  values[x] = y
```

This yields a list of integer outputs (one per input row), which feeds
`TruthTable(width, values=values)`.

---

## 5. Output and Visualization

For each permutation:

- **Gate list**: `[(target, ctrl1, ctrl2), ...]`
- **ASCII circuit**:
  - `X` target
  - `1` active-high control (ctrl1)
  - `0` active-low control (ctrl2)

Example output snippet:

```
perm [2,0,1] ...
  gates: 5
  gate_list: [(0, 1, 2), ...]
q0: -|X|-
q1: -1|-|
q2: -0|-|
```

---

## 6. Enumeration and Ordering

The script supports different enumeration orders for all `n!` permutations.
This helps explore “hard” shuffles early:

```
--order lex           (default)
--order hamming-desc  (most moved wires first)
--order hamming-asc
--order swap-desc     (largest minimal swap distance first)
--order swap-asc
--order random --seed 7
```

The script also computes and stores:

- `hamming`: number of wires moved (w[i] != i)
- `swap_distance`: minimal swaps from identity (n - cycles)

Use `--summary` to print aggregate counts by distance.

---

## 7. Swap-Space Exclusion (Same Permutation, More Circuits)

When collecting **multiple circuits for the same permutation**, you should
exclude commuting‑swap variants to avoid duplicates.

Flags:

```
--max-solutions K
--exclude-swap-space
--swap-depth N          # optional; if omitted, full swap-space
--swap-max-circuits M   # optional cap
```

By default, swap-space exclusion is **enabled**.
With no depth provided, it enumerates the **full swap space** (good for small
gate counts).

---

## 8. Cycle-Type Only Enumeration

To reduce SAT calls from `n!` to `p(n)` (integer partitions), use:

```
--cycle-types-only
```

This synthesizes **one canonical permutation per cycle type**. You can later
generate any permutation of that cycle type by wire‑relabeling.

**UI / DB note:** the cycle‑type tables in the UI are simple **aggregations of
what is in the DB**. They show how many permutations of each cycle type exist
and how many circuits were **found within the current gate bounds**. If you
only run `--cycle-types-only`, the DB will contain *one* representative per
cycle type unless you explicitly expand via relabeling or run the full `n!`
enumeration.

**Mathematical rationale (short):**
- Two permutations `w, w' ∈ S_n` are **conjugate** if `w' = σ⁻¹ w σ` for some
  relabeling `σ` of the wires.
- In `S_n`, conjugacy classes are **exactly determined by cycle type** (the
  multiset of cycle lengths), which corresponds to an **integer partition** of
  `n`. Hence the count `p(n)`.
- If `C` implements `w`, then relabeling every wire in the gate list by `σ`
  yields a circuit that implements `σ⁻¹ w σ`. So **one circuit per cycle type**
  can be reused to generate all permutations of that type by wire relabeling.

**Canonical representative example:** for cycle type `[3,2,1,1,1]` on `n=8`,
use cycles `(0 1 2)(3 4)(5)(6)(7)` as the canonical `w₀`. Any other permutation
with the same cycle type is obtained by mapping each canonical cycle onto a
target cycle of the same length and relabeling wires accordingly.

**Minimal code sketch (Python):**
```python
def relabel_gates(gates, sigma):
    # gates: list of (t, c1, c2)
    return [(sigma[t], sigma[c1], sigma[c2]) for (t, c1, c2) in gates]

def build_sigma(canonical_cycles, target_cycles):
    # canonical_cycles/target_cycles: list of cycles grouped by length
    sigma = {}
    for canon_cycle, target_cycle in zip(canonical_cycles, target_cycles):
        for a, b in zip(canon_cycle, target_cycle):
            sigma[a] = b
    return sigma

# Example usage:
# canonical_cycles = [[0,1,2],[3,4],[5],[6],[7]]
# target_cycles    = [[2,5,7],[1,6],[0],[3],[4]]
# sigma = build_sigma(canonical_cycles, target_cycles)
# new_gates = relabel_gates(canonical_gates, sigma)
```

---

## 9. Waksman Network (Rearrangeable Permutation Network)

**Waksman networks** are fixed topologies of 2×2 switches that can realize
**any permutation** of `n` wires by choosing the switch settings (swap / no‑swap).
They are **rearrangeable** (like Beneš): for every permutation, there exists a
routing through the network.

Key properties:

- **Size/complexity:** ~`O(n log n)` switches; depth about `2⌈log₂ n⌉ − 1` for
  powers of two (close for general `n`).
- **Structure:** recursive. One stage of switches feeds two smaller Waksman
  subnetworks; another stage of switches recombines them.
- **Routing algorithm:** given a permutation, set the first/last stages so each
  input is directed to the correct subnetwork; recurse on the induced permutations.
  This is efficient and **admits multiple valid routings**, which is useful for
  obfuscation.

**Why it matters for wire shufflers:**

- It gives a **fixed, regular circuit skeleton** (switch positions are fixed;
  only settings change).
- You can choose among multiple valid switch settings to hide the shuffle while
  keeping a uniform structure.
- It **scales much better** than truth‑table SAT as `n` grows.

**Mapping to Gate‑57:**

- Each 2×2 switch is just **swap vs no‑swap** on two wires.
- Compile each swap into a small fixed Gate‑57 macro (e.g., a 6‑gate 3‑wire swap).
- Since the macro returns the helper wire unchanged, it is safe to use any
  third wire (`n ≥ 3`).
- Total gate count is roughly:

```
gates ≈ (number of switches) × (swap‑macro size)
```

**Doc‑ready short paragraph:**

Waksman networks are rearrangeable 2×2‑switch networks that realize any wire
permutation using `O(n log n)` switches. The topology is fixed; only switch
settings vary. A standard recursive routing algorithm sets the first/last
stages to split the permutation into smaller permutations, then recurses. This
yields multiple valid routings for the same permutation, which is attractive
for obfuscation. In our setting, each switch compiles to a fixed Gate‑57 swap
macro (or identity), giving a scalable, regular wire‑shuffler construction.

---

## 10. Solver Racing (Optional)

You can race multiple SAT solvers with `SolverRacer`:

```
--solvers cadical153,glucose4
```

This can reduce tail latency on hard instances.

---

## 11. Exhaustive vs Sampled Runs

Exhaustive (small `n` only):

```
python sat_revsynth/scripts/synth_wire_shuffle.py \
  --width 4 --all-perms --order hamming-desc --max-gates 8 --verify
```

Sampled:

```
python sat_revsynth/scripts/synth_wire_shuffle.py \
  --width 5 --all-perms --order random --seed 7 --limit 50 --max-gates 8
```

---

## 12. Storage (Future DB)

You can store results in JSON for later ingestion:

```
--out-json /tmp/w4_wire_shuffles.json
```

Each record includes:

```
{
  "perm": [2,0,1],
  "found": true,
  "gate_count": 5,
  "gates": [[t,c1,c2], ...],
  "stats": { "hamming": 3, "swap_distance": 2, ... }
}
```

Optional dimgroup buckets (by gate count):

```
--out-dimgroup-dir /tmp/wire_shuffles_dimgroups
```

Note: dimgroups store circuits only; **permutation metadata is not included**.

---

## 13. Important Caveats

- **Width >= 3** is required for ECA57.
- SAT is feasible only for small widths / gate counts.
- If a permutation shows “no circuit found”, that means **UNSAT within the
  current gate bound**, not that the shuffle is impossible. Increase
  `--max-gates` (or run an extension with `--min-gates`) to improve coverage.
- `ECA57Circuit.unroll()` is meant for **identity circuits**. It does not
  preserve the shuffle permutation in general.
- `--require-all-wires` forces each wire to appear in some gate (often not
  needed for pure shuffles). If you enable this, make sure
  `--min-gates >= 1`.
- Swap-space exclusion is **on by default**, so commuting‑swap variants are
  not enumerated. If you want the full swap space, run a **separate job**
  with `--no-exclude-swap-space` and store it in a different dataset/DB.

---

## 14. Extending Runs (Incremental Bounds)

If you already ran up to some bound and want to push further without
repeating earlier gate counts, use `--min-gates`:

```
python sat_revsynth/scripts/synth_wire_shuffle.py \
  --width 6 --all-perms \
  --min-gates 11 --max-gates 12 \
  --max-solutions 999999 --exclude-swap-space \
  --solvers cadical153,glucose4 \
  --out-json /tmp/w6_g12.json
```

---

## 15. Suggested Next Steps

1. Run exhaustive `width=3` with a small gate bound and save JSON.
2. Increase to `width=4`, tune `--max-gates` until most permutations are SAT.
3. If results look good, define a lightweight DB schema keyed by:
   - width
   - permutation (or cycle type)
   - gate count
   - gate list

If you want cycle-type categories or a CSV export, those can be added to the
script easily.
