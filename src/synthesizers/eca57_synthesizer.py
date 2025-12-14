"""SAT-based synthesis for ECA57 circuits.

This module provides SAT-based exact synthesis for ECA57 (Rule 57) reversible circuits.
The ECA57 gate implements: target ^= (ctrl1 OR NOT ctrl2)

SAT Encoding:
    - Each gate position has variables for (target, ctrl1, ctrl2) wire assignments
    - Data flow is modeled through the circuit
    - The OR-NOT condition is encoded as: flip = ctrl1 OR (NOT ctrl2)
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Tuple
from itertools import product

from sat.cnf import CNF, Literal
from sat.solver import Solver
from gates.eca57 import ECA57Gate, ECA57Circuit

if TYPE_CHECKING:
    from truth_table.truth_table import TruthTable


class ECA57Synthesizer:
    """SAT-based synthesizer for ECA57 circuits.
    
    Encodes ECA57 circuit synthesis as a SAT problem and finds circuits
    with the specified number of gates that implement a target truth table.
    
    Args:
        output: Target truth table.
        gate_count: Exact number of ECA57 gates.
        solver: SAT solver to use.
    
    Example:
        >>> from truth_table.truth_table import TruthTable
        >>> from sat.solver import Solver
        >>> tt = TruthTable(3)  # Identity on 3 wires
        >>> synth = ECA57Synthesizer(tt, gate_count=2, solver=Solver("glucose4"))
        >>> circuit = synth.solve()
    """
    
    def __init__(self, output: "TruthTable", gate_count: int, solver: Solver):
        self._output = output
        self._gate_count = gate_count
        self._solver = solver
        self._width = output.bits_num()
        self._words = len(output)
        self._circuit: Optional[ECA57Circuit] = None
        
        assert self._width >= 3, "ECA57 requires at least 3 wires"
        
        self._cnf, self._targets, self._ctrl1s, self._ctrl2s = self._make_eca57_cnf()
    
    def _make_eca57_cnf(self) -> Tuple[CNF, list, list, list]:
        """Build CNF encoding for ECA57 circuit synthesis.
        
        Variables:
            t_{w}_{g}: wire w is target for gate g (one-hot per gate)
            c1_{w}_{g}: wire w is ctrl1 for gate g (one-hot per gate)
            c2_{w}_{g}: wire w is ctrl2 for gate g (one-hot per gate)
            d_{w}_{g}_{i}: data bit on wire w after gate g for input word i
            
        Returns:
            Tuple of (cnf, targets, ctrl1s, ctrl2s) where each is a 2D list indexed [gate][wire].
        """
        cnf = CNF()
        width = self._width
        gates = self._gate_count
        words = self._words
        
        # Gate structure variables
        targets = [[cnf.reserve_name(f"t_{w}_{g}") for w in range(width)] for g in range(gates)]
        ctrl1s = [[cnf.reserve_name(f"c1_{w}_{g}") for w in range(width)] for g in range(gates)]
        ctrl2s = [[cnf.reserve_name(f"c2_{w}_{g}") for w in range(width)] for g in range(gates)]
        
        # Data flow variables: d[word][gate+1][wire] (gate+1 because we have input at 0)
        data = [[[cnf.reserve_name(f"d_{w}_{g}_{i}") for w in range(width)]
                 for g in range(gates + 1)] for i in range(words)]
        
        # Auxiliary variables for the OR-NOT condition
        or_cond = [[cnf.reserve_name(f"or_{g}_{i}") for g in range(gates)] for i in range(words)]
        flip = [[cnf.reserve_name(f"flip_{g}_{i}") for g in range(gates)] for i in range(words)]
        
        # Constraints for gate structure
        for g in range(gates):
            # Exactly one target per gate
            cnf.exactly(targets[g], 1)
            # Exactly one ctrl1 per gate (different from target)
            cnf.exactly(ctrl1s[g], 1)
            # Exactly one ctrl2 per gate (different from target and ctrl1)
            cnf.exactly(ctrl2s[g], 1)
            
            # Target, ctrl1, ctrl2 must be different wires
            for w in range(width):
                # target and ctrl1 cannot be same wire
                cnf.nand(targets[g][w], ctrl1s[g][w])
                # target and ctrl2 cannot be same wire
                cnf.nand(targets[g][w], ctrl2s[g][w])
                # ctrl1 and ctrl2 cannot be same wire
                cnf.nand(ctrl1s[g][w], ctrl2s[g][w])
        
        # Data flow constraints
        for i in range(words):
            # Initial data (input)
            for w in range(width):
                input_bit = (i >> w) & 1
                cnf.set_literal(data[i][0][w], input_bit == 1)
            
            # Gate application: ECA57 rule target ^= (ctrl1 OR NOT ctrl2)
            for g in range(gates):
                # For each gate, we need to compute:
                # 1. or_cond[g][i] = data[ctrl1] OR (NOT data[ctrl2])
                # 2. flip[g][i] = or_cond AND (wire is target)
                # 3. data_out = data_in XOR flip
                
                # Compute ctrl1_val: which wire provides ctrl1 value
                # ctrl1_val = OR over w: (c1_w_g AND d_w_g_i)
                c1_products = []
                for w in range(width):
                    prod_var = cnf.reserve_name(f"C1v_{w}_{g}_{i}", True)
                    cnf.equals_and(prod_var, [ctrl1s[g][w], data[i][g][w]])
                    c1_products.append(prod_var)
                ctrl1_val = cnf.reserve_name(f"C1val_{g}_{i}", True)
                cnf.equals_or(ctrl1_val, c1_products)
                
                # Compute ctrl2_val: which wire provides ctrl2 value  
                c2_products = []
                for w in range(width):
                    prod_var = cnf.reserve_name(f"C2v_{w}_{g}_{i}", True)
                    cnf.equals_and(prod_var, [ctrl2s[g][w], data[i][g][w]])
                    c2_products.append(prod_var)
                ctrl2_val = cnf.reserve_name(f"C2val_{g}_{i}", True)
                cnf.equals_or(ctrl2_val, c2_products)
                
                # or_cond = ctrl1_val OR (NOT ctrl2_val)
                # Equivalently: or_cond = ctrl1_val OR neg_ctrl2
                neg_ctrl2 = -ctrl2_val
                cnf.equals_or(or_cond[i][g], [ctrl1_val, neg_ctrl2])
                
                # Apply gate to each wire
                for w in range(width):
                    # switch_bit = or_cond AND (w is target)
                    switch_bit = cnf.reserve_name(f"Sw_{w}_{g}_{i}", True)
                    cnf.equals_and(switch_bit, [or_cond[i][g], targets[g][w]])
                    
                    # data_out = data_in XOR switch_bit
                    cnf.xor([data[i][g+1][w], data[i][g][w], switch_bit])
            
            # Output constraints
            for w in range(width):
                output_bit = self._output[i][w]
                if output_bit in [0, 1]:
                    cnf.set_literal(data[i][gates][w], output_bit == 1)
        
        return cnf, targets, ctrl1s, ctrl2s
    
    def solve(self) -> Optional[ECA57Circuit]:
        """Solve for an ECA57 circuit.
        
        Returns:
            ECA57Circuit if satisfiable, None otherwise.
        """
        if self._circuit is not None:
            return self._circuit
        
        sat, literals = self._solver.solve(self._cnf)
        
        if not sat:
            return None
        
        # Extract gate assignments
        circuit = ECA57Circuit(self._width)
        
        for g in range(self._gate_count):
            # Find which wire is target, ctrl1, ctrl2
            target = None
            ctrl1 = None
            ctrl2 = None
            
            for w in range(self._width):
                if self._targets[g][w].value() in literals:
                    target = w
                if self._ctrl1s[g][w].value() in literals:
                    ctrl1 = w
                if self._ctrl2s[g][w].value() in literals:
                    ctrl2 = w
            
            assert target is not None and ctrl1 is not None and ctrl2 is not None
            circuit.add_gate(target, ctrl1, ctrl2)
        
        self._circuit = circuit
        return circuit
    
    def exclude_solution(self, circuit: ECA57Circuit) -> "ECA57Synthesizer":
        """Exclude a solution to find alternative circuits.
        
        Args:
            circuit: Circuit to exclude.
            
        Returns:
            Self for chaining.
        """
        # Build exclusion clause for this exact circuit
        exclusion_list = []
        
        for g, gate in enumerate(circuit.gates()):
            for w in range(self._width):
                t_lit = self._targets[g][w].value()
                t_lit = t_lit if w == gate.target else -t_lit
                exclusion_list.append(t_lit)
                
                c1_lit = self._ctrl1s[g][w].value()
                c1_lit = c1_lit if w == gate.ctrl1 else -c1_lit
                exclusion_list.append(c1_lit)
                
                c2_lit = self._ctrl2s[g][w].value()
                c2_lit = c2_lit if w == gate.ctrl2 else -c2_lit
                exclusion_list.append(c2_lit)
        
        self._cnf.exclude_by_values(exclusion_list)
        self._circuit = None  # Reset cached solution
        return self
