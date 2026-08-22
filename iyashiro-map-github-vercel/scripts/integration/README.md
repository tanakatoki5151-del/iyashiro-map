# Integrated R3 + ORBIT runtime build

The build-integrated-data.ps1 script reads the frozen sources without modifying
them:

- ALL PROJECT R3 bundle:
  - data/ALL_LENS_CELL_LEDGER_84060.csv.gz
  - data/SPIRITUAL_PASS_CELL_LEDGER.csv.gz
  - MANIFEST.json
- PROJECT ORBIT v2:
  - ORBIT_CELL_FACILITY_DISTANCES_v2_20260822.csv.gz
  - ORBIT_CANONICAL_FACILITIES_v2_20260822.csv.gz
  - ORBIT_VERIFICATION_v2_20260822.json

The builder validates source hashes, exact headers, counts, uniqueness, the
four-distance closure of every valid cell, nearest-facility references, R3 pass
membership, R3/ORBIT coordinate identity, and materialization of all 624 grid
rows before writing a release manifest. Manifest source pointers are portable
source:// logical names; machine-local absolute paths are never published.

## Run

Use PowerShell 7. The four source arguments are required so the build cannot
silently discover an older similarly named file.

    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
    & .\scripts\integration\build-integrated-data.ps1 \
      -R3Bundle '<absolute R3 bundle path>' \
      -OrbitDistances '<absolute ORBIT v2 distance gzip path>' \
      -OrbitFacilities '<absolute ORBIT v2 facility gzip path>' \
      -OrbitVerification '<absolute ORBIT v2 verification JSON path>'

The default output is public/data/integrated. The builder refuses to overwrite
normal output. A pre-existing output directory is accepted only when every
entry is named __partial_failed_*.

## Failure and partial output

A failed build may leave facilities, rows, or schema.json under the output root.
Never treat those files as a release: only a run with release-manifest.json and
qa.status=PASS is canonical.

Before retrying, move every partial item into an explicitly named quarantine.
Do not delete it. Quarantine must be outside public before deployment, for
example:

    __quarantine__/integrated_data_failed_run1_20260823

Resolve and verify absolute source and destination paths before any recursive
move. The final public/data/integrated directory must contain only the canonical
generated release.

## Runtime contract

app/lib/integrated-data/runtime.ts exports:

- lookupIntegratedCell(cellId)
- ensureIntegratedReleaseReady()
- releaseMetadata
- INTEGRATED_RELEASE_METADATA
- IntegratedArtifactMissingError
- IntegratedReleaseNotReadyError

The runtime validates the release manifest before lookup and caps its
per-process row-promise LRU at 64 entries. A missing artifact throws a typed
error; only an existing row shard with no requested cell returns null.

All 120,662 valid cells have ORBIT temple, shrine, cemetery, and general
hospital distance facts. Only the 84,060 R3 lens-ledger cells have R3
large-hospital, strong-history, P8, and pass/fail facts. The other 36,602 cells
remain UNKNOWN; they are never converted to safe or zero.

Shrines and general hospitals remain context-only and ranking-excluded,
respectively. Cemetery coverage is explicitly incomplete. Source-first and
robustness ranks are area-family ranks in R3, not cell-addressable ranks, so the
cell runtime returns them as null instead of guessing membership.
