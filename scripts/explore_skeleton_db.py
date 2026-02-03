#!/usr/bin/env python3
"""
Skeleton Identity Database Explorer

Explores the ids_n* databases in local_mixing/db that contain
fully noncommuting identity circuits (skeleton chains).

Usage:
    python scripts/explore_skeleton_db.py --list
    python scripts/explore_skeleton_db.py --stats
    python scripts/explore_skeleton_db.py --db ids_n5 --taxonomy OnCtrl1,OnActive,OnActive
    python scripts/explore_skeleton_db.py --db ids_n5 --show-circuits 5
    python scripts/explore_skeleton_db.py --verify
"""

import argparse
import lmdb
import struct
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from collections import defaultdict

# Default path to local_mixing db
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "local_mixing" / "db"

# Collision type enum (matches Rust bincode)
COLLISION_TYPES = {
    0: 'OnActive',
    1: 'OnCtrl1',
    2: 'OnCtrl2',
    3: 'OnNew'
}

COLLISION_TO_INT = {v: k for k, v in COLLISION_TYPES.items()}


def decode_taxonomy(key_bytes: bytes) -> Tuple[str, str, str]:
    """Decode GatePair taxonomy from bincode key."""
    if len(key_bytes) >= 3:
        a, c1, c2 = key_bytes[0], key_bytes[1], key_bytes[2]
        return (
            COLLISION_TYPES.get(a, f'Unknown({a})'),
            COLLISION_TYPES.get(c1, f'Unknown({c1})'),
            COLLISION_TYPES.get(c2, f'Unknown({c2})')
        )
    return ('?', '?', '?')


def encode_taxonomy(taxonomy: Tuple[str, str, str]) -> bytes:
    """Encode taxonomy tuple to bincode key."""
    return bytes([
        COLLISION_TO_INT.get(taxonomy[0], 3),
        COLLISION_TO_INT.get(taxonomy[1], 3),
        COLLISION_TO_INT.get(taxonomy[2], 3)
    ])


def decode_circuits(val_bytes: bytes) -> List[List[Tuple[int, int, int]]]:
    """Decode bincode Vec<Vec<u8>> to list of circuits."""
    if len(val_bytes) < 8:
        return []

    num_circuits = struct.unpack('<Q', val_bytes[:8])[0]
    circuits = []
    offset = 8

    for _ in range(num_circuits):
        if offset + 8 > len(val_bytes):
            break
        blob_len = struct.unpack('<Q', val_bytes[offset:offset+8])[0]
        offset += 8
        if offset + blob_len > len(val_bytes):
            break

        blob = val_bytes[offset:offset+blob_len]
        gates = [(blob[i], blob[i+1], blob[i+2]) for i in range(0, len(blob), 3)]
        circuits.append(gates)
        offset += blob_len

    return circuits


def gates_collide(g1: Tuple[int, int, int], g2: Tuple[int, int, int]) -> bool:
    """Check if two gates collide (don't commute)."""
    t1, c1a, c1b = g1
    t2, c2a, c2b = g2
    # g1's target on g2's controls?
    if t1 == c2a or t1 == c2b:
        return True
    # g2's target on g1's controls?
    if t2 == c1a or t2 == c1b:
        return True
    return False


def all_adjacent_collide(circuit: List[Tuple[int, int, int]]) -> bool:
    """Check if all adjacent gate pairs collide."""
    for i in range(len(circuit) - 1):
        if not gates_collide(circuit[i], circuit[i+1]):
            return False
    return True


def format_circuit(circuit: List[Tuple[int, int, int]], max_gates: int = 10) -> str:
    """Format circuit for display."""
    if len(circuit) <= max_gates:
        return ' -> '.join(f'({t},{c1},{c2})' for t, c1, c2 in circuit)
    else:
        head = ' -> '.join(f'({t},{c1},{c2})' for t, c1, c2 in circuit[:3])
        tail = ' -> '.join(f'({t},{c1},{c2})' for t, c1, c2 in circuit[-2:])
        return f'{head} -> ... -> {tail} [{len(circuit)} gates]'


