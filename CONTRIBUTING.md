# Contributing to SAT RevSynth

## Development Setup

1. Clone and install dependencies:
   ```bash
   git clone https://github.com/M4D-A/sat_revsynth.git
   cd sat_revsynth
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   pip install black flake8
   ```

2. Run tests:
   ```bash
   cd src
   pytest -v
   ```

## Code Style

- Follow PEP 8 guidelines
- Use `black` for formatting: `black --line-length 100 src/`
- Run `flake8` before committing

## Project Structure

- `src/circuit/`: Circuit representation and operations
- `src/sat/`: CNF encoding and solver interface
- `src/synthesizers/`: Synthesis algorithms
- `src/database/`: Canonicalization and storage
- `src/gates/`: Gate set definitions

## Adding Tests

- Place tests in `*_test.py` files alongside the module
- Use pytest fixtures for common setup
- Test across multiple solvers when relevant

## Pull Request Process

1. Create a feature branch
2. Add tests for new functionality
3. Ensure all tests pass
4. Submit PR with clear description
