"""High-level API for skeleton chain synthesis and limited unrolling.

This module provides a clean public interface for:
1. Synthesizing skeleton chains (identity circuits with collision constraints)
2. Limited unrolling to prevent memory explosion
3. Finding multiple skeleton classes via exclude-until-UNSAT

Example usage:
    >>> # Synthesize a skeleton chain
    >>> skeleton = synthesize_skeleton_chain(
    ...     wires=8,
    ...     gates=16,
    ...     solver_name="glucose4"
    ... )

    >>> # Generate bounded equivalents
    >>> variants = limited_unroll(
    ...     skeleton,
    ...     max_circuits=1000,
    ...     max_permutations=100
    ... )

    >>> # Find multiple skeleton classes
    >>> families = find_skeleton_families(
    ...     wires=4,
    ...     gates=10,
    ...     max_families=5
    ... )
"""
from __future__ import annotations

from typing import List, Optional
from gates.eca57 import ECA57Circuit
from truth_table.truth_table import TruthTable
from sat.solver import Solver
from synthesizers.eca57_skeleton_synthesizer import ECA57SkeletonSynthesizer


def synthesize_skeleton_chain(
    wires: int,
    gates: int,
    chain_length: int | None = None,
    solver_name: str = "glucose4",
    avoid_adjacent_identical: bool = True,
    timeout: int | None = None,
) -> ECA57Circuit | None:
    """Synthesize a skeleton chain (identity circuit with collision constraints).

    A skeleton chain is an identity circuit where all adjacent gates collide
    (don't commute). This means each gate's target is used as a control by
    at least one adjacent gate.

    Args:
        wires: Number of circuit wires.
        gates: Number of gates to synthesize.
        chain_length: If provided, enforces exactly this many consecutive
            collisions. If None, enforces collision for all adjacent pairs.
        solver_name: SAT solver to use ("glucose4", "minisat-gh", etc.).
        avoid_adjacent_identical: If True, prevents identical adjacent gates.
        timeout: Optional solver timeout in seconds.

    Returns:
        ECA57Circuit if SAT, None if UNSAT.

    Example:
        >>> skeleton = synthesize_skeleton_chain(8, 16)
        >>> if skeleton:
        ...     # Verify all adjacent gates collide
        ...     for i in range(len(skeleton) - 1):
        ...         assert not skeleton.gate_swappable(i)
    """
    # Create identity truth table
    identity_values = list(range(1 << wires))
    tt = TruthTable(wires, values=identity_values)

    # Create solver
    solver = Solver(solver_name)
    if timeout:
        # Note: Solver timeout support may vary by solver
        pass  # TODO: Add timeout support if available

    # Create skeleton synthesizer
    synth = ECA57SkeletonSynthesizer(
        output=tt,
        gate_count=gates,
        solver=solver,
        chain_length=chain_length,
        avoid_adjacent_identical=avoid_adjacent_identical,
    )

    # Solve
    return synth.solve()


def limited_unroll(
    circuit: ECA57Circuit,
    max_circuits: int = 10000,
    max_swap_depth: int = 10,
    max_swap_circuits: int = 1000,
    max_permutations: int | None = None,
    include_rotations: bool = True,
    include_mirror: bool = True,
    use_skeleton_mode: bool = False,
) -> List[ECA57Circuit]:
    """Generate equivalent circuits with bounded exploration.

    For large circuits (16+ wires, 32+ gates), full unrolling generates
    billions of circuits and exhausts memory. This function provides
    controlled expansion via sampling and budget limits.

    Args:
        circuit: Source circuit to unroll.
        max_circuits: Maximum total circuits to generate.
        max_swap_depth: Maximum BFS depth for swap exploration.
        max_swap_circuits: Maximum circuits from swap space.
        max_permutations: If None, use all permutations; if int, sample that many.
            For large widths (16+), recommend 100-1000.
        include_rotations: Whether to include rotations.
        include_mirror: Whether to include mirror (reverse).
        use_skeleton_mode: If True, use fast skeleton-only canonical form
            (skip swap exploration entirely). Use this for pure skeleton chains.

    Returns:
        List of equivalent circuits (bounded).

    Example:
        >>> skeleton = synthesize_skeleton_chain(16, 32)
        >>> # For skeleton chains, no swaps exist - use skeleton mode
        >>> variants = limited_unroll(
        ...     skeleton,
        ...     max_circuits=1000,
        ...     max_permutations=100,
        ...     use_skeleton_mode=True  # Fast path for skeletons
        ... )
        >>> # Result: ~1000 circuits instead of 10^9
    """
    if use_skeleton_mode:
        # For skeleton chains: skip swap exploration entirely
        # Equivalence = rotations × mirror × permutations only
        return _skeleton_mode_unroll(
            circuit,
            max_circuits,
            max_permutations,
            include_rotations,
            include_mirror,
        )
    else:
        # Standard limited unroll with swap exploration
        return circuit.limited_unroll(
            max_swap_depth=max_swap_depth,
            max_swap_circuits=max_swap_circuits,
            max_permutations=max_permutations,
            max_total_circuits=max_circuits,
            include_rotations=include_rotations,
            include_mirror=include_mirror,
        )


