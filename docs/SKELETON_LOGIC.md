# Skeleton Logic and Chain of Non-Commuting Gates

This document explains the "Skeleton" concept used in generating robust identity circuits and details the specific logic behind enforcing a "Chain of Non-Commuting Gates."

## 1. The Concept: Backbone vs. Soup

When generating random circuits (or identities), we care about the **dependency structure**.

*   **Commuting Gates ("Soup")**: If gates $g_1$ and $g_2$ commute (share no wire), their order doesn't matter. A circuit made of many commuting gates is fluid; gates can "float" past each other. This is weak structure.
*   **Non-Commuting Gates ("Bone")**: If $g_1$ and $g_2$ collide (share a wire), their relative order is fixed (unless other intermediate gates allow a move). A sequence of colliding gates forms a rigid structure or **Backbone**.

## 2. Skeleton Graph

The **Skeleton Graph** is a representation of these collisions.
*   **Nodes**: The gates in the circuit.
*   **Edges**: An edge exists between gate $i$ and gate $j$ if they **collide** (do not commute).

In our `ECA57SkeletonSynthesizer`, we enforce constraints on this graph during generation.

### Collision Logic
For ECA57 gates $\{t, c_1, c_2\}$, two gates $g_i$ and $g_j$ collide if:
$$ \text{target}(g_i) \in \{\text{target}(g_j), \text{ctrl}_1(g_j), \text{ctrl}_2(g_j)\} $$
$$ \text{OR} $$
$$ \text{target}(g_j) \in \{\text{target}(g_i), \text{ctrl}_1(g_i), \text{ctrl}_2(g_i)\} $$

*(Note: In reversible logic, control-control overlap does not prevent commutation, but target-control or target-target overlap does.)*

## 3. Enforcement of "Chain of Non-Commuting Gates"

To blindly generate a "hard" circuit, we can strictly enforce that the circuit MUST contain a contiguous chain of collisions. This creates a "spine" that runs through the circuit, preventing it from decomposing into independent parallel sub-circuits.

### The Algorithm (`_enforce_chain`)

In `ECA57SkeletonSynthesizer.py`, the constraint is added as follows:

1.  **Define Collision Variables**: For every adjacent pair $(g_i, g_{i+1})$, create a literal $C_{i, i+1}$ which is TRUE if they collide.
2.  **Define Chain Variables**: For a chain length $L$, we create variables $Chain_{start, L}$ representing a chain starting at index `start`.
3.  **Constraint**:
    $$ Chain_{start, L} \iff \bigwedge_{k=start}^{start+L-2} C_{k, k+1} $$
    (i.e., The chain exists at `start` if and only if all adjacent pairs in the range collide).
4.  **Global Constraint**:
    $$ \bigvee_{s} Chain_{s, L} $$
    (At least one such chain must exist in the circuit).

### Why do this?
By enforcing a chain of length equal to the circuit depth (or close to it), we ensure the circuit is fully entangled in time. No part of the circuit can be trivially reordered away from its neighbors without resolving the non-commutativity.

## 4. Generated Examples

We have generated example identity circuits that satisfy these strict chain constraints (saved in `sat_revsynth/generated_skeletons/`):

*   **[chain_3w_6g.gate](generated_skeletons/chain_3w_6g.gate)**: 3 wires, 6 gates. Full chain.
*   **[chain_4w_10g.gate](generated_skeletons/chain_4w_10g.gate)**: 4 wires, 10 gates. Full chain.
*   **[chain_6w_12g.gate](generated_skeletons/chain_6w_12g.gate)**: 6 wires, 12 gates. Full chain.
*   **[chain_8w_16g.gate](generated_skeletons/chain_8w_16g.gate)**: 8 wires, 16 gates. Full chain.

These circuits are guaranteed to be "stiff" - you cannot reorder the gates significantly because every gate is "locked" to its neighbor by a shared wire operation.
