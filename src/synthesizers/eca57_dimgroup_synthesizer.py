"""ECA57 DimGroup and Collection Synthesizers.

Exhaustive synthesis of ECA57 identity circuits using the unroll-exclude pattern:
1. Find one identity circuit via SAT
2. Unroll it to get all equivalent circuits
3. Exclude all equivalents from the solver
4. Repeat until UNSAT
"""
from __future__ import annotations

import time
from typing import Optional, List, Callable, Union

from sat.solver import Solver
from sat.solver_racer import SolverRacer
from synthesizers.eca57_synthesizer import ECA57Synthesizer
from truth_table.truth_table import TruthTable
from gates.eca57 import ECA57Circuit
from circuit.eca57_dim_group import ECA57DimGroup
from circuit.eca57_collection import ECA57Collection


class ECA57PartialSynthesizer:
    """Single-shot synthesizer for one batch of equivalent circuits.
    
    Creates a new ECA57Synthesizer instance, applies exclusions for
    previously found circuits, and finds the next identity circuit.
    """
    
    def __init__(self, width: int, gate_count: int, solver_name: Union[str, List[str]] = "glucose4"):
        """Initialize synthesizer for given dimensions.
        
        Args:
            width: Number of wires.
            gate_count: Number of gates.
            solver_name: Name of SAT solver(s) to use.
        """
        self._width = width
        self._gate_count = gate_count
        self._solver_name = solver_name
        
        # Identity truth table
        tt = TruthTable(width)
        
        # Instantiate solver or racer
        if isinstance(solver_name, list):
            solver_instance = SolverRacer(solver_name)
        else:
            solver_instance = Solver(solver_name)
        
        self._synthesizer = ECA57Synthesizer(
            tt, 
            gate_count, 
            solver=solver_instance,
            disable_empty_lines=True
        )
    
    def synthesize(self) -> ECA57DimGroup:
        """Find one circuit and unroll to equivalence class.
        
        Returns:
            DimGroup containing all equivalent circuits, or empty if UNSAT.
        """
        circuit = self._synthesizer.solve()
        dg = ECA57DimGroup(self._width, self._gate_count)
        
        if circuit is not None:
            # Unroll to get all equivalents
            equivalents = circuit.unroll()
            dg.extend(equivalents)
        
        return dg
    
    def exclude_subcircuit(self, circuit: ECA57Circuit) -> "ECA57PartialSynthesizer":
        """Exclude a circuit from future solutions.
        
        Args:
            circuit: Circuit to exclude.
            
        Returns:
            Self for chaining.
        """
        self._synthesizer.exclude_subcircuit(circuit)
        return self


class ECA57DimGroupSynthesizer:
    """Exhaustive synthesizer for all identity circuits of a given dimension.
    
    Implements the unroll-exclude loop:
    1. Create a fresh synthesizer
    2. Exclude all previously found circuits
    3. Find next circuit and unroll it
    4. Add all equivalents to results
    5. Repeat until UNSAT
    """
    
    def __init__(self, width: int, gate_count: int, solver_name: Union[str, List[str]] = "glucose4"):
        """Initialize synthesizer.
        
        Args:
            width: Number of wires (must be >= 3 for ECA57).
            gate_count: Number of gates.
            solver_name: SAT solver(s) to use.
        """
        assert width >= 3, "ECA57 requires at least 3 wires"
        self._width = width
        self._gate_count = gate_count
        self._solver_name = solver_name
    
    def synthesize(
        self, 
        progress_callback: Optional[Callable[[int, int, float], None]] = None
    ) -> ECA57DimGroup:
        """Find all identity circuits for this dimension.
        
        Args:
            progress_callback: Optional callback(iteration, circuits_found, elapsed_seconds).
            
        Returns:
            DimGroup containing all found circuits.
        """
        dg = ECA57DimGroup(self._width, self._gate_count)
        iteration = 0
        start_time = time.time()
        
        while True:
            iteration += 1
            
            # Create fresh synthesizer
            ps = ECA57PartialSynthesizer(
                self._width, 
                self._gate_count, 
                self._solver_name
            )
            
            # Exclude all previously found circuits
            for circuit in dg:
                ps.exclude_subcircuit(circuit)
            
            # Find next batch
            partial_dg = ps.synthesize()
            
            if partial_dg:
                dg.join(partial_dg)
                
                if progress_callback:
                    elapsed = time.time() - start_time
                    progress_callback(iteration, len(dg), elapsed)
            else:
                # UNSAT - no more circuits
                break
        
        return dg


