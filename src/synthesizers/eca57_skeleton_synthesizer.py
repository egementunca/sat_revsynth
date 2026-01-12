"""SAT-based synthesizer for ECA57 circuits with Skeleton Graph constraints.

This module extends ECA57Synthesizer to support "Skeleton Graph" constraints,
which enforce specific collision (non-commutativity) structures between gates.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from sat.cnf import CNF, Literal
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
    """
    
    def __init__(self, output: "TruthTable", gate_count: int, solver: Solver, 
                 disable_empty_lines: bool = True):
        super().__init__(output, gate_count, solver, disable_empty_lines)
        
        # Add skeleton constraints
        self._add_skeleton_constraints()
        
    def _add_skeleton_constraints(self):
        """Add constraints for skeleton graph structure.
        
        Currently enforces a simple "Chain" structure:
        Gate i and Gate i+1 MUST collide for all i.
        """
        cnf = self._cnf
        gates = self._gate_count
        width = self._width
        
        # We need collision variables for adjacent gates
        # collision_{i}_{i+1}
        
        for g in range(gates - 1):
            next_g = g + 1
            
            # Create collision variable: true if g and next_g collide
            # Internal vars must start with Uppercase
            collision_var = cnf.reserve_name(f"Col_{g}_{next_g}", True)
            
            # A collision happens if:
            # 1. T_g == C1_next_g
            # 2. T_g == C2_next_g
            # 3. T_next_g == C1_g
            # 4. T_next_g == C2_g
            
            # We build these conditions. Each is an OR over wires.
            conditions = []
            
            # 1. T_g == C1_next
            # Exists w such that t_{w}_{g} AND c1_{w}_{next}
            t_g_c1_next_vars = []
            for w in range(width):
                # temp = t_g_w AND c1_next_w
                temp = cnf.reserve_name(f"Match_t{g}c1{next_g}_{w}", True)
                cnf.equals_and(temp, [self._targets[g][w], self._ctrl1s[next_g][w]])
                t_g_c1_next_vars.append(temp)
            
            cond1 = cnf.reserve_name(f"Cond_t{g}c1{next_g}", True)
            cnf.equals_or(cond1, t_g_c1_next_vars)
            conditions.append(cond1)
            
            # 2. T_g == C2_next
            t_g_c2_next_vars = []
            for w in range(width):
                temp = cnf.reserve_name(f"Match_t{g}c2{next_g}_{w}", True)
                cnf.equals_and(temp, [self._targets[g][w], self._ctrl2s[next_g][w]])
                t_g_c2_next_vars.append(temp)
                
            cond2 = cnf.reserve_name(f"Cond_t{g}c2{next_g}", True)
            cnf.equals_or(cond2, t_g_c2_next_vars)
            conditions.append(cond2)
            
            # 3. T_next == C1_g
            t_next_c1_g_vars = []
            for w in range(width):
                temp = cnf.reserve_name(f"Match_t{next_g}c1{g}_{w}", True)
                cnf.equals_and(temp, [self._targets[next_g][w], self._ctrl1s[g][w]])
                t_next_c1_g_vars.append(temp)
                
            cond3 = cnf.reserve_name(f"Cond_t{next_g}c1{g}", True)
            cnf.equals_or(cond3, t_next_c1_g_vars)
            conditions.append(cond3)
            
            # 4. T_next == C2_g
            t_next_c2_g_vars = []
            for w in range(width):
                temp = cnf.reserve_name(f"Match_t{next_g}c2{g}_{w}", True)
                cnf.equals_and(temp, [self._targets[next_g][w], self._ctrl2s[g][w]])
                t_next_c2_g_vars.append(temp)
                
            cond4 = cnf.reserve_name(f"Cond_t{next_g}c2{g}", True)
            cnf.equals_or(cond4, t_next_c2_g_vars)
            conditions.append(cond4)
            
            # collisions_var <=> OR(cond1, cond2, cond3, cond4)
            cnf.equals_or(collision_var, conditions)
            
            # ENFORCE THE CHAIN: collision must be true
            cnf.set_literal(collision_var, True)
