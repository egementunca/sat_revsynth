"""SQLite database schema for circuit storage with equivalence classes.

Schema Overview:
    equivalence_classes: Groups of circuits equivalent under unroll operations
    circuits: Individual circuits with reference to their equivalence class
"""
from __future__ import annotations

SCHEMA_SQL = """
-- Equivalence classes group circuits that are equivalent under unroll operations
-- (swaps, rotations, reversals, wire permutations)
CREATE TABLE IF NOT EXISTS equivalence_classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    width INTEGER NOT NULL,
    gate_count INTEGER NOT NULL,
    invariant_hash TEXT NOT NULL,
    class_size INTEGER DEFAULT 1,
    representative_id INTEGER,  -- FK to circuits (set after inserting representative)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Individual circuits with their equivalence class membership
CREATE TABLE IF NOT EXISTS circuits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    equivalence_class_id INTEGER REFERENCES equivalence_classes(id),
    canonical_repr TEXT UNIQUE NOT NULL,  -- JSON representation of gates
    gate_list TEXT NOT NULL,              -- Original gate list as JSON
    width INTEGER NOT NULL,
    gate_count INTEGER NOT NULL,
    is_representative BOOLEAN DEFAULT FALSE,
    truth_table_hash TEXT,                -- Optional: for quick lookup
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_equiv_width_gc ON equivalence_classes(width, gate_count);
CREATE INDEX IF NOT EXISTS idx_equiv_hash ON equivalence_classes(invariant_hash);
CREATE INDEX IF NOT EXISTS idx_circuits_equiv ON circuits(equivalence_class_id);
CREATE INDEX IF NOT EXISTS idx_circuits_width_gc ON circuits(width, gate_count);
"""

FOREIGN_KEY_UPDATE = """
-- Update representative_id after inserting the representative circuit
UPDATE equivalence_classes 
SET representative_id = ? 
WHERE id = ?;
"""


def get_schema() -> str:
    """Return the SQL schema for circuit database."""
    return SCHEMA_SQL