class SkeletonDBExplorer:
    """Explorer for skeleton identity databases."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.env = None
        self.db_names = ['ids_n3', 'ids_n4', 'ids_n5', 'ids_n6', 'ids_n7']

    def __enter__(self):
        self.env = lmdb.open(str(self.db_path), max_dbs=60, readonly=True)
        return self

    def __exit__(self, *args):
        if self.env:
            self.env.close()

    def list_databases(self) -> Dict[str, int]:
        """List available skeleton databases and their entry counts."""
        results = {}
        for db_name in self.db_names:
            try:
                db = self.env.open_db(db_name.encode())
                with self.env.begin(db=db) as txn:
                    results[db_name] = txn.stat()['entries']
            except:
                results[db_name] = -1  # Not found
        return results

    def get_stats(self, db_name: str) -> Dict:
        """Get detailed stats for a database."""
        try:
            db = self.env.open_db(db_name.encode())
        except:
            return {'error': f'Database {db_name} not found'}

        stats = {
            'db_name': db_name,
            'taxonomies': [],
            'total_circuits': 0,
            'circuit_sizes': defaultdict(int),
            'all_fully_noncommuting': True
        }

        with self.env.begin(db=db) as txn:
            cursor = txn.cursor()
            for key, val in cursor:
                taxonomy = decode_taxonomy(key)
                circuits = decode_circuits(val)

                tax_stats = {
                    'taxonomy': taxonomy,
                    'count': len(circuits),
                    'sizes': {}
                }

                for circuit in circuits:
                    size = len(circuit)
                    stats['circuit_sizes'][size] = stats['circuit_sizes'].get(size, 0) + 1
                    tax_stats['sizes'][size] = tax_stats['sizes'].get(size, 0) + 1

                    if not all_adjacent_collide(circuit):
                        stats['all_fully_noncommuting'] = False

                stats['total_circuits'] += len(circuits)
                stats['taxonomies'].append(tax_stats)

        return stats

    def get_circuits(self, db_name: str, taxonomy: Optional[Tuple[str, str, str]] = None,
                     limit: int = 10) -> List[Dict]:
        """Get circuits from a database, optionally filtered by taxonomy."""
        try:
            db = self.env.open_db(db_name.encode())
        except:
            return []

        results = []
        with self.env.begin(db=db) as txn:
            if taxonomy:
                # Lookup specific taxonomy
                key = encode_taxonomy(taxonomy)
                val = txn.get(key, db=db)
                if val:
                    circuits = decode_circuits(val)
                    for i, circuit in enumerate(circuits[:limit]):
                        results.append({
                            'taxonomy': taxonomy,
                            'index': i,
                            'gates': len(circuit),
                            'circuit': circuit,
                            'fully_noncommuting': all_adjacent_collide(circuit)
                        })
            else:
                # Iterate all taxonomies
                cursor = txn.cursor()
                count = 0
                for key, val in cursor:
                    if count >= limit:
                        break
                    tax = decode_taxonomy(key)
                    circuits = decode_circuits(val)
                    for i, circuit in enumerate(circuits[:max(1, limit // 5)]):
                        if count >= limit:
                            break
                        results.append({
                            'taxonomy': tax,
                            'index': i,
                            'gates': len(circuit),
                            'circuit': circuit,
                            'fully_noncommuting': all_adjacent_collide(circuit)
                        })
                        count += 1

        return results

    def verify_all(self) -> Dict:
        """Verify all databases contain fully noncommuting circuits."""
        results = {}
        for db_name in self.db_names:
            stats = self.get_stats(db_name)
            if 'error' in stats:
                results[db_name] = {'status': 'not_found'}
            else:
                results[db_name] = {
                    'status': 'ok' if stats['all_fully_noncommuting'] else 'has_commuting',
                    'total_circuits': stats['total_circuits'],
                    'taxonomies': len(stats['taxonomies'])
                }
        return results


def main():
    parser = argparse.ArgumentParser(description='Skeleton Identity Database Explorer')
    parser.add_argument('--db-path', type=Path, default=DEFAULT_DB_PATH,
                       help='Path to LMDB database directory')
    parser.add_argument('--list', action='store_true',
                       help='List available databases')
    parser.add_argument('--stats', action='store_true',
                       help='Show detailed stats for all databases')
    parser.add_argument('--db', type=str,
                       help='Specific database to explore (e.g., ids_n5)')
    parser.add_argument('--taxonomy', type=str,
                       help='Filter by taxonomy (e.g., OnCtrl1,OnActive,OnActive)')
    parser.add_argument('--show-circuits', type=int, default=0,
                       help='Show N sample circuits')
    parser.add_argument('--verify', action='store_true',
                       help='Verify all circuits are fully noncommuting')

    args = parser.parse_args()

    with SkeletonDBExplorer(args.db_path) as explorer:
        if args.list:
            print("\n=== Skeleton Identity Databases ===\n")
            dbs = explorer.list_databases()
            for name, count in dbs.items():
                if count >= 0:
                    print(f"  {name}: {count} taxonomies")
                else:
                    print(f"  {name}: not found")
            print()

        elif args.verify:
            print("\n=== Verification Results ===\n")
            results = explorer.verify_all()
            for db_name, info in results.items():
                status = info['status']
                if status == 'ok':
                    print(f"  {db_name}: OK ({info['total_circuits']} circuits, {info['taxonomies']} taxonomies)")
                elif status == 'has_commuting':
                    print(f"  {db_name}: WARNING - contains commuting pairs!")
                else:
                    print(f"  {db_name}: not found")
            print()

        elif args.stats:
            print("\n=== Database Statistics ===\n")
            for db_name in explorer.db_names:
                stats = explorer.get_stats(db_name)
                if 'error' in stats:
                    print(f"--- {db_name}: {stats['error']} ---\n")
                    continue

                print(f"--- {db_name} ---")
                print(f"  Total circuits: {stats['total_circuits']}")
                print(f"  Taxonomies: {len(stats['taxonomies'])}")
                print(f"  All fully noncommuting: {stats['all_fully_noncommuting']}")
                print(f"  Circuit sizes: {dict(stats['circuit_sizes'])}")
                print(f"  Taxonomies:")
                for tax in stats['taxonomies']:
                    print(f"    {tax['taxonomy']}: {tax['count']} circuits, sizes={tax['sizes']}")
                print()

        elif args.db:
            taxonomy = None
            if args.taxonomy:
                parts = args.taxonomy.split(',')
                if len(parts) == 3:
                    taxonomy = tuple(parts)

            if args.show_circuits > 0:
                print(f"\n=== Circuits from {args.db} ===\n")
                circuits = explorer.get_circuits(args.db, taxonomy, args.show_circuits)
                for c in circuits:
                    print(f"Taxonomy: {c['taxonomy']}")
                    print(f"  Index: {c['index']}, Gates: {c['gates']}")
                    print(f"  Fully noncommuting: {c['fully_noncommuting']}")
                    print(f"  Circuit: {format_circuit(c['circuit'])}")
                    print()
            else:
                stats = explorer.get_stats(args.db)
                if 'error' in stats:
                    print(f"Error: {stats['error']}")
                else:
                    print(f"\n=== {args.db} Statistics ===\n")
                    print(f"Total circuits: {stats['total_circuits']}")
                    print(f"Taxonomies: {len(stats['taxonomies'])}")
                    for tax in stats['taxonomies']:
                        print(f"  {tax['taxonomy']}: {tax['count']} circuits")

        else:
            parser.print_help()


if __name__ == '__main__':
    main()