class ECA57CollectionSynthesizer:
    """Synthesizer for complete collections of ECA57 identity circuits.
    
    Iterates over all (width, gate_count) combinations up to specified limits.
    """
    
    def __init__(self, max_width: int, max_gate_count: int, solver_name: str = "glucose4"):
        """Initialize collection synthesizer.
        
        Args:
            max_width: Maximum number of wires.
            max_gate_count: Maximum number of gates.
            solver_name: SAT solver to use.
        """
        assert max_width >= 3, "ECA57 requires at least 3 wires"
        self._max_width = max_width
        self._max_gate_count = max_gate_count
        self._solver_name = solver_name
    
    def synthesize(
        self,
        progress_callback: Optional[Callable[[int, int, int, int, float], None]] = None,
        save_path: Optional[str] = None
    ) -> ECA57Collection:
        """Synthesize complete collection.
        
        Args:
            progress_callback: Optional callback(width, gc, circuits_in_group, total, elapsed).
            save_path: If provided, save collection to this path after each dimension.
            
        Returns:
            Complete collection of identity circuits.
        """
        from pathlib import Path
        
        collection = ECA57Collection(self._max_width, self._max_gate_count)
        start_time = time.time()
        total_circuits = 0
        
        for width in range(3, self._max_width + 1):
            for gc in range(2, self._max_gate_count + 1):
                # Synthesize this dimension
                dgs = ECA57DimGroupSynthesizer(width, gc, self._solver_name)
                dimgroup = dgs.synthesize()
                
                collection[width][gc] = dimgroup
                total_circuits += len(dimgroup)
                
                if progress_callback:
                    elapsed = time.time() - start_time
                    progress_callback(width, gc, len(dimgroup), total_circuits, elapsed)
                
                # Save checkpoint if requested
                if save_path:
                    collection.save_json(Path(save_path))
        
        return collection


def benchmark_solvers(width: int = 5, gate_count: int = 5) -> dict:
    """Benchmark different SAT solvers for ECA57 synthesis.
    
    Args:
        width: Test circuit width.
        gate_count: Test gate count.
        
    Returns:
        Dictionary mapping solver name to timing results.
    """
    results = {}
    
    # Use all available solvers
    solvers_to_test = Solver.available_solvers
    print(f"Benchmarking {len(solvers_to_test)} solvers on W={width} GC={gate_count}...")
    
    for solver_name in solvers_to_test:
        print(f"  > {solver_name:<15}", end="", flush=True)
        try:
            tt = TruthTable(width)
            start = time.time()
            
            synth = ECA57Synthesizer(tt, gate_count, Solver(solver_name))
            circuit = synth.solve()
            
            elapsed = time.time() - start
            found = circuit is not None
            status = "FOUND" if found else "UNSAT"
            print(f" : {status} in {elapsed:.4f}s")
            
            results[solver_name] = {
                "time": elapsed,
                "found": found,
                "error": None
            }
        except Exception as e:
            print(f" : ERROR ({e})")
            results[solver_name] = {
                "time": None,
                "found": False,
                "error": str(e)
            }
    
    # Print summary sorted by time
    print("\n" + "="*40)
    print(f"RESULTS (W={width} GC={gate_count})")
    print("="*40)
    
    valid_results = [
        (k, v) for k, v in results.items() 
        if v["found"] and v["time"] is not None
    ]
    valid_results.sort(key=lambda x: x[1]["time"])
    
    for rank, (name, stats) in enumerate(valid_results, 1):
        print(f"{rank:2d}. {name:<15} : {stats['time']:.4f}s")
        
    return results
