# LocationProfile v2 and PLACEGRAPH integration

Related issue: #10

## Purpose

The current production API already returns the legacy `theory`, `modern` and `combined` diagnosis. This integration adds project-owned Fact layers without destructively replacing that response and without directly adding research-project scores.

```text
address or coordinate
  -> queryAnchor
  -> canonical 100m cell
  -> legacy diagnose runtime
  -> project adapters
  -> PLACEGRAPH identity/time/geometry deduplication
  -> LocationProfile v2
  -> land dossier UI
  -> optional Decision Factors and PersonalPreferencePolicy
```

## Data ownership

- The site integration core owns query anchors, canonical-cell resolution, 100m/300m/500m search bands, API composition and presentation.
- PLACEGRAPH owns global identity, temporal geometry, transformation lineage and cell closure. It does not overwrite source-project evidence status.
- VEIL, UNDERLAND, LIMEN, V10/V11 and ECOSCAPE remain domain owners for their own facts and source-local IDs.
- KASO is activated only when building shape, direction or floor-plan evidence is available. An address point is not sufficient.

## PLACEGRAPH runtime package

The Drive-held `PLACEGRAPH_LOCATION_PROFILE_ADAPTER_v1_20260817.zip` contains:

- 120,662 explicit cell-closure records
- 1,479 sparse indexed cells
- 2,841 candidate-cell links
- 27 Global Features
- 30 Temporal Geometries
- 4 computed geometry entries
- status policies and handoff fixtures

The runtime does not need to load 120,662 rows for each request. It resolves the canonical cell, reads a sparse override when present and otherwise returns:

`NO_INDEXED_CANDIDATE_SOURCE_LIMITED`

That state means no currently indexed candidate is attached to the cell under partially scanned sources. It never means safe, empty or historically verified absent.

## Public and owner audiences

Public output is deny-by-default for feature details until the source row is explicitly public-eligible. Cell closure and coverage can still be shown.

Owner output may include internal candidate, conflict and provenance information, but it must preserve the original status and must not promote a candidate to confirmed.

## Fixed acceptance fixture

Input: `東京都豊島区目白五丁目8-1`

Expected:

- matched address: `東京都豊島区目白五丁目８番１号`
- coordinate approximately `35.723007, 139.694672`
- canonical cell: `g130-240`
- PLACEGRAPH closure: `NO_INDEXED_CANDIDATE_SOURCE_LIMITED`
- known links: `0`
- source ceiling: `PARTIAL_KNOWN_SOURCES`

Correct presentation:

> 現在取り込まれている歴史・場所資料では、この100mセルに紐づく既知候補はありません。ただし資料走査は部分的で、歴史上の不存在や安全を保証するものではありません。

## Next implementation slice

1. Add `/api/profile` accepting either `q` or `lat/lng`.
2. Create one queryAnchor and canonical cell per request.
3. Preserve the current diagnose response under `legacyRuntime`.
4. Add the PLACEGRAPH layer through `buildPlaceGraphLayer`.
5. Compose the final payload through `composeLocationProfile`.
6. Add `audience=public|owner` and authentication before owner output.
7. Expand the result sheet into Fact cards, timeline and coverage sections.
8. Port only the small VEIL adapter contract from draft PR #9 after independent acceptance tests.

## Non-goals for this contract PR

- no production route change
- no dataset committed to GitHub
- no score, ranking or automatic-exclusion mutation
- no merge of the large research branches
- no Vercel production promotion
