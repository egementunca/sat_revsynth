# Waksman-Style Wire Shuffler

## Overview

This document describes the current Waksman-style wire permutation synthesis in this repo.
The implementation is swap-based for correctness and scalability. A true Waksman routing
algorithm (fixed topology with recursive routing) is still a future upgrade.

## What It Does

- Generates ECA57 circuits that implement arbitrary wire permutations.
- Uses a swap macro (6 gates) for each swap.
- Supports optional obfuscation by filling identity slots with random identity circuits.

## Current Implementation

- `SimpleSwapNetwork` computes a swap sequence (selection-sort style).
- Each swap compiles to the 6-gate ECA57 macro.
- `WaksmanNetwork` is a wrapper that currently delegates to `SimpleSwapNetwork`.
- Obfuscation uses `identity_filler.py` to insert random identity circuits.

## Key Files

- `sat_revsynth/src/synthesizers/waksman.py`
- `sat_revsynth/src/synthesizers/identity_filler.py`
- `sat_revsynth/scripts/synth_waksman.py`
- `sat_revsynth/src/synthesizers/waksman_test.py`
- `identity-factory-api/identity_factory/api/waksman_endpoints.py`
- `identity-factory-api/identity_factory/wire_shuffler_db.py`

## CLI Usage

Single permutation:

```bash
python3 sat_revsynth/scripts/synth_waksman.py --width 8 --perm 7,6,5,4,3,2,1,0
```

Random permutation:

```bash
python3 sat_revsynth/scripts/synth_waksman.py --width 16 --random
```

Batch random permutations:

```bash
python3 sat_revsynth/scripts/synth_waksman.py --width 16 --sample 100 --output circuits.json
```

Verify a permutation:

```bash
python3 sat_revsynth/scripts/synth_waksman.py --width 8 --perm 7,6,5,4,3,2,1,0 --verify
```

## API Endpoints

Base path: `/api/v1/waksman`

- `POST /generate` generate a single circuit
- `GET /circuits` list stored circuits
- `GET /circuit/{id}` fetch a specific circuit
- `GET /stats` stats by width
- `GET /compare/{perm_hash}` compare SAT vs Waksman
- `POST /generate-batch` batch generation

## Notes On Width

- The current swap-based approach works for any width >= 2.
- Circuit width is `n + 1` because the swap macro uses one auxiliary wire.

## Tests

Run unit tests:

```bash
python3 -m pytest sat_revsynth/src/synthesizers/waksman_test.py -q
```

## Future Work

- Implement true Waksman/Beneš routing (fixed topology).
- Expose routing variants for structural diversity.
- Add performance/size benchmarks across widths.
