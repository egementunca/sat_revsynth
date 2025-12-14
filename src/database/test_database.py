"""Tests for database and equivalence class functionality."""
from __future__ import annotations

import pytest
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit.circuit import Circuit
from database.equivalence import (
    get_invariants,
    invariants_hash,
    circuit_to_tuple,
    compute_equivalence_class,
    select_representative,
    canonicalize,
    canonical_repr,
    are_equivalent,
)
from database.db import CircuitDatabase


class TestEquivalence:
    """Tests for equivalence class computation."""
    
    def test_get_invariants_basic(self):
        """Test invariant extraction."""
        circ = Circuit(3).cx(0, 1).mcx([0, 1], 2)
        invariants = get_invariants(circ)
        
        assert invariants[0] == 3  # width
        assert invariants[1] == 2  # gate_count
        assert isinstance(invariants[2], tuple)  # gate signature
    
    def test_invariants_preserved_under_permutation(self):
        """Test that invariants are preserved under wire permutation."""
        circ1 = Circuit(3).cx(0, 1).mcx([0, 1], 2)
        circ2 = circ1.permute([1, 0, 2])  # Swap wires 0 and 1
        
        inv1 = get_invariants(circ1)
        inv2 = get_invariants(circ2)
        
        assert inv1 == inv2
    
    def test_invariants_preserved_under_rotation(self):
        """Test that invariants are preserved under rotation."""
        circ1 = Circuit(3).cx(0, 1).x(2).mcx([0, 1], 2)
        circ2 = circ1.rotate(1)
        
        assert get_invariants(circ1) == get_invariants(circ2)
    
    def test_circuit_to_tuple(self):
        """Test circuit tuple conversion."""
        circ = Circuit(2).cx(0, 1).x(0)
        t = circuit_to_tuple(circ)
        
        assert isinstance(t, tuple)
        assert len(t) == 2
        assert t[0] == ((0,), 1)  # CNOT
        assert t[1] == ((), 0)    # X
    
    def test_compute_equivalence_class_simple(self):
        """Test equivalence class computation."""
        circ = Circuit(2).x(0).x(1)
        equiv_class = compute_equivalence_class(circ)
        
        assert len(equiv_class) >= 1
        assert circ in equiv_class
    
    def test_select_representative(self):
        """Test representative selection is deterministic."""
        circ = Circuit(2).x(0).x(1)
        equiv_class = compute_equivalence_class(circ)
        
        rep1 = select_representative(equiv_class)
        rep2 = select_representative(equiv_class)
        
        assert rep1 == rep2
    
    def test_canonicalize_deterministic(self):
        """Test that canonicalization is deterministic."""
        circ = Circuit(3).cx(0, 1).x(2)
        
        canon1 = canonicalize(circ)
        canon2 = canonicalize(circ)
        
        assert canon1 == canon2
    
    def test_equivalent_circuits_same_canonical(self):
        """Test that equivalent circuits have same canonical form."""
        circ1 = Circuit(2).x(0).x(1)
        circ2 = Circuit(2).x(1).x(0)  # Permuted version
        
        # These should be in the same equivalence class
        canon1 = canonicalize(circ1)
        canon2 = canonicalize(circ2)
        
        assert canon1 == canon2
    
    def test_are_equivalent_true(self):
        """Test equivalence detection for equivalent circuits."""
        circ1 = Circuit(2).x(0).x(1)
        circ2 = circ1.permute([1, 0])
        
        assert are_equivalent(circ1, circ2)
    
    def test_are_equivalent_false(self):
        """Test equivalence detection for non-equivalent circuits."""
        circ1 = Circuit(2).cx(0, 1)
        circ2 = Circuit(2).x(0)
        
        assert not are_equivalent(circ1, circ2)


class TestDatabase:
    """Tests for circuit database."""
    
    def test_create_database(self):
        """Test database creation."""
        with CircuitDatabase(":memory:") as db:
            assert db.count_circuits() == 0
    
    def test_add_circuit(self):
        """Test adding a circuit."""
        with CircuitDatabase(":memory:") as db:
            circ = Circuit(2).cx(0, 1)
            circuit_id, equiv_id = db.add_circuit(circ)
            
            assert circuit_id is not None
            assert equiv_id is not None
            assert db.count_circuits() == 1
    
    def test_add_duplicate_circuit(self):
        """Test that duplicate circuits return existing IDs."""
        with CircuitDatabase(":memory:") as db:
            circ = Circuit(2).cx(0, 1)
            id1, _ = db.add_circuit(circ)
            id2, _ = db.add_circuit(circ)
            
            assert id1 == id2
            assert db.count_circuits() == 1
    
    def test_add_equivalent_circuits(self):
        """Test adding equivalent circuits."""
        with CircuitDatabase(":memory:") as db:
            circ1 = Circuit(2).x(0).x(1)
            circ2 = circ1.permute([1, 0])
            
            _, equiv_id1 = db.add_circuit(circ1)
            _, equiv_id2 = db.add_circuit(circ2)
            
            # Should be in same equivalence class
            assert equiv_id1 == equiv_id2
    
    def test_query_by_width_gates(self):
        """Test querying by width and gate count."""
        with CircuitDatabase(":memory:") as db:
            db.add_circuit(Circuit(2).cx(0, 1))
            db.add_circuit(Circuit(2).x(0).x(1))
            db.add_circuit(Circuit(3).cx(0, 1))
            
            results = db.query_by_width_gates(width=2, gate_count=1)
            assert len(results) == 1
    
    def test_get_representative(self):
        """Test getting equivalence class representative."""
        with CircuitDatabase(":memory:") as db:
            circ = Circuit(2).cx(0, 1)
            _, equiv_id = db.add_circuit(circ)
            
            rep = db.get_representative(equiv_id)
            assert rep is not None
            assert rep["is_representative"] == 1
    
    def test_count_equivalence_classes(self):
        """Test counting equivalence classes."""
        with CircuitDatabase(":memory:") as db:
            db.add_circuit(Circuit(2).cx(0, 1))
            db.add_circuit(Circuit(2).x(0))
            
            count = db.count_equivalence_classes(width=2)
            assert count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
