"""Solver Racer: Run multiple SAT solvers in parallel and take the first result.

Reduces tail latency by racing different heuristics/solvers against each other.
"""
import multiprocessing
import queue
import time
from typing import List, Tuple, Optional, Any

from sat.cnf import CNF, Solution
from sat.solver import Solver



class SimpleCNF:
    """A pickleable minimal CNF wrapper for the worker process."""
    def __init__(self, clauses: List[List[int]], nv: int):
        self._clauses = clauses
        self._nv = nv
        
        # Mock internal structure expected by Solver
        class Inner:
            pass
        self._cnf = Inner()
        self._cnf.clauses = clauses
        self._cnf.nv = nv
        
    def clauses(self) -> List[List[int]]:
        return self._clauses


def solve_worker(solver_name: str, clauses: List[List[int]], nv: int, out_queue: multiprocessing.Queue):
    """Worker process to run a single solver."""
    try:
        # Reconstruct a minimal CNF object
        cnf = SimpleCNF(clauses, nv)
        
        # Re-instantiate solver in process to be safe
        solver = Solver(solver_name)
        result = solver.solve(cnf)
        out_queue.put((solver_name, result))
    except Exception as e:
        out_queue.put((solver_name, e))


class SolverRacer:
    """Races multiple SAT solvers in parallel."""
    
    def __init__(self, solver_names: List[str]):
        self.solver_names = solver_names
        
    def solve(self, cnf: CNF) -> Solution:
        """Race solvers on the given CNF.
        
        Returns:
            The first (sat, model) result obtained.
        """
        # If only one solver, run directly (avoid overhead)
        if len(self.solver_names) == 1:
            return Solver(self.solver_names[0]).solve(cnf)
        
        # Extract raw data for pickling (CNF contains unpickleable lambdas)
        clauses = cnf.clauses()
        nv = cnf._cnf.nv
        
        # Setup multiprocessing
        result_queue = multiprocessing.Queue()
        processes = []
        
        for name in self.solver_names:
            p = multiprocessing.Process(
                target=solve_worker,
                args=(name, clauses, nv, result_queue),
                name=f"SolverRacer-{name}"
            )

            processes.append(p)
            p.start()
            
        final_result = (False, [])
        finished_count = 0
        
        try:
            while finished_count < len(self.solver_names):
                try:
                    # Wait for next result
                    solver_name, res = result_queue.get(timeout=None)
                    finished_count += 1
                    
                    if isinstance(res, Exception):
                        # print(f"Solver {solver_name} failed: {res}")
                        continue
                        
                    sat, model = res
                    
                    # If SAT, we have a winner!
                    if sat:
                        final_result = (True, model)
                        break
                    
                    # If UNSAT, we continue unless all are UNSAT
                    # (Assuming all solvers are correct, first UNSAT is enough,
                    # but typically we terminate on first result anyway)
                    final_result = (False, [])
                    break
                    
                except queue.Empty:
                    continue
                    
        finally:
            # Terminate all processes
            for p in processes:
                if p.is_alive():
                    p.terminate()
            
            # Join them to clean up zombies
            for p in processes:
                p.join(timeout=0.1)
                
        return final_result
