# Installation Guide

## Prerequisites

- Python 3.8 or higher
- Git
- `pip` (Python package installer)

## Standard Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/M4D-A/sat_revsynth.git
    cd sat_revsynth
    ```

2.  **Create a virtual environment:**

    It is recommended to use a virtual environment to manage dependencies.

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

    This will install `python-sat` (pysat), `qiskit`, `pytest`, `numpy`, and `lmdb`.

## Installing External SAT Solvers

While `sat_revsynth` comes with many builtin solvers (via `pysat`), you may achieve better performance with modern, standalone SAT solvers.

### Kissat (Recommended for single-core performance)

Kissat was the winner of the SAT Competition 2024.

1.  Clone and build:
    ```bash
    git clone https://github.com/arminbiere/kissat.git
    cd kissat
    ./configure && make
    ```
2.  Add to PATH or copy to `/usr/local/bin`:
    ```bash
    sudo cp build/kissat /usr/local/bin/
    ```

### CaDiCaL 2.0

CaDiCaL is a versatile and robust solver.

1.  Clone and build:
    ```bash
    git clone https://github.com/arminbiere/cadical.git
    cd cadical
    ./configure && make
    ```
2.  Add to PATH:
    ```bash
    sudo cp build/cadical /usr/local/bin/
    ```

## Verifying Installation

To check if everything is working correctly, run the test suite:

```bash
cd src
pytest -v
```
