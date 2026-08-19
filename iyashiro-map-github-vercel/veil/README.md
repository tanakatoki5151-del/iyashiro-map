# PROJECT VEIL address-grid core (isolated branch)

This directory is an **independent PROJECT VEIL prototype**. It is intentionally
not wired into the deployed Iyashiro score/ranking UI.

## What it does

- resolves a latitude/longitude to the SHA-fixed canonical 100m `cellId` space;
- uses only the canonical grid and municipality-membership byte array;
- returns target-cell identity plus recall-preserving 100/300/500m candidate
  cell windows;
- blocks legacy Iyashiro score/label/ranking fields from the output surface.

The radius cell lists are **prefilters**, not evidence matches. Final VEIL
feature inclusion still requires exact geometry/shortest-distance rules and the
lane-specific evidence gates.

## Canonical source contract

Production input remains the external, read-only `regional-catalog-v4.json`
pointer fixed by PROJECT VEIL. This branch does **not** copy that 5MB source or
create a second geometry master.

Expected invariants:

- cells: 120,662
- municipalities: 48
- Tokyo 23: 62,553
- Yokohama: 43,785
- Kawasaki: 14,324
- grid: 624 x 462, nominal 100m

## Run tests

```bash
node --test veil/address-grid-core.test.mjs
```

No deployment or merge is implied by this branch. Integration should happen
only after VEIL normalized-feature/shadow data exists and the address API
acceptance tests pass.
