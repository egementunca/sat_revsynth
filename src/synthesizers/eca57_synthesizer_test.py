"""Tests for ECA57 DimGroup and Collection Synthesizers."""
from __future__ import annotations

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from gates.eca57 import ECA57Circuit, ECA57Gate
from circuit.eca57_dim_group import ECA57DimGroup
from circuit.eca57_collection import ECA57Collection
from synthesizers.eca57_dimgroup_synthesizer import (
    ECA57PartialSynthesizer,
    ECA57DimGroupSynthesizer,
    benchmark_solvers,
)


class TestECA57DimGroup:
    """Tests for ECA57DimGroup container."""
    
    def test_create_empty(self):
        """Test creating empty dim group."""
        dg = ECA57DimGroup(3, 2)
        assert len(dg) == 0
        assert not dg
        assert dg.width == 3
        assert dg.gate_count == 2
    
    def test_append_circuit(self):
        """Test appending circuits."""
        dg = ECA57DimGroup(3, 2)
        
        circ = ECA57Circuit(3)
        circ.add_gate(0, 1, 2)
        circ.add_gate(0, 1, 2)
        
        dg.append(circ)
        assert len(dg) == 1
        assert dg
    
    def test_dimension_validation(self):
        """Test that dimension mismatch raises error."""
        dg = ECA57DimGroup(3, 2)
        
        # Wrong gate count
        circ = ECA57Circuit(3)
        circ.add_gate(0, 1, 2)  # Only 1 gate
        
        with pytest.raises(AssertionError):
            dg.append(circ)
    
    def test_serialization(self):
        """Test to_dict/from_dict roundtrip."""
        dg = ECA57DimGroup(3, 2)
        
        circ = ECA57Circuit(3)
        circ.add_gate(0, 1, 2)
        circ.add_gate(0, 1, 2)
        dg.append(circ)
        
        data = dg.to_dict()
        dg2 = ECA57DimGroup.from_dict(data)
        
        assert len(dg2) == 1
        assert dg2.width == 3
        assert dg2.gate_count == 2


class TestECA57Collection:
    """Tests for ECA57Collection container."""
    
    def test_create_collection(self):
        """Test creating empty collection."""
        coll = ECA57Collection(5, 4)
        assert coll.max_width == 5
        assert coll.max_gate_count == 4
        assert coll.total_circuits() == 0
    
    def test_indexing(self):
        """Test 2D indexing."""
        coll = ECA57Collection(4, 4)
        
        dg = ECA57DimGroup(3, 2)
        circ = ECA57Circuit(3)
        circ.add_gate(0, 1, 2)
        circ.add_gate(0, 1, 2)
        dg.append(circ)
        
        coll[3][2] = dg
        
        assert coll[3][2] is not None
        assert len(coll[3][2]) == 1
        assert coll.total_circuits() == 1
    
    def test_json_roundtrip(self, tmp_path):
        """Test JSON save/load."""
        coll = ECA57Collection(4, 4)
        
        dg = ECA57DimGroup(3, 2)
        circ = ECA57Circuit(3)
        circ.add_gate(0, 1, 2)
        circ.add_gate(0, 1, 2)
        dg.append(circ)
        coll[3][2] = dg
        
        path = tmp_path / "test_collection.json"
        coll.save_json(path)
        
        coll2 = ECA57Collection.load_json(path)
        assert coll2.total_circuits() == 1
        assert len(coll2[3][2]) == 1
    
    def test_compact_roundtrip(self, tmp_path):
        """Test compact format save/load."""
        coll = ECA57Collection(4, 4)
        
        dg = ECA57DimGroup(3, 2)
        circ = ECA57Circuit(3)
        circ.add_gate(0, 1, 2)
        circ.add_gate(0, 1, 2)
        dg.append(circ)
        coll[3][2] = dg
        
        path = tmp_path / "test_collection.txt"
        coll.save_compact(path)
        
        coll2 = ECA57Collection.load_compact(path)
        assert coll2.total_circuits() == 1


class TestECA57Synthesis:
    """Tests for synthesis functionality."""
    
    def test_partial_synthesizer_finds_identity(self):
        """Test that partial synthesizer finds identity circuits."""
        ps = ECA57PartialSynthesizer(3, 2, solver_name="glucose4")
        dg = ps.synthesize()
        
        # Should find some circuits
        assert len(dg) > 0
        
        # All should be identities
        for circ in dg:
            assert circ.is_identity(), f"Circuit is not identity: {circ}"
    
    def test_dimgroup_synthesizer_width3_gc2(self):
        """Test exhaustive synthesis for (3, 2)."""
        synth = ECA57DimGroupSynthesizer(3, 2, solver_name="glucose4")
        dg = synth.synthesize()
        
        # Should find all identity circuits
        assert len(dg) > 0
        
        # All should be identities
        for circ in dg:
            assert circ.is_identity()
        
        # For (3, 2), identity circuits are G;G where G is any ECA57 gate
        # There are 6 distinct gates on 3 wires
        # Each can be doubled to make identity
        # unroll expands these further via swaps, rotations, etc.
        print(f"Found {len(dg)} circuits for (3, 2)")
    
    def test_exclude_prevents_refinding(self):
        """Test that excluding a circuit prevents finding it again."""
        ps1 = ECA57PartialSynthesizer(3, 2, solver_name="glucose4")
        dg1 = ps1.synthesize()
        
        assert len(dg1) > 0
        first_circuit = dg1[0]
        
        # New synthesizer, exclude the first circuit
        ps2 = ECA57PartialSynthesizer(3, 2, solver_name="glucose4")
        ps2.exclude_subcircuit(first_circuit)
        dg2 = ps2.synthesize()
        
        # Should not contain the excluded circuit
        for circ in dg2:
            assert tuple(g.to_tuple() for g in circ.gates()) != tuple(g.to_tuple() for g in first_circuit.gates())


class TestSolverBenchmark:
    """Tests for solver benchmarking."""
    
    def test_benchmark_runs(self):
        """Test that benchmark function runs without error."""
        results = benchmark_solvers(width=3, gate_count=2)
        
        assert len(results) > 0
        
        # At least one solver should succeed
        successful = [s for s, r in results.items() if r["found"]]
        assert len(successful) > 0, f"No solvers succeeded: {results}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
