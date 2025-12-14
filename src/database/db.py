"""Circuit database with equivalence class support.

Provides a high-level API for storing, querying, and managing circuits
with automatic equivalence class computation.
"""
from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Iterator

from database.schema import SCHEMA_SQL
from database.equivalence import (
    get_invariants,
    invariants_hash,
    circuit_to_tuple,
    compute_equivalence_class,
    select_representative,
    canonical_repr,
)

if TYPE_CHECKING:
    from circuit.circuit import Circuit


class CircuitDatabase:
    """SQLite-backed database for circuits with equivalence class tracking.
    
    Example:
        >>> db = CircuitDatabase("circuits.db")
        >>> db.add_circuit(my_circuit)
        >>> results = db.query_by_width_gates(width=3, gate_count=4)
    """
    
    def __init__(self, db_path: str | Path = ":memory:"):
        """Initialize database connection and create schema.
        
        Args:
            db_path: Path to SQLite database file. Use ":memory:" for in-memory.
        """
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
    
    def _init_schema(self):
        """Create database tables if they don't exist."""
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()
    
    def close(self):
        """Close database connection."""
        self.conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def add_circuit(
        self, 
        circuit: "Circuit", 
        compute_class: bool = True
    ) -> tuple[int, int]:
        """Add a circuit to the database.
        
        Args:
            circuit: The circuit to add.
            compute_class: If True, compute equivalence class and representative.
                          If False, just add the circuit with a new equivalence class.
        
        Returns:
            Tuple of (circuit_id, equivalence_class_id).
        """
        # Get canonical representation
        canon_str = canonical_repr(circuit)
        
        # Check if circuit already exists
        existing = self.conn.execute(
            "SELECT id, equivalence_class_id FROM circuits WHERE canonical_repr = ?",
            (canon_str,)
        ).fetchone()
        
        if existing:
            return (existing["id"], existing["equivalence_class_id"])
        
        # Get circuit properties
        width = circuit.width()
        gate_count = len(circuit)
        gate_list_json = json.dumps(circuit_to_tuple(circuit))
        inv_hash = invariants_hash(circuit)
        
        # Find or create equivalence class
        cursor = self.conn.cursor()
        
        if compute_class:
            # Check for existing class with same invariants
            equiv_class_row = cursor.execute(
                """SELECT id FROM equivalence_classes 
                   WHERE invariant_hash = ? AND width = ? AND gate_count = ?""",
                (inv_hash, width, gate_count)
            ).fetchone()
            
            if equiv_class_row:
                equiv_class_id = equiv_class_row["id"]
                # Increment class size
                cursor.execute(
                    "UPDATE equivalence_classes SET class_size = class_size + 1 WHERE id = ?",
                    (equiv_class_id,)
                )
            else:
                # Create new equivalence class
                cursor.execute(
                    """INSERT INTO equivalence_classes 
                       (width, gate_count, invariant_hash, class_size)
                       VALUES (?, ?, ?, 1)""",
                    (width, gate_count, inv_hash)
                )
                equiv_class_id = cursor.lastrowid
        else:
            # Create new equivalence class for this circuit
            cursor.execute(
                """INSERT INTO equivalence_classes 
                   (width, gate_count, invariant_hash, class_size)
                   VALUES (?, ?, ?, 1)""",
                (width, gate_count, inv_hash)
            )
            equiv_class_id = cursor.lastrowid
        
        # Insert circuit
        cursor.execute(
            """INSERT INTO circuits 
               (equivalence_class_id, canonical_repr, gate_list, width, gate_count)
               VALUES (?, ?, ?, ?, ?)""",
            (equiv_class_id, canon_str, gate_list_json, width, gate_count)
        )
        circuit_id = cursor.lastrowid
        
        # Set as representative if this is first circuit in class
        existing_rep = cursor.execute(
            "SELECT representative_id FROM equivalence_classes WHERE id = ?",
            (equiv_class_id,)
        ).fetchone()
        
        if existing_rep and existing_rep["representative_id"] is None:
            cursor.execute(
                """UPDATE equivalence_classes SET representative_id = ? WHERE id = ?""",
                (circuit_id, equiv_class_id)
            )
            cursor.execute(
                "UPDATE circuits SET is_representative = TRUE WHERE id = ?",
                (circuit_id,)
            )
        
        self.conn.commit()
        return (circuit_id, equiv_class_id)
    
    def add_circuits_batch(
        self, 
        circuits: list["Circuit"],
        compute_class: bool = True
    ) -> list[tuple[int, int]]:
        """Add multiple circuits efficiently.
        
        Args:
            circuits: List of circuits to add.
            compute_class: Whether to compute equivalence classes.
            
        Returns:
            List of (circuit_id, equivalence_class_id) tuples.
        """
        results = []
        for circuit in circuits:
            results.append(self.add_circuit(circuit, compute_class))
        return results
    
    def get_circuit_by_id(self, circuit_id: int) -> Optional[dict]:
        """Get circuit record by ID."""
        row = self.conn.execute(
            "SELECT * FROM circuits WHERE id = ?",
            (circuit_id,)
        ).fetchone()
        return dict(row) if row else None
    
    def get_representative(self, equiv_class_id: int) -> Optional[dict]:
        """Get the representative circuit for an equivalence class."""
        row = self.conn.execute(
            """SELECT c.* FROM circuits c
               JOIN equivalence_classes ec ON c.id = ec.representative_id
               WHERE ec.id = ?""",
            (equiv_class_id,)
        ).fetchone()
        return dict(row) if row else None
    
    def query_by_width_gates(
        self, 
        width: int, 
        gate_count: int
    ) -> list[dict]:
        """Query all circuits with given width and gate count."""
        rows = self.conn.execute(
            "SELECT * FROM circuits WHERE width = ? AND gate_count = ?",
            (width, gate_count)
        ).fetchall()
        return [dict(row) for row in rows]
    
    def query_representatives(
        self, 
        width: Optional[int] = None, 
        gate_count: Optional[int] = None
    ) -> list[dict]:
        """Query representative circuits only.
        
        Args:
            width: Optional filter by width.
            gate_count: Optional filter by gate count.
            
        Returns:
            List of representative circuit records.
        """
        query = "SELECT * FROM circuits WHERE is_representative = TRUE"
        params = []
        
        if width is not None:
            query += " AND width = ?"
            params.append(width)
        if gate_count is not None:
            query += " AND gate_count = ?"
            params.append(gate_count)
        
        rows = self.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
    
    def get_equivalence_class_stats(self) -> list[dict]:
        """Get statistics about equivalence classes grouped by (width, gate_count)."""
        rows = self.conn.execute(
            """SELECT width, gate_count, 
                      COUNT(*) as num_classes,
                      SUM(class_size) as total_circuits
               FROM equivalence_classes
               GROUP BY width, gate_count
               ORDER BY width, gate_count"""
        ).fetchall()
        return [dict(row) for row in rows]
    
    def count_circuits(
        self, 
        width: Optional[int] = None, 
        gate_count: Optional[int] = None
    ) -> int:
        """Count circuits matching optional filters."""
        query = "SELECT COUNT(*) FROM circuits WHERE 1=1"
        params = []
        
        if width is not None:
            query += " AND width = ?"
            params.append(width)
        if gate_count is not None:
            query += " AND gate_count = ?"
            params.append(gate_count)
        
        return self.conn.execute(query, params).fetchone()[0]
    
    def count_equivalence_classes(
        self, 
        width: Optional[int] = None, 
        gate_count: Optional[int] = None
    ) -> int:
        """Count equivalence classes matching optional filters."""
        query = "SELECT COUNT(*) FROM equivalence_classes WHERE 1=1"
        params = []
        
        if width is not None:
            query += " AND width = ?"
            params.append(width)
        if gate_count is not None:
            query += " AND gate_count = ?"
            params.append(gate_count)
        
        return self.conn.execute(query, params).fetchone()[0]
