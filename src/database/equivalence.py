"""Equivalence class computation for reversible circuits.

Circuits are equivalent under the unroll operations:
    - Swaps: commute adjacent non-interfering gates
    - Rotations: cyclic permutation of gate order  
    - Reversals: mirror the circuit
    - Wire permutations: relabel wires

Due to commutation constraints, circuits with identical invariants
(width, depth, gate types) may belong to different equivalence classes
if no swap sequence connects them.
"""
from __future__ import annotations

from typing import TYPE_CHECKING
from functools import lru_cache
import hashlib
import json

if TYPE_CHECKING:
    from circuit.circuit import Circuit


def get_invariants(circuit: "Circuit") -> tuple:
    """Get invariants that are preserved across equivalence operations.
    
    Returns:
        Tuple of (width, gate_count, sorted gate signatures).
        Gate signature is (num_controls, target_position_type).
    """
    width = circuit.width()
    gate_count = len(circuit)
    
    # Count gates by structure (number of controls)
    control_counts = {}
    for controls, _ in circuit.gates():
        num_controls = len(controls)
        control_counts[num_controls] = control_counts.get(num_controls, 0) + 1
    
    # Sort for consistent representation
    gate_signature = tuple(sorted(control_counts.items()))
    
    return (width, gate_count, gate_signature)


def invariants_hash(circuit: "Circuit") -> str:
    """Compute a hash of circuit invariants for quick comparison."""
    invariants = get_invariants(circuit)
    invariant_str = json.dumps(invariants, sort_keys=True)
    return hashlib.sha256(invariant_str.encode()).hexdigest()[:16]


def circuit_to_tuple(circuit: "Circuit") -> tuple:
    """Convert circuit to a hashable tuple representation."""
    return tuple(
        (tuple(controls), target) 
        for controls, target in circuit.gates()
    )


def tuple_to_gates(t: tuple) -> list:
    """Convert tuple representation back to gates list."""
    return [(list(controls), target) for controls, target in t]


def compute_equivalence_class(circuit: "Circuit") -> list["Circuit"]:
    """Compute the full equivalence class of a circuit via BFS over unroll operations.
    
    Uses the existing unroll() method which applies swaps, rotations, 
    reversals, and wire permutations.
    
    Args:
        circuit: The circuit to find equivalents for.
        
    Returns:
        List of all circuits equivalent to the input under unroll operations.
    """
    return circuit.unroll()


def select_representative(equiv_class: list["Circuit"]) -> "Circuit":
    """Select a canonical representative from an equivalence class.
    
    Uses lexicographic ordering on the gate tuple representation:
    ((controls0, target0), (controls1, target1), ...)
    
    The smallest such tuple is chosen as the representative.
    
    Args:
        equiv_class: List of equivalent circuits.
        
    Returns:
        The lexicographically smallest circuit.
    """
    if not equiv_class:
        raise ValueError("Cannot select representative from empty class")
    
    # Convert to tuple form for comparison
    circuit_tuples = [(circuit_to_tuple(c), c) for c in equiv_class]
    
    # Sort by tuple representation
    circuit_tuples.sort(key=lambda x: x[0])
    
    return circuit_tuples[0][1]


def canonicalize(circuit: "Circuit") -> "Circuit":
    """Return the canonical (lexicographically minimal) form of a circuit.
    
    This computes the full equivalence class and returns the representative.
    For circuits where computing the full class is expensive, use 
    select_representative on a precomputed class.
    
    Args:
        circuit: The circuit to canonicalize.
        
    Returns:
        The canonical representative of the circuit's equivalence class.
    """
    equiv_class = compute_equivalence_class(circuit)
    return select_representative(equiv_class)


def canonical_repr(circuit: "Circuit") -> str:
    """Get a string representation of the canonical form for database storage.
    
    Returns:
        JSON string of the canonical gate tuple.
    """
    canon = canonicalize(circuit)
    return json.dumps(circuit_to_tuple(canon))


def are_equivalent(circuit_a: "Circuit", circuit_b: "Circuit") -> bool:
    """Check if two circuits are in the same equivalence class.
    
    First checks invariants (fast), then computes equivalence class if needed.
    
    Args:
        circuit_a: First circuit.
        circuit_b: Second circuit.
        
    Returns:
        True if circuits are equivalent under unroll operations.
    """
    # Quick check: invariants must match
    if get_invariants(circuit_a) != get_invariants(circuit_b):
        return False
    
    # Compute equivalence class of a and check if b is in it
    equiv_class_a = compute_equivalence_class(circuit_a)
    return circuit_b in equiv_class_a
