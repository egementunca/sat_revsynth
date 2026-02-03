"""Tests for skeleton chain database."""
from __future__ import annotations

import tempfile
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.skeleton_db import (
    CollisionType,
    GatePair,
    get_collision_type,
    gate_pair_taxonomy,
    circuit_to_blob,
    serialize_circuit_list,
    deserialize_circuit_list,
    SkeletonDBBuilder,
    SkeletonDBConfig,
    enumerate_all_taxonomies,
    enumerate_collision_taxonomies,
    count_collision_taxonomies,
)
from gates.eca57 import ECA57Circuit


class TestCollisionType:
    """Tests for CollisionType enum."""

    def test_collision_type_values(self):
        """Test that enum values match Rust definitions."""
        assert CollisionType.OnActive == 0
        assert CollisionType.OnCtrl1 == 1
        assert CollisionType.OnCtrl2 == 2
        assert CollisionType.OnNew == 3

    def test_get_collision_type_on_active(self):
        """Test detecting collision on target wire."""
        g1 = (0, 1, 2)  # target=0, ctrl1=1, ctrl2=2
        assert get_collision_type(g1, 0) == CollisionType.OnActive

    def test_get_collision_type_on_ctrl1(self):
        """Test detecting collision on ctrl1 wire."""
        g1 = (0, 1, 2)
        assert get_collision_type(g1, 1) == CollisionType.OnCtrl1

    def test_get_collision_type_on_ctrl2(self):
        """Test detecting collision on ctrl2 wire."""
        g1 = (0, 1, 2)
        assert get_collision_type(g1, 2) == CollisionType.OnCtrl2

    def test_get_collision_type_on_new(self):
        """Test detecting no collision."""
        g1 = (0, 1, 2)
        assert get_collision_type(g1, 3) == CollisionType.OnNew
        assert get_collision_type(g1, 5) == CollisionType.OnNew


class TestGatePair:
    """Tests for GatePair taxonomy."""

    def test_gate_pair_creation(self):
        """Test creating a GatePair."""
        gp = GatePair(
            a=CollisionType.OnActive,
            c1=CollisionType.OnCtrl1,
            c2=CollisionType.OnNew,
        )
        assert gp.a == CollisionType.OnActive
        assert gp.c1 == CollisionType.OnCtrl1
        assert gp.c2 == CollisionType.OnNew

    def test_gate_pair_serialization(self):
        """Test GatePair serialization matches Rust bincode format."""
        gp = GatePair(
            a=CollisionType.OnActive,
            c1=CollisionType.OnCtrl1,
            c2=CollisionType.OnNew,
        )
        data = gp.to_bytes()

        # Should be 12 bytes (3 x u32)
        assert len(data) == 12

        # Test round-trip
        gp2 = GatePair.from_bytes(data)
        assert gp == gp2

    def test_gate_pair_all_variants(self):
        """Test all CollisionType combinations serialize correctly."""
        for a in CollisionType:
            for c1 in CollisionType:
                for c2 in CollisionType:
                    gp = GatePair(a, c1, c2)
                    data = gp.to_bytes()
                    gp2 = GatePair.from_bytes(data)
                    assert gp == gp2

    def test_gate_pair_is_collision(self):
        """Test collision detection."""
        # Gates collide when target of one hits controls of other

        # gate2's target hits gate1's ctrl1 -> collision
        gp1 = GatePair(
            a=CollisionType.OnCtrl1,
            c1=CollisionType.OnNew,
            c2=CollisionType.OnNew,
        )
        assert gp1.is_collision()

        # gate2's ctrl1 hits gate1's target -> collision
        gp2 = GatePair(
            a=CollisionType.OnNew,
            c1=CollisionType.OnActive,
            c2=CollisionType.OnNew,
        )
        assert gp2.is_collision()

        # No collision: all OnNew
        gp3 = GatePair(
            a=CollisionType.OnNew,
            c1=CollisionType.OnNew,
            c2=CollisionType.OnNew,
        )
        assert not gp3.is_collision()
        assert gp3.is_none()

    def test_gate_pair_taxonomy(self):
        """Test computing taxonomy from two gates."""
        g1 = (0, 1, 2)
        g2 = (1, 0, 3)  # target=1 (OnCtrl1 of g1), ctrl1=0 (OnActive of g1)

        tax = gate_pair_taxonomy(g1, g2)

        assert tax.a == CollisionType.OnCtrl1   # g2's target=1 is g1's ctrl1
        assert tax.c1 == CollisionType.OnActive  # g2's ctrl1=0 is g1's target
        assert tax.c2 == CollisionType.OnNew     # g2's ctrl2=3 is not in g1


