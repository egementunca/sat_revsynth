"""SAT Solver Interface for Circuit Synthesis.

This module provides a unified interface to multiple SAT solvers, supporting both
builtin solvers (via python-sat) and external command-line solvers.

Supported Solvers:
    Builtin (python-sat): cadical103/153, glucose3/4/42, lingeling, 
        maplechrono, maplecm, maplesat, mergesat3, minisat22, minisat-gh,
        minicard, gluecard3/4
    
    External: kissat, kissat-sc2024, cadical (2.0), sbva-cadical

Example:
    >>> from sat.solver import Solver
    >>> from sat.cnf import CNF
    >>> solver = Solver("glucose4")
    >>> sat, model = solver.solve(cnf)
"""
from pysat.solvers import Solver as PySolver
from subprocess import Popen, PIPE
from sat.cnf import CNF, Solution

import threading
import queue


class Solver:
    """Unified SAT solver interface.
    
    Provides a common solve() method for both python-sat builtin solvers
    and external command-line SAT solvers.
    
    Args:
        name: Solver name (must be in available_solvers).
        args: Optional additional command-line arguments for external solvers.
    
    Attributes:
        external_solvers: Dict of external solver names to default arguments.
        builtin_solvers: List of python-sat solver names.
        available_solvers: Combined list of all supported solvers.
    
    Example:
        >>> solver = Solver("kissat")
        >>> sat, literals = solver.solve(cnf)
    """
    external_solvers = {
        "kissat": ["-q"],
        "kissat-sc2024": ["-q"],
        "cadical": ["--quiet"],
        # "cms":["--verb", "0"],
        # "parkissat": ["-v=1", "-c=8", "-max-memory=8"]
    }

    builtin_solvers = [
        "cadical103",
        "cadical153",
        "gluecard3",
        "gluecard4",
        "glucose3",
        "glucose4",
        "glucose42",
        "lingeling",
        "maplechrono",
        "maplecm",
        "maplesat",
        "mergesat3",
        "minicard",
        "minisat22",
        "minisat-gh",
    ]

    available_solvers = list(external_solvers.keys()) + builtin_solvers

    def __init__(self, name: str, args=None):
        if name not in Solver.available_solvers:
            raise ValueError(f"Solver {name} not supported")
        self.__name = name
        self.__args = args

    def solve(self, cnf: CNF) -> Solution:
        """Run the SAT solver on the given CNF formula.
        
        Args:
            cnf: The formula in CNF format.
            
        Returns:
            Solution tuple: (satisfiable: bool, literals: list[int]).
            If unsatisfiable, literals is empty.
        """
        if self.__name in self.builtin_solvers:
            solution = self._solve_builtin(cnf)
        elif self.__name in self.external_solvers:
            solution = self._solve_external(cnf)
        else:
            raise ValueError(f"Solver {self.__name} not supported")
        return solution

    def _solve_builtin(self, cnf: CNF) -> Solution:
        clauses = cnf.clauses()
        with PySolver(name=self.__name, bootstrap_with=clauses) as builtin_solver:
            if builtin_solver.solve():
                ids = builtin_solver.get_model()
                if ids:
                    return (True, ids)
                else:
                    return (False, [])
            else:
                return (False, [])

    def _solve_external(self, cnf: CNF) -> Solution:
        args = self.external_solvers[self.__name]
        if self.__args is not None:
            args += self.__args
        p = Popen([self.__name, *args], stdin=PIPE, stdout=PIPE, stderr=PIPE)

        clauses = cnf._cnf.clauses
        cls_num = len(clauses)
        step = 20000

        def producer(out_q):
            header = f"p cnf {cnf._cnf.nv} {cls_num}\n"
            out_q.put(header)
            for i in range(0, cls_num, step):
                slice = clauses[i : i + step]
                string = " 0\n".join([" ".join([str(lit) for lit in cl]) for cl in slice]) + " 0\n"
                out_q.put(string)
            out_q.put(None)

        def consumer(in_q, p):
            while True:
                item = in_q.get()
                if item is None:
                    break
                p.stdin.write(item.encode())
            p.stdin.close()

        q = queue.Queue()
        t1 = threading.Thread(target=producer, args=(q,))
        t2 = threading.Thread(target=consumer, args=(q, p))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert p.stdout is not None
        out = p.stdout.read()

        string = out.decode("utf-8")
        return self._parse_solution(string)

    @staticmethod
    def _parse_solution(string: str) -> Solution:
        string = string.lower()
        if "unsat" in string:
            return (False, [])

        def is_int(s):
            return s.isdigit() or (s[0] == "-" and s[1:].isdigit())

        ints = [int(s) for s in string.split() if is_int(s)]
        ids = [i for i in ints if i != 0]
        return (True, ids)
