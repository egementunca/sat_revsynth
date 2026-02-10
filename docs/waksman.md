# Waksman-Style Wire Shuffler

## Overview

This document describes wire permutation synthesis in this repo.
There are two paths:
- **SimpleSwapNetwork** (current default): swap-based and correct for any width.
- **Beneš (fixed-topology)**: implemented but still experimental for large widths.
Minimal Waksman routing remains a future upgrade.

## What It Does

- Generates ECA57 circuits that implement arbitrary wire permutations.
- Uses a swap macro (6 gates) for each swap.
- Supports optional obfuscation by filling identity slots with random identity circuits.

## Current Implementation

- `SimpleSwapNetwork` computes a swap sequence (selection-sort style).
- Each swap compiles to the 6-gate ECA57 macro (or an optional swap gadget library).
- `BenesNetwork` exists for fixed topology (use `--benes` in the CLI).
- Obfuscation uses `identity_filler.py` to insert random identity circuits.

## Key Files

- `sat_revsynth/src/synthesizers/waksman.py` (includes `BenesNetwork`)
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

Beneš (experimental):

```bash
python3 sat_revsynth/scripts/synth_waksman.py --width 16 --random --benes
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

## Swap Gadget Enumeration

You can SAT-enumerate swap gadgets (3-wire circuits that swap wire 0/1 and preserve wire 2):

```bash
python3 sat_revsynth/scripts/enumerate_swap_gadgets.py \
  --min-gates 6 --max-gates 20 --output sat_revsynth/data/swap_library.json
```

Then use the library during synthesis:

```bash
python3 sat_revsynth/scripts/synth_waksman.py --width 16 --random \
  --swap-library sat_revsynth/data/swap_library.json
```

## Future Work

- Stabilize Beneš routing for larger widths.
- Implement **minimal Waksman** routing (fewer switches).
- Expose routing variants for structural diversity.
- Add performance/size benchmarks across widths.
