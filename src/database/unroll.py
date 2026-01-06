"""Unrolling pipeline for cheap template expansion.

Generates more templates from seed templates using identity-preserving transforms:
- mirror: reverse gate order (gates are self-inverse for ECA57)
- permute_lines: wire relabeling
- rotate: cyclic gate rotation
- gate_swap_dfs: enumerate via commuting swaps
"""
from __future__ import annotations

import itertools
from typing import Iterator, Optional, Set, Any
from dataclasses import dataclass

from database.basis import GateBasis, ECA57Basis
from database.templates import TemplateRecord, TemplateStore, OriginKind


# Unroll operation flags (bitfield)
UNROLL_MIRROR = 1 << 0
UNROLL_PERMUTE = 1 << 1
UNROLL_ROTATE = 1 << 2
UNROLL_SWAP = 1 << 3


def mirror(gates: list, basis: GateBasis) -> list:
    """Mirror a template: reverse order and invert each gate.
    
    For ECA57, gates are self-inverse, so just reverse.
    """
    return [basis.invert(g) for g in reversed(gates)]


def permute_lines(gates: list, perm: list[int], basis: GateBasis) -> list:
    """Permute wire labels according to perm.
    
    Args:
        gates: List of gates.
        perm: Permutation where perm[old] = new.
        basis: Gate basis.
        
    Returns:
        Gates with wires relabeled.
    """
    result = []
    for gate in gates:
        wires = basis.touched_wires(gate)
        new_wires = [perm[w] for w in wires]
        
        # Reconstruct gate (ECA57 specific for now)
        result.append(tuple(new_wires))
    
    return result


def rotate(gates: list, r: int) -> list:
    """Rotate gates cyclically by r positions.
    
    For identity circuits, this preserves the identity property.
    rotate(gates, 1) moves first gate to end.
    
    Args:
        gates: List of gates.
        r: Rotation amount (positive = rotate left).
        
    Returns:
        Rotated gate list.
    """
    if not gates or r == 0:
        return gates
    r = r % len(gates)
    return gates[r:] + gates[:r]


def adjacent_commuting_pairs(gates: list, basis: GateBasis) -> Iterator[int]:
    """Find indices where adjacent gates commute.
    
    Yields:
        Index i where gates[i] and gates[i+1] commute.
    """
    for i in range(len(gates) - 1):
        if basis.commutes(gates[i], gates[i + 1]):
            yield i


def swap_at(gates: list, idx: int) -> list:
    """Swap adjacent gates at index idx."""
    result = list(gates)
    result[idx], result[idx + 1] = result[idx + 1], result[idx]
    return result


def gate_swap_dfs(
    gates: list,
    width: int,
    basis: GateBasis,
    max_nodes: int = 10000,
) -> Iterator[list]:
    """Enumerate template variants via commuting gate swaps.
    
    Performs BFS/DFS over the graph where:
    - Nodes are canonical gate orderings
    - Edges are swaps of adjacent commuting gates
    
    Args:
        gates: Initial gate list.
        width: Circuit width.
        basis: Gate basis.
        max_nodes: Budget for exploration.
        
    Yields:
        Gate lists (including the original).
    """
    # Get canonical form of initial
    _, initial_hash = basis.canonicalize(gates, width)
    
    visited: Set[bytes] = {initial_hash}
    queue = [gates]
    node_count = 0
    
    while queue and node_count < max_nodes:
        current = queue.pop(0)
        node_count += 1
        yield current
        
        # Try all commuting swaps
        for idx in adjacent_commuting_pairs(current, basis):
            swapped = swap_at(current, idx)
            _, swap_hash = basis.canonicalize(swapped, width)
            
            if swap_hash not in visited:
                visited.add(swap_hash)
                queue.append(swapped)


@dataclass
class UnrollConfig:
    """Configuration for unrolling."""
    do_mirror: bool = True
    do_permute: bool = True
    do_rotate: bool = True
    do_swap_dfs: bool = True
    swap_dfs_budget: int = 1000
    max_permutations: int = 24  # Limit for large widths


def unroll_template(
    gates: list,
    width: int,
    basis: GateBasis,
    config: Optional[UnrollConfig] = None,
) -> Iterator[tuple[list, int]]:
    """Generate all variants of a template via unrolling.
    
    Args:
        gates: Original gate list.
        width: Circuit width.
        basis: Gate basis.
        config: Unrolling configuration.
        
    Yields:
        (variant_gates, unroll_ops_bitfield) tuples.
    """
    config = config or UnrollConfig()
    
    # Start with original
    base_variants = [(gates, 0)]
    
    # Apply mirror
    if config.do_mirror:
        mirrored = mirror(gates, basis)
        base_variants.append((mirrored, UNROLL_MIRROR))
    
    # Apply rotations
    if config.do_rotate and len(gates) > 1:
        for r in range(1, len(gates)):
            rotated = rotate(gates, r)
            base_variants.append((rotated, UNROLL_ROTATE))
            
            if config.do_mirror:
                rot_mir = mirror(rotated, basis)
                base_variants.append((rot_mir, UNROLL_ROTATE | UNROLL_MIRROR))
    
    # Apply wire permutations
    permuted_variants = []
    if config.do_permute:
        # Generate permutations of [0..width-1]
        perms = list(itertools.permutations(range(width)))
        
        # Limit if too many
        if len(perms) > config.max_permutations:
            perms = perms[:config.max_permutations]
        
        for variant, ops in base_variants:
            for perm in perms:
                if list(perm) == list(range(width)):
                    continue  # Skip identity permutation
                permuted = permute_lines(variant, list(perm), basis)
                permuted_variants.append((permuted, ops | UNROLL_PERMUTE))
    
    all_variants = base_variants + permuted_variants
    
    # Apply swap DFS to each variant
    if config.do_swap_dfs:
        for variant, ops in all_variants:
            for swapped in gate_swap_dfs(variant, width, basis, config.swap_dfs_budget):
                yield (swapped, ops | UNROLL_SWAP)
    else:
        for variant, ops in all_variants:
            yield (variant, ops)


def unroll_and_insert(
    store: TemplateStore,
    source_record: TemplateRecord,
    gates: list,
    width: int,
    config: Optional[UnrollConfig] = None,
) -> tuple[int, int]:
    """Unroll a template and insert all variants into the store.
    
    Args:
        store: Template store.
        source_record: The source template record.
        gates: Source gate list.
        width: Circuit width.
        config: Unrolling configuration.
        
    Returns:
        (inserted_count, duplicate_count)
    """
    inserted = 0
    duplicates = 0
    
    for variant_gates, unroll_ops in unroll_template(
        gates, width, store.basis, config
    ):
        record = store.insert_template(
            gates=variant_gates,
            width=width,
            origin=OriginKind.UNROLL,
            origin_template_id=source_record.template_id,
            unroll_ops=unroll_ops,
            family_hash=source_record.family_hash,
        )
        
        if record is not None:
            inserted += 1
        else:
            duplicates += 1
    
    return inserted, duplicates