class TestCircuitSerialization:
    """Tests for circuit blob serialization."""

    def test_circuit_to_blob(self):
        """Test converting circuit to blob format."""
        circuit = ECA57Circuit(4)
        circuit.add_gate(0, 1, 2)
        circuit.add_gate(1, 0, 3)

        blob = circuit_to_blob(circuit)

        # Each gate is 3 bytes
        assert len(blob) == 6
        assert blob == bytes([0, 1, 2, 1, 0, 3])

    def test_circuit_list_serialization(self):
        """Test serializing list of circuit blobs."""
        circuits = [
            bytes([0, 1, 2, 1, 0, 3]),
            bytes([0, 2, 1]),
        ]

        data = serialize_circuit_list(circuits)
        circuits2 = deserialize_circuit_list(data)

        assert circuits == circuits2

    def test_circuit_list_empty(self):
        """Test serializing empty list."""
        circuits = []

        data = serialize_circuit_list(circuits)
        circuits2 = deserialize_circuit_list(data)

        assert circuits2 == []

    def test_circuit_list_single(self):
        """Test serializing single circuit."""
        circuits = [bytes([0, 1, 2])]

        data = serialize_circuit_list(circuits)
        circuits2 = deserialize_circuit_list(data)

        assert circuits == circuits2


class TestTaxonomyEnumeration:
    """Tests for taxonomy enumeration utilities."""

    def test_enumerate_all_taxonomies(self):
        """Test enumerating all taxonomies."""
        all_tax = list(enumerate_all_taxonomies())

        # 4^3 = 64 total combinations
        assert len(all_tax) == 64

        # Should be unique
        assert len(set(all_tax)) == 64

    def test_enumerate_collision_taxonomies(self):
        """Test enumerating collision taxonomies only."""
        collision_tax = list(enumerate_collision_taxonomies())

        # All should be collisions
        for tax in collision_tax:
            assert tax.is_collision()

        # Should be non-empty
        assert len(collision_tax) > 0

        # Should be less than total
        assert len(collision_tax) < 64

    def test_count_collision_taxonomies(self):
        """Test counting collision taxonomies."""
        count = count_collision_taxonomies()

        # Should match enumeration
        assert count == len(list(enumerate_collision_taxonomies()))

        # Known value: 64 - 18 = 46 collision types
        # (all combinations where at least one is not OnNew, minus non-collision ones)
        assert count == 46


