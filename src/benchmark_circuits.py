#!/usr/bin/env python3
"""Save benchmark circuits with visualizations and skeleton graphs.

Runs benchmark across solvers and saves each found circuit with:
- ASCII circuit representation
- Skeleton graph (gate dependency DAG) as both text and SVG
- JSON circuit data

Usage:
    python3 benchmark_circuits.py --width 7 --gc 17 -o benchmark_output
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple, Dict

from synthesizers.eca57_synthesizer import ECA57Synthesizer
from sat.solver import Solver
from truth_table.truth_table import TruthTable
from gates.eca57 import ECA57Circuit, ECA57Gate


def gates_collide(g1: ECA57Gate, g2: ECA57Gate) -> bool:
    """Check if two ECA57 gates collide (share any common wire).
    
    Per reference: gates collide if they share ANY wire (target, ctrl1, or ctrl2).
    """
    wires1 = {g1.target, g1.ctrl1, g1.ctrl2}
    wires2 = {g2.target, g2.ctrl1, g2.ctrl2}
    return bool(wires1 & wires2)


def build_skeleton_graph(circuit: ECA57Circuit) -> List[Tuple[int, int]]:
    """Build skeleton graph edges per the reference definition.
    
    Edge (g_i, g_j) exists iff:
    1. i < j
    2. g_i and g_j collide (share any wire)
    3. No intermediate gate g_k (i < k < j) collides with BOTH g_i and g_j
    
    This creates the transitive reduction of the collision graph.
    
    Returns:
        List of (source, target) directed edges.
    """
    edges = []
    gates = circuit.gates()
    n = len(gates)
    
    for i in range(n):
        for j in range(i + 1, n):
            if not gates_collide(gates[i], gates[j]):
                continue  # No collision, no edge
            
            # Check if any intermediate gate k collides with both i and j
            blocked = False
            for k in range(i + 1, j):
                if gates_collide(gates[i], gates[k]) and gates_collide(gates[k], gates[j]):
                    blocked = True
                    break
            
            if not blocked:
                edges.append((i, j))
    
    return edges


def skeleton_to_dot(circuit: ECA57Circuit, solver_name: str) -> str:
    """Generate DOT format for skeleton graph visualization."""
    edges = build_skeleton_graph(circuit)
    gates = circuit.gates()
    
    lines = [
        f'digraph "{solver_name}_skeleton" {{',
        '  rankdir=LR;',
        '  node [shape=box, fontsize=10];',
    ]
    
    # Add nodes with gate labels
    for i, g in enumerate(gates):
        label = f"G{i}\\n({g.target},{g.ctrl1},{g.ctrl2})"
        lines.append(f'  {i} [label="{label}"];')
    
    # Add edges
    for src, dst in edges:
        lines.append(f'  {src} -> {dst};')
    
    lines.append('}')
    return '\n'.join(lines)


def skeleton_text_matrix(circuit: ECA57Circuit) -> str:
    """Generate text-based skeleton matrix visualization."""
    edges = build_skeleton_graph(circuit)
    n = len(circuit)
    
    # Build adjacency matrix
    matrix = [[' ' for _ in range(n)] for _ in range(n)]
    for i, j in edges:
        matrix[i][j] = '█'
        matrix[j][i] = '█'
    
    # Format output
    lines = ["Skeleton Matrix (█ = dependency):"]
    
    # Header
    header = "   " + "".join(f"{i%10}" for i in range(n))
    lines.append(header)
    
    for i in range(n):
        row = f"{i:2d} " + "".join(matrix[i])
        lines.append(row)
    
    # Stats
    lines.append(f"\nTotal edges: {len(edges)}")
    lines.append(f"Density: {len(edges) / (n*(n-1)/2):.2%}")
    
    return '\n'.join(lines)


def circuit_to_ascii(circuit: ECA57Circuit) -> str:
    """Generate ASCII art of the circuit."""
    width = circuit.width()
    gates = circuit.gates()
    
    lines = []
    for i, g in enumerate(gates):
        lines.append(f"[{i:2d}] t={g.target} c+={g.ctrl1} c-={g.ctrl2}")
    
    return '\n'.join(lines)


def run_benchmark_with_save(width: int, gate_count: int, output_dir: Path) -> Dict:
    """Run benchmark and save each circuit with visualizations."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    solvers = [
        "cadical153", "cadical103",
        "glucose4", "glucose42", "glucose3",
        "minisat22", "minisat-gh",
        # "lingeling",  # Disabled - too slow
    ]
    
    results = {}
    
    for solver_name in solvers:
        print(f"\n{'='*60}")
        print(f"Testing solver: {solver_name}")
        print('='*60)
        
        try:
            tt = TruthTable(width)
            start = time.time()
            
            synth = ECA57Synthesizer(tt, gate_count, Solver(solver_name))
            circuit = synth.solve()
            
            elapsed = time.time() - start
            
            if circuit is None:
                print(f"  No solution found")
                results[solver_name] = {"time": elapsed, "found": False}
                continue
            
            print(f"  Found circuit in {elapsed:.2f}s")
            print(f"  Is identity: {circuit.is_identity()}")
            
            # Save circuit data
            solver_dir = output_dir / solver_name
            solver_dir.mkdir(exist_ok=True)
            
            # 1. JSON data
            circuit_data = {
                "solver": solver_name,
                "width": width,
                "gate_count": gate_count,
                "time_seconds": elapsed,
                "is_identity": circuit.is_identity(),
                "gates": [g.to_tuple() for g in circuit.gates()]
            }
            with open(solver_dir / "circuit.json", "w") as f:
                json.dump(circuit_data, f, indent=2)
            
            # 2. Circuit ASCII
            with open(solver_dir / "circuit.txt", "w") as f:
                f.write(f"Solver: {solver_name}\n")
                f.write(f"Width: {width}, Gates: {gate_count}\n")
                f.write(f"Time: {elapsed:.4f}s\n")
                f.write(f"Is Identity: {circuit.is_identity()}\n")
                f.write("\n" + str(circuit) + "\n")
            
            # 3. Skeleton graph DOT
            dot_content = skeleton_to_dot(circuit, solver_name)
            with open(solver_dir / "skeleton.dot", "w") as f:
                f.write(dot_content)
            
            # 4. Skeleton matrix text
            matrix_content = skeleton_text_matrix(circuit)
            with open(solver_dir / "skeleton_matrix.txt", "w") as f:
                f.write(f"Solver: {solver_name}\n\n")
                f.write(matrix_content)
            
            # 5. Try to generate SVG if graphviz available
            try:
                import subprocess
                svg_result = subprocess.run(
                    ["dot", "-Tsvg", "-o", str(solver_dir / "skeleton.svg")],
                    input=dot_content,
                    capture_output=True,
                    text=True
                )
                if svg_result.returncode == 0:
                    print(f"  Generated skeleton.svg")
            except FileNotFoundError:
                print(f"  (graphviz not installed, skipping SVG)")
            
            # Store results
            edges = build_skeleton_graph(circuit)
            results[solver_name] = {
                "time": elapsed,
                "found": True,
                "is_identity": circuit.is_identity(),
                "skeleton_edges": len(edges),
                "skeleton_density": len(edges) / (gate_count * (gate_count - 1) / 2)
            }
            
            print(f"  Skeleton: {len(edges)} edges, density {results[solver_name]['skeleton_density']:.2%}")
            print(f"  Saved to {solver_dir}")
            
        except Exception as e:
            print(f"  ERROR: {e}")
            results[solver_name] = {"time": None, "found": False, "error": str(e)}
    
    # Save summary
    summary_path = output_dir / "summary.json"
    with open(summary_path, "w") as f:
        json.dump({
            "width": width,
            "gate_count": gate_count,
            "results": results
        }, f, indent=2)
    
    # Print summary table
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"{'Solver':<15} {'Time (s)':<12} {'Identity':<10} {'Edges':<8} {'Density':<10}")
    print("-"*60)
    
    sorted_results = sorted(
        [(s, r) for s, r in results.items() if r.get("found")],
        key=lambda x: x[1]["time"]
    )
    
    for solver, r in sorted_results:
        print(f"{solver:<15} {r['time']:<12.4f} {'✓' if r.get('is_identity') else '✗':<10} {r.get('skeleton_edges', 'N/A'):<8} {r.get('skeleton_density', 0)*100:.1f}%")
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Benchmark and save circuits with skeleton graphs")
    parser.add_argument("--width", type=int, default=7, help="Circuit width")
    parser.add_argument("--gc", type=int, default=17, help="Gate count")
    parser.add_argument("-o", "--output", default="benchmark_output", help="Output directory")
    
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    run_benchmark_with_save(args.width, args.gc, output_dir)


if __name__ == "__main__":
    main()
