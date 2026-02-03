"""SAT-based synthesizer for ECA57 circuits with Skeleton Graph constraints.

This module extends ECA57Synthesizer to support "Skeleton Graph" constraints,
which enforce specific collision (non-commutativity) structures between gates.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from sat.cnf import Literal
from sat.solver import Solver
from synthesizers.eca57_synthesizer import ECA57Synthesizer

if TYPE_CHECKING:
    from truth_table.truth_table import TruthTable


class ECA57SkeletonSynthesizer(ECA57Synthesizer):
    """Synthesizer for ECA57 circuits with Skeleton Graph constraints.

    This synthesizer adds constraints to enforce a specific structure in the
    circuit's dependency graph (skeleton graph).

    A "Collision" between gate i and gate j exists if they do not commute.
    For ECA57 gates (t, c1, c2), they collide if:
      target(i) in {ctrl1(j), ctrl2(j)} OR target(j) in {ctrl1(i), ctrl2(i)}

    Args:
        output: Target truth table.
        gate_count: Exact number of ECA57 gates.
        solver: SAT solver to use.
        chain_length: Number of adjacent collision edges to enforce in a
            contiguous block. None enforces collisions for all adjacent pairs.
        avoid_adjacent_identical: If True, forbid identical adjacent gates
            (prevents immediate cancellation g*g).
    """

    def __init__(
        self,
        output: "TruthTable",
        gate_count: int,
        solver: Solver,
        disable_empty_lines: bool = True,
        chain_length: Optional[int] = None,
        avoid_adjacent_identical: bool = True,
    ):
        super().__init__(output, gate_count, solver, disable_empty_lines)

        # Add skeleton constraints
        self._add_skeleton_constraints(chain_length, avoid_adjacent_identical)

    def _add_skeleton_constraints(
        self,
        chain_length: Optional[int],
        avoid_adjacent_identical: bool,
    ) -> None:
        """Add constraints for skeleton graph structure."""
        gates = self._gate_count

        if gates < 2:
            return

        adj_collisions = []
        for g in range(gates - 1):
            next_g = g + 1
            adj_collisions.append(self._collision_var(g, next_g))
            if avoid_adjacent_identical:
                self._forbid_adjacent_identical(g, next_g)

        # Also handle wrap-around pair (last gate, first gate) for cyclic identity circuits.
        # This is important because rotations can make the last and first gates adjacent,
        # creating consecutive identical gates if not forbidden.
        if avoid_adjacent_identical:
            self._forbid_adjacent_identical(gates - 1, 0)

        self._enforce_chain(adj_collisions, chain_length)

    def _collision_var(self, g: int, next_g: int) -> Literal:
        """Create collision variable for gate g and next_g."""
        cnf = self._cnf

        cond1 = self._match_or(
            f"Match_t{g}c1{next_g}",
            self._targets[g],
            self._ctrl1s[next_g],
        )
        cond2 = self._match_or(
            f"Match_t{g}c2{next_g}",
            self._targets[g],
            self._ctrl2s[next_g],
        )
        cond3 = self._match_or(
            f"Match_t{next_g}c1{g}",
            self._targets[next_g],
            self._ctrl1s[g],
        )
        cond4 = self._match_or(
            f"Match_t{next_g}c2{g}",
            self._targets[next_g],
            self._ctrl2s[g],
        )

        collision_var = cnf.reserve_name(f"Col_{g}_{next_g}", True)
        cnf.equals_or(collision_var, [cond1, cond2, cond3, cond4])
        return collision_var

    def _match_or(self, prefix: str, vars_a: list[Literal], vars_b: list[Literal]) -> Literal:
        """Return a literal representing OR_w (vars_a[w] AND vars_b[w])."""
        cnf = self._cnf
        width = self._width

        matches = []
        for w in range(width):
            temp = cnf.reserve_name(f"{prefix}_{w}", True)
            cnf.equals_and(temp, [vars_a[w], vars_b[w]])
            matches.append(temp)

        match_or = cnf.reserve_name(prefix, True)
        cnf.equals_or(match_or, matches)
        return match_or

    def _forbid_adjacent_identical(self, g: int, next_g: int) -> None:
        """Forbid gate g and next_g from being identical."""
        cnf = self._cnf

        t_eq = self._match_or(f"EqT_{g}_{next_g}", self._targets[g], self._targets[next_g])
        c1_eq = self._match_or(f"EqC1_{g}_{next_g}", self._ctrl1s[g], self._ctrl1s[next_g])
        c2_eq = self._match_or(f"EqC2_{g}_{next_g}", self._ctrl2s[g], self._ctrl2s[next_g])

        cnf._cnf.append([-t_eq.value(), -c1_eq.value(), -c2_eq.value()])

    def _enforce_chain(
        self,
        adj_collisions: list[Literal],
        chain_length: Optional[int],
    ) -> None:
        """Enforce a contiguous chain of adjacent collisions."""
        cnf = self._cnf
        max_edges = len(adj_collisions)

        if chain_length is None or chain_length >= max_edges:
            for collision_var in adj_collisions:
                cnf.set_literal(collision_var, True)
            return

        if chain_length <= 0:
            return

        max_start = max_edges - chain_length
        chain_starts = []
        for start in range(max_start + 1):
            chain_var = cnf.reserve_name(f"Chain_{start}_{chain_length}", True)
            chain_starts.append(chain_var)
            for idx in range(start, start + chain_length):
                cnf._cnf.append([-chain_var.value(), adj_collisions[idx].value()])

        cnf.atleast(chain_starts, 1)
