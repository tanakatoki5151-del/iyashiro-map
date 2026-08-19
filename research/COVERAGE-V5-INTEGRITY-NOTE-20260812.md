# V10 100m evidence coverage v5 integrity note

Date: 2026-08-12

## Finding

The legacy value `85,767 zero-evidence cells / 71.1%` cannot be treated as a live cell-membership metric.

Direct audit of the reconstructed V10 source shows that `scripts/build-v10-assets.py` writes the following values into `coverage_baseline` as constants:

- `cellCount = regional["cellCount"]`
- `minimumScore = 0`
- `maximumScore = 46`
- `averageScore = 2.6`
- `zeroEvidenceCellCount = 85767`
- `zeroEvidenceCellSharePercent = 71.1`

The generated `research-coverage-v5.json` preserves the aggregate values but does not contain the 85,767 legacy cell IDs.

## Consequence

The legacy 71.1% series is frozen as an informational historical baseline. It must not be reduced using:

- 100% L03-b historical land-use coverage;
- catalog or website no-hit searches;
- total number of research logs;
- review polygons, candidate buffers, or context layers.

A new series, **cellId-specific execution/evidence coverage**, must be built from explicit cell membership.

## Required evidence layers

1. Cell-specific search execution evidence. `cellId`, query/method, source, date and bounded target are required.
2. Registered major-history evidence. Proxy points and verified historical boundaries remain separate.
3. Review-candidate evidence. These features retain `scoringEffect=none` until promotion.
4. Historical land-use / landform / disaster context. These are explanatory context, never negative major-history evidence.

## Quality gates

- Duplicate research log IDs: zero.
- Pending rows do not increase executed-cell coverage.
- No-hit is not proof of absence.
- The legacy 71.1% may only be replaced by a separately defined new metric with explicit cell membership and documented semantics.
- Exact historical polygon count remains zero until source-backed geometry, modern-location correspondence and independent review are complete.

See `research/audit_100m_evidence_coverage_v5.py` for a reproducible fail-closed audit.
