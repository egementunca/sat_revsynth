"""SAT-based Circuit Synthesis.

This module provides SAT-based exact synthesis for reversible circuits.
Given a target truth table and gate count, it finds a circuit that implements
the function (or proves none exists).

The SAT encoding models:
    - Gate structure: each gate has exactly one target, controls are a subset of other wires
    - Data flow: bits propagate through gates with XOR updates at targets
    - Input/Output: initial state is identity, output matches target truth table

Key features:
    - Exact synthesis with specified gate count
    - Solution enumeration (exclude previously found circuits)
    - Constraint options: disable_empty_lines, set_global_controls_num
    - Support for excluding subcircuits (identity templates)

Example:
    >>> from truth_table.truth_table import TruthTable
    >>> from sat.solver import Solver
    >>> tt = TruthTable(2).cx(0, 1)  # CNOT function
    >>> synth = CircuitSynthesizer(tt, gate_count=1, solver=Solver("glucose4"))
    >>> circuit = synth.solve()
"""
from __future__ import annotations

from circuit.circuit import Circuit, Gate
from circuit.dim_group import DimGroup
from circuit.collection import Collection
from truth_table.truth_table import TruthTable
from sat.cnf import CNF, Literal
from sat.solver import Solver
from itertools import product
from functools import reduce


LiteralGrid = list[list[Literal]]


