#!/usr/bin/env python3
"""Collect and aggregate results from completed cluster jobs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Any
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def load_results(results_dir: Path) -> List[Dict[str, Any]]:
    """Load all JSON result files from directory."""
    results = []
    for json_file in results_dir.glob("*.json"):
        try:
            with open(json_file) as f:
                data = json.load(f)
                data["_file"] = str(json_file)
                results.append(data)
        except Exception as e:
            print(f"Warning: Could not load {json_file}: {e}")
    return results


def summarize_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate summary statistics from results."""
    summary = {
        "total_jobs": len(results),
        "total_circuits": sum(r.get("num_circuits", 0) for r in results),
        "total_time_seconds": sum(r.get("elapsed_seconds", 0) for r in results),
        "by_width_gates": {},
    }
    
    for r in results:
        key = f"w{r.get('width', '?')}_g{r.get('gates', '?')}"
        gate_set = r.get("gate_set", "mct")
        full_key = f"{gate_set}_{key}"
        
        if full_key not in summary["by_width_gates"]:
            summary["by_width_gates"][full_key] = {
                "width": r.get("width"),
                "gates": r.get("gates"),
                "gate_set": gate_set,
                "num_circuits": 0,
                "elapsed_seconds": 0,
                "jobs": 0,
            }
        
        entry = summary["by_width_gates"][full_key]
        entry["num_circuits"] += r.get("num_circuits", 0)
        entry["elapsed_seconds"] += r.get("elapsed_seconds", 0)
        entry["jobs"] += 1
    
    return summary


def populate_database(results: List[Dict[str, Any]], db_path: str) -> int:
    """Populate database with circuits from results.
    
    Returns:
        Number of circuits added.
    """
    from database.db import CircuitDatabase
    from circuit.circuit import Circuit
    
    count = 0
    with CircuitDatabase(db_path) as db:
        for r in results:
            width = r.get("width", 3)
            circuits_data = r.get("circuits", [])
            gate_set = r.get("gate_set", "mct")
            
            if gate_set != "mct":
                print(f"Skipping ECA57 circuits (not yet supported in database)")
                continue
            
            for gate_list in circuits_data:
                circ = Circuit(width)
                for controls, target in gate_list:
                    circ.mcx(controls, target)
                db.add_circuit(circ, compute_class=True)
                count += 1
    
    return count


def main():
    parser = argparse.ArgumentParser(description="Collect and process cluster job results")
    parser.add_argument("results_dir", type=str, help="Directory containing result JSON files")
    parser.add_argument("--summary", action="store_true", help="Print summary statistics")
    parser.add_argument("--populate-db", type=str, metavar="DB_PATH",
                       help="Populate SQLite database with circuits")
    parser.add_argument("--output", type=str, help="Write aggregated results to JSON file")
    
    args = parser.parse_args()
    
    results_dir = Path(args.results_dir)
    if not results_dir.exists():
        print(f"Error: Directory not found: {results_dir}")
        return 1
    
    print(f"Loading results from: {results_dir}")
    results = load_results(results_dir)
    print(f"Loaded {len(results)} result files")
    
    if args.summary or not (args.populate_db or args.output):
        summary = summarize_results(results)
        print("\n=== Summary ===")
        print(f"Total jobs: {summary['total_jobs']}")
        print(f"Total circuits: {summary['total_circuits']}")
        print(f"Total time: {summary['total_time_seconds']:.2f}s")
        print("\nBy width/gates:")
        for key, data in sorted(summary["by_width_gates"].items()):
            print(f"  {key}: {data['num_circuits']} circuits in {data['elapsed_seconds']:.2f}s")
    
    if args.output:
        with open(args.output, "w") as f:
            json.dump({"results": results, "summary": summarize_results(results)}, f, indent=2)
        print(f"\nAggregated results saved to: {args.output}")
    
    if args.populate_db:
        print(f"\nPopulating database: {args.populate_db}")
        count = populate_database(results, args.populate_db)
        print(f"Added {count} circuits to database")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