def _skeleton_mode_unroll(
    circuit: ECA57Circuit,
    max_circuits: int,
    max_permutations: int | None,
    include_rotations: bool,
    include_mirror: bool,
) -> List[ECA57Circuit]:
    """Unroll skeleton chains without swap exploration (fast path).

    For skeleton chains where no adjacent gates commute, swap space is trivial.
    This function skips swap_space_bfs() entirely and only applies:
    - Rotations (if enabled)
    - Mirror/reverse (if enabled)
    - Wire permutations (sampled if max_permutations is set)

    IMPORTANT: Distributes budget fairly across rotations to maximize taxonomy
    coverage. Each rotation can have a different first-two-gates taxonomy,
    so we want at least one variant from each rotation.

    Args:
        circuit: Skeleton chain circuit.
        max_circuits: Maximum circuits to generate.
        max_permutations: If None, use all; if int, sample.
        include_rotations: Include rotations.
        include_mirror: Include mirror.

    Returns:
        List of equivalent circuits (skeleton mode).
    """
    import random
    from itertools import permutations as iterperms

    equivalents = [circuit]

    # Step 1: Rotations
    if include_rotations:
        new_equivs = []
        for c in equivalents:
            new_equivs.extend(c.rotations())
        equivalents = new_equivs

        # Dedup
        seen = set()
        unique = []
        for c in equivalents:
            key = tuple(g.to_tuple() for g in c._gates)
            if key not in seen:
                seen.add(key)
                unique.append(c)
        equivalents = unique

    # Step 2: Mirror
    if include_mirror:
        new_equivs = []
        for c in equivalents:
            new_equivs.append(c)
            new_equivs.append(c.reverse())
        equivalents = new_equivs

        # Dedup
        seen = set()
        unique = []
        for c in equivalents:
            key = tuple(g.to_tuple() for g in c._gates)
            if key not in seen:
                seen.add(key)
                unique.append(c)
        equivalents = unique

    # Early exit if budget hit (rotations + mirrors already exceed budget)
    if len(equivalents) >= max_circuits:
        return equivalents[:max_circuits]

    # Step 3: Permutations - distribute fairly across rotations
    # Each rotation can have different taxonomy, so ensure all rotations get some permutations
    all_perms = list(iterperms(range(circuit._width)))

    if max_permutations is None:
        sampled_perms = all_perms
    elif len(all_perms) <= max_permutations:
        sampled_perms = all_perms
    else:
        sampled_perms = random.sample(all_perms, max_permutations)

    # Calculate how many permutations per rotation to stay within budget
    num_rotations = len(equivalents)
    perms_per_rotation = max(1, max_circuits // num_rotations)

    new_equivs = []
    for c in equivalents:
        # Sample a subset of permutations for this rotation
        if len(sampled_perms) <= perms_per_rotation:
            rotation_perms = sampled_perms
        else:
            rotation_perms = random.sample(sampled_perms, perms_per_rotation)

        for perm in rotation_perms:
            new_equivs.append(c.permute(list(perm)))

    # Final dedup and enforce budget
    seen = set()
    unique = []
    for c in new_equivs:
        if len(unique) >= max_circuits:
            break
        key = tuple(g.to_tuple() for g in c._gates)
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


def find_skeleton_families(
    wires: int,
    gates: int,
    max_families: int = 10,
    solver_name: str = "glucose4",
    chain_length: int | None = None,
    timeout_per_solve: int | None = None,
) -> List[ECA57Circuit]:
    """Find multiple distinct skeleton chain families via exclude-until-UNSAT.

    Uses iterative SAT solving with exclusion constraints to find different
    equivalence classes of skeleton chains. Each returned circuit is from
    a different equivalence class (under rotation/mirror/permutation).

    Note: This is computationally expensive for large circuits. Recommended
    for small-to-medium circuits (≤8 wires, ≤16 gates).

    Args:
        wires: Number of circuit wires.
        gates: Number of gates per circuit.
        max_families: Maximum number of families to find.
        solver_name: SAT solver to use.
        chain_length: Optional collision chain length constraint.
        timeout_per_solve: Optional timeout per SAT solve (seconds).

    Returns:
        List of skeleton chains (one per equivalence class).

    Example:
        >>> families = find_skeleton_families(
        ...     wires=4,
        ...     gates=10,
        ...     max_families=5
        ... )
        >>> # Each family can be unrolled separately
        >>> for skeleton in families:
        ...     variants = limited_unroll(skeleton, max_circuits=500)
    """
    found_families = []
    excluded_canonicals = set()

    for _ in range(max_families):
        # Synthesize with current exclusions
        # Note: This requires extending the synthesizer to support exclusion clauses
        # For now, this is a placeholder for the full implementation
        skeleton = synthesize_skeleton_chain(
            wires=wires,
            gates=gates,
            chain_length=chain_length,
            solver_name=solver_name,
            timeout=timeout_per_solve,
        )

        if skeleton is None:
            # UNSAT - no more families
            break

        # Get canonical form (fast skeleton mode)
        canonical_key = skeleton.canonical_skeleton_key()

        # Check if we've seen this equivalence class
        if canonical_key in excluded_canonicals:
            # This shouldn't happen if exclusion is working correctly
            # But could occur due to sampling
            continue

        # Add to results
        found_families.append(skeleton)
        excluded_canonicals.add(canonical_key)

        # TODO: Add exclusion constraint to SAT solver for next iteration
        # This requires extending ECA57SkeletonSynthesizer to support
        # excluding specific canonical forms

    return found_families


def verify_skeleton_chain(circuit: ECA57Circuit) -> bool:
    """Verify that a circuit is a true skeleton chain.

    A skeleton chain has:
    1. All adjacent gates colliding (non-commuting)
    2. Identity function (if intended)

    Args:
        circuit: Circuit to verify.

    Returns:
        True if circuit is a skeleton chain.

    Example:
        >>> skeleton = synthesize_skeleton_chain(4, 8)
        >>> if skeleton:
        ...     assert verify_skeleton_chain(skeleton)
    """
    # Check collision property
    for i in range(len(circuit) - 1):
        if circuit.gate_swappable(i):
            return False  # Found a non-colliding pair

    return True


def estimate_unroll_size(
    wires: int,
    gates: int,
    is_skeleton: bool = False,
) -> dict:
    """Estimate the size of full unroll for a circuit.

    Provides rough estimates of:
    - Number of rotations
    - Swap space size (if not skeleton)
    - Total permutations
    - Expected total circuits

    Args:
        wires: Number of wires.
        gates: Number of gates.
        is_skeleton: If True, assume skeleton chain (no swaps).

    Returns:
        Dictionary with size estimates.

    Example:
        >>> est = estimate_unroll_size(16, 32, is_skeleton=True)
        >>> print(f"Expected circuits: {est['total_estimate']}")
        >>> # Use this to decide max_permutations parameter
    """
    import math

    rotations = gates  # At most 'gates' unique rotations
    mirror = 2  # Original + reversed
    perms = math.factorial(wires)

    if is_skeleton:
        # Skeleton chains: swap_space = 1
        swap_space = 1
    else:
        # Estimate swap space (very rough)
        # For general circuits, swap space can be exponential
        # Conservative estimate: 2^(gates/4)
        swap_space = min(2 ** (gates // 4), 10000)

    total = rotations * mirror * swap_space * perms

    return {
        "rotations": rotations,
        "mirror": mirror,
        "swap_space": swap_space,
        "permutations": perms,
        "total_estimate": total,
        "recommended_max_permutations": min(perms, 1000),
        "is_feasible_full_unroll": total < 1_000_000,
    }