class CircuitSynthesizer:
    """SAT-based exact synthesizer for reversible circuits.
    
    Encodes the synthesis problem as a SAT formula and uses a solver to find
    circuits that implement the target truth table with exactly the specified
    number of gates.
    
    Args:
        output: Target truth table to synthesize.
        gate_count: Exact number of gates in the circuit.
        solver: SAT solver to use.
    
    Attributes:
        _output: Target truth table.
        _gate_count: Number of gates.
        _width: Number of wires (derived from truth table).
        _cnf: The SAT formula encoding the synthesis constraints.
    """
    def __init__(self, output: TruthTable, gate_count: int, solver: Solver):
        assert len(output) >= 2
        assert len(output) == pow(2, len(output[0]))
        assert all(len(word) == len(output[0]) for word in output)
        assert gate_count >= 0

        self._output = output
        self._gate_count = gate_count
        self._solver = solver
        self._width = len(output[0])
        self._words = len(output)
        self._circuit = None
        self._cnf, self._controls, self._targets = self._make_revcirc_cnf()

    def _make_revcirc_cnf(self) -> tuple[CNF, LiteralGrid, LiteralGrid]:
        cnf = CNF()
        line_iter = range(self._width)
        gate_iter = range(self._gate_count)
        ext_gate_iter = range(self._gate_count + 1)
        word_iter = range(self._words)

        controls = [[cnf.reserve_name(f"c_{lid}_{gid}") for lid in line_iter] for gid in gate_iter]
        targets = [[cnf.reserve_name(f"t_{lid}_{gid}") for lid in line_iter] for gid in gate_iter]
        or_bits = [[[cnf.reserve_name(f"o_{lid}_{gid}_{wid}") for lid in line_iter]
                    for gid in gate_iter] for wid in word_iter]
        data_bits = [[[cnf.reserve_name(f"d_{lid}_{gid}_{wid}") for lid in line_iter]
                      for gid in ext_gate_iter] for wid in word_iter]
        add_bits = [[cnf.reserve_name(f"a_{gid}_{wid}") for gid in gate_iter] for wid in word_iter]
        switch_bits = [[[cnf.reserve_name(f"s_{lid}_{gid}_{w}") for lid in line_iter]
                        for gid in gate_iter] for w in word_iter]

        # Single target per gate
        for target_layer in targets:
            cnf.exactly(target_layer, 1)

        # Target qubit cannot be a control qubit
        for gid, lid in product(gate_iter, line_iter):
            cnf.nand(targets[gid][lid], controls[gid][lid])

        # Target qubit is the data bit
        for wid, gid, lid in product(word_iter, gate_iter, line_iter):
            cnf.equals_or(or_bits[wid][gid][lid], [data_bits[wid][gid][lid], -controls[gid][lid]])

        # Add bit is the or of all or bits
        for wid, gid in product(word_iter, gate_iter):
            l_list = [or_bits[wid][gid][lid] for lid in line_iter]
            cnf.equals_and(add_bits[wid][gid], l_list)

        # Switch bit is the add bit and the target qubit
        for wid, gid, lid in product(word_iter, gate_iter, line_iter):
            cnf.equals_and(switch_bits[wid][gid][lid], [add_bits[wid][gid], targets[gid][lid]])

        # Data bit is the previous data bit xored with the switch bit
        for wid, gid, lid in product(word_iter, gate_iter, line_iter):
            cnf.xor([data_bits[wid][gid+1][lid], data_bits[wid]
                    [gid][lid], switch_bits[wid][gid][lid]])

        # Input/Output edge constraints
        for wid, lid in product(word_iter, line_iter):
            cnf.set_literal(data_bits[wid][0][lid], (wid >> lid & 1 == 1))

        for wid, lid in product(word_iter, line_iter):
            if self._output[wid][lid] in [0, 1]:
                a = data_bits[wid][self._gate_count][lid]
                b = (self._output[wid][lid] == 1)
                cnf.set_literal(a, b)

        return cnf, controls, targets

    def _gate_exclusion_list(self, layer: int, gate: Gate) -> list[int]:
        controls, target = gate
        assert layer < self._gate_count
        assert all([0 <= c and c < self._width] for c in controls)
        assert 0 <= target and target < self._width
        exclusion_list: list[int] = []
        for i in range(self._width):
            c_literal = self._controls[layer][i].value()
            c_literal = c_literal if i in controls else -c_literal
            t_literal = self._targets[layer][i].value()
            t_literal = t_literal if i == target else -t_literal
            exclusion_list += [c_literal, t_literal]
        return exclusion_list

    def exclude_solution(self, circuit: Circuit) -> "CircuitSynthesizer":
        if circuit._exclusion_list is None:
            gates = circuit.gates()
            exclusion_list: list[int] = []
            for layer, gate in enumerate(gates):
                exclusion_list += self._gate_exclusion_list(layer, gate)
            circuit._exclusion_list = exclusion_list
        self._cnf.exclude_by_values(circuit._exclusion_list)
        return self

    def disable_empty_lines(self) -> "CircuitSynthesizer":
        line_iter = range(self._width)
        gate_iter = range(self._gate_count)
        for lid in line_iter:
            line_targets = [self._targets[gid][lid] for gid in gate_iter]
            line_controls = [self._controls[gid][lid] for gid in gate_iter]
            line_variables = line_targets + line_controls
            self._cnf.atleast(line_variables, 1)
        return self

    def disable_full_control_lines(self) -> "CircuitSynthesizer":
        line_iter = range(self._width)
        gate_iter = range(self._gate_count)
        for lid in line_iter:
            line_controls = [-self._controls[gid][lid] for gid in gate_iter]
            self._cnf.atleast(line_controls, 1)
        return self

    def set_global_controls_num(self, controls_num: int) -> "CircuitSynthesizer":
        assert 0 <= controls_num and controls_num <= (self._width - 1) * self._gate_count
        self._global_controls_num = controls_num
        all_controls = reduce(lambda x, y: x+y, self._controls)
        self._cnf.exactly(all_controls, controls_num)
        return self

    def exclude_subcircircuit(self, circuit: Circuit) -> "CircuitSynthesizer":
        gates = circuit.gates()
        outer_gc = self._gate_count
        inner_gc = len(circuit)
        max_shift = outer_gc - inner_gc
        for shift in range(max_shift + 1):
            exclusion_list: list[int] = []
            for layer, gate in enumerate(gates):
                exclusion_list += self._gate_exclusion_list(layer+shift, gate)
            circuit._exclusion_list = exclusion_list
            self._cnf.exclude_by_values(circuit._exclusion_list)
        return self

    def exclude_dimgroup(self, dimgroup: DimGroup) -> "CircuitSynthesizer":
        for circuit in dimgroup:
            self.exclude_subcircircuit(circuit)
        return self

    def exclude_collection(self, collection: Collection) -> "CircuitSynthesizer":
        width = self._width
        subcollection = collection[width]
        for dg in subcollection[2:3]:
            self.exclude_dimgroup(dg)
        return self

    def solve(self) -> Circuit | None:
        if self._circuit is None:
            line_iter = range(self._width)
            gate_iter = range(self._gate_count)
            sat, literals = self._solver.solve(self._cnf)
            controls = self._controls
            targets = self._targets
            if not sat:
                self.circuit = None
                return self.circuit
            circuit = Circuit(self._width)
            for gid in gate_iter:
                g_controls = [lid for lid in line_iter if controls[gid][lid].value() in literals]
                g_targets = [lid for lid in line_iter if targets[gid][lid].value() in literals]
                assert len(g_targets) == 1
                circuit.mcx(g_controls, g_targets[0])
            self._circuit = circuit
        return self._circuit