class TestSkeletonDBBuilder:
    """Tests for SkeletonDBBuilder."""

    def test_builder_creation(self):
        """Test creating a database builder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_db"

            config = SkeletonDBConfig(
                map_size=10 * 1024 * 1024,  # 10 MB for testing
                min_wires=4,
                max_wires=4,
            )

            with SkeletonDBBuilder(db_path, config) as builder:
                assert builder.path == db_path
                assert db_path.exists()

    def test_add_skeleton(self):
        """Test adding a skeleton circuit to the database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_db"

            config = SkeletonDBConfig(map_size=10 * 1024 * 1024)

            with SkeletonDBBuilder(db_path, config) as builder:
                # Create a simple circuit (may not be identity)
                circuit = ECA57Circuit(4)
                circuit.add_gate(0, 1, 2)
                circuit.add_gate(1, 0, 3)

                taxonomy = builder.add_skeleton(circuit, 4)

                assert taxonomy is not None
                assert builder.stats["circuits_added"] == 1

    def test_lookup(self):
        """Test looking up circuits by taxonomy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_db"

            config = SkeletonDBConfig(map_size=10 * 1024 * 1024)

            with SkeletonDBBuilder(db_path, config) as builder:
                # Add a circuit
                circuit = ECA57Circuit(4)
                circuit.add_gate(0, 1, 2)
                circuit.add_gate(1, 0, 3)

                taxonomy = builder.add_skeleton(circuit, 4)

                # Lookup
                circuits = builder.lookup(4, taxonomy)

                assert len(circuits) == 1
                assert circuits[0] == circuit_to_blob(circuit)

    def test_get_random_identity(self):
        """Test getting a random identity from database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_db"

            config = SkeletonDBConfig(map_size=10 * 1024 * 1024)

            with SkeletonDBBuilder(db_path, config) as builder:
                # Add multiple circuits with same taxonomy
                # Use valid wire combinations (all distinct wires per gate)
                unique_gates = [
                    (2, 0, 3),  # Different third gates
                    (2, 3, 0),
                    (3, 0, 2),
                    (3, 2, 0),
                    (2, 1, 3),
                ]
                for i, (t, c1, c2) in enumerate(unique_gates):
                    circuit = ECA57Circuit(4)
                    circuit.add_gate(0, 1, 2)
                    circuit.add_gate(1, 0, 3)
                    circuit.add_gate(t, c1, c2)
                    builder.add_skeleton(circuit, 4)

                # Get taxonomy from first circuit
                g1 = (0, 1, 2)
                g2 = (1, 0, 3)
                taxonomy = gate_pair_taxonomy(g1, g2)

                # Get random
                blob = builder.get_random_identity(4, taxonomy)

                assert blob is not None
                assert len(blob) >= 6  # At least 2 gates

    def test_max_circuits_per_taxonomy(self):
        """Test that max_circuits_per_taxonomy limit is respected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_db"

            config = SkeletonDBConfig(
                map_size=10 * 1024 * 1024,
                max_circuits_per_taxonomy=3,
            )

            with SkeletonDBBuilder(db_path, config) as builder:
                # Create valid unique circuits with distinct wires per gate
                # Using 5 wires to have more valid combinations
                unique_gates = [
                    (2, 0, 3), (2, 3, 0), (2, 0, 4), (2, 4, 0), (2, 3, 4),
                    (3, 0, 2), (3, 2, 0), (3, 0, 4), (3, 4, 0), (3, 2, 4),
                ]
                for t, c1, c2 in unique_gates:
                    circuit = ECA57Circuit(5)
                    circuit.add_gate(0, 1, 2)
                    circuit.add_gate(1, 0, 3)
                    circuit.add_gate(t, c1, c2)
                    builder.add_skeleton(circuit, 5)

                # Get taxonomy
                g1 = (0, 1, 2)
                g2 = (1, 0, 3)
                taxonomy = gate_pair_taxonomy(g1, g2)

                # Should only have max_circuits_per_taxonomy
                circuits = builder.lookup(5, taxonomy)
                assert len(circuits) <= 3

    def test_get_stats(self):
        """Test getting database statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_db"

            config = SkeletonDBConfig(map_size=10 * 1024 * 1024)

            with SkeletonDBBuilder(db_path, config) as builder:
                # Add some circuits
                circuit = ECA57Circuit(4)
                circuit.add_gate(0, 1, 2)
                circuit.add_gate(1, 0, 3)
                builder.add_skeleton(circuit, 4)

                circuit2 = ECA57Circuit(5)
                circuit2.add_gate(0, 1, 2)
                circuit2.add_gate(1, 0, 3)
                builder.add_skeleton(circuit2, 5)

                stats = builder.get_stats()

                assert "taxonomies_per_width" in stats
                assert "circuits_per_width" in stats
                assert 4 in stats["taxonomies_per_width"]
                assert 5 in stats["taxonomies_per_width"]


class TestIntegration:
    """Integration tests for skeleton database with synthesis."""

    def test_synthesize_and_add(self):
        """Test synthesizing and adding a skeleton chain."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_db"

            config = SkeletonDBConfig(
                map_size=10 * 1024 * 1024,
                max_circuits_per_taxonomy=100,
            )

            with SkeletonDBBuilder(db_path, config) as builder:
                # Synthesize and add
                added, taxonomy = builder.synthesize_and_add(
                    wires=4,
                    gates=8,
                    max_variants=10,
                )

                # May or may not succeed depending on SAT solver
                if taxonomy is not None:
                    assert added > 0
                    assert builder.stats["synthesis_calls"] == 1

                    # Verify circuits are in DB
                    circuits = builder.lookup(4, taxonomy)
                    assert len(circuits) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
