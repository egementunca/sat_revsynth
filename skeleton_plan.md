# Experimental: Skeleton Graph Constraints

## Goal
Explore "HARD" identity templates by enforcing specific structural properties based on the **Skeleton Graph** concept. Limiting the search space to circuits with specific collision properties (e.g., long non-commuting chains) may reveal complex identities that are otherwise hard to find.

## User Review Required
> [!IMPORTANT]
> This is an experimental feature. We will create a new synthesizer subclass `ECA57SkeletonSynthesizer` to avoid breaking the main exploration.

## Concept: Skeleton Graph & Collisions
Based on the provided description and image:
1.  **Collision**: Two gates $\gamma_i$ and $\gamma_j$ **collide** (do not commute) if targets of one are in the controls of the other.
    -   Gate $\gamma = (t, c_1, c_2)$
    -   Condition: $\gamma_i$ and $\gamma_j$ collide if $t_i \in \{c_{1j}, c_{2j}\}$ OR $t_j \in \{c_{1i}, c_{2i}\}$.
2.  **Edge**: Directed edge $g_i \to g_j$ exists iff:
    -   $i < j$
    -   $\gamma_i$ and $\gamma_j$ collide
    -   No intermediate gate $g_k$ ($i < k < j$) collides with *both* $\gamma_i$ and $\gamma_j$.
3.  **Target Property**: "Long non-commutating colliding chain".
    -   Enforce that the skeleton graph contains a simple path of length $L$ (or is exactly a path).

## Proposed Changes

### 1. New Synthesizer Class
Create `src/synthesizers/eca57_skeleton_synthesizer.py`.
-   Inherit from `ECA57Synthesizer` or wrap it.
-   Add SAT constraints for "Collision".

### 2. SAT Encoding of Collisions
-   Define `collision_{i}_{j}` variable for all pairs $i < j$.
    -   `collision_{i}_{j}` $\iff$ $(t_i = c_{1j}) \lor (t_i = c_{2j}) \lor (t_j = c_{1i}) \lor (t_j = c_{2i})$.
-   This can be encoded using the existing variables $t_{w,i}, c_{w,i}$.
    -   Example: $t_i = c_{1j}$ is true if $\exists w: t_{w,i} \land c1_{w,j}$.

### 3. Encoding Skeleton Edges
-   Define `edge_{i}_{j}`.
    -   `edge_{i}_{j}` $\iff$ `collision_{i}_{j}` $\land$ $\forall k (i < k < j): \neg(\text{collision}_{i,k} \land \text{collision}_{k,j})$.

### 4. Enforcing Chain Structure
-   To force a "long chain", we can require:
    -   $edge_{i, i+1}$ is TRUE for all $i$ (simplest chain).
    -   OR allow "skips" but force a path.
-   **User Request**: "long noncommutating colliding chain next to each other".
    -   Simplest interpretation: Gate $i$ and Gate $i+1$ MUST collide for all $i$.
    -   This forces a purely non-commuting sequence $g_1 \leftrightarrow g_2 \leftrightarrow \dots \leftrightarrow g_m$.

## Verification Plan
1.  **Unit Test**: Create a small `w=4, gc=5` test.
2.  **Constraint**: Force `collision_{i, i+1}` for all $i$.
3.  **Check**: Verify generated circuits actually have this property (manually check shared wires).
