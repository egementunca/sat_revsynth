# Contributing to SAT RevSynth

Thank you for your interest in contributing!

## Development Setup

1.  **Clone and install dependencies:**
    ```bash
    git clone https://github.com/M4D-A/sat_revsynth.git
    cd sat_revsynth
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    pip install black flake8 pytest
    ```

2.  **Run tests:**
    ```bash
    cd src
    pytest -v
    ```

## Development Workflow

1.  **Create a feature branch** from `main`.
2.  **Write code and tests**. Ensure your code is well-documented with docstrings.
3.  **Run linting**:
    ```bash
    black --line-length 100 src/
    flake8 src/
    ```
4.  **Submit a Pull Request**.

## Project Structure

For a detailed architecture overview, see [docs/design/architecture.md](docs/design/architecture.md).

- `src/circuit/`: Circuit representation and operations
- `src/sat/`: CNF encoding and solver interface
- `src/synthesizers/`: Synthesis algorithms
- `src/database/`: Canonicalization and storage
- `src/gates/`: Gate set definitions

## Pull Request Process

1.  Describe your changes clearly in the PR description.
2.  Link to any related issues.
3.  Ensure all CI checks pass.
