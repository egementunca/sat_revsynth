# API Reference

## Core Modules

### `circuit`

- **[Circuit](../src/circuit/circuit.py)**: The main class representing a reversible circuit.
    - `tt()`: Get truth table.
    - `append()`, `cx()`, `mcx()`: Add gates.
    - `unroll()`: Generate equivalent circuits (swap/rotation/permutation).

### `synthesizers`

- **[CircuitSynthesizer](../src/synthesizers/circuit_synthesizer.py)**: The SAT-based synthesizer.
    - `solve()`: Run the synthesis.
    - `exclude_solution(circuit)`: Add a blocking clause to find different circuits.
    - `disable_empty_lines()`: Constrain synthesis to use all wires.

### `truth_table`

- **[TruthTable](../src/truth_table/truth_table.py)**: Boolean function representation.

### `sat`

- **[Solver](../src/sat/solver.py)**: Interface for SAT solvers.
    - Supports `glucose4`, `cadical153` (builtin) and `kissat` (external).

### `database`

- **[TemplateDBEnv](../src/database/lmdb_env.py)**: Low-level LMDB wrapper.
- **[TemplateStore](../src/database/templates.py)**: High-level API for storing and retrieving templates.
