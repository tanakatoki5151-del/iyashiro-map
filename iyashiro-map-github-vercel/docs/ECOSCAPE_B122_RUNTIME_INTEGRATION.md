# ECOSCAPE B122 Runtime Integration

## Purpose

Connect the Drive-canonical ECOSCAPE house-selection data plane to `LocationProfile v2` as a read-only Fact layer.

This runtime exposes the existing B114–B120 facts for a canonical 100 m cell. It does not rescore the legacy diagnosis, rewrite source projects, or allow external lenses to override ECOSCAPE candidacy.

## Canonical source chain

- B114: Core6 four-pillar Level B V4, 120,662 cells
- B115: residential candidate cells and connected components
- B116: official e-Stat area and core-zone aggregation
- B120: static property-profile adapter
- B121: cross-layer explainability audit, 14 / 14 PASS
- B122: deterministic runtime, LocationProfile adapter and API/UI integration
- B127: production-promotion gate and full Drive readback package

The compact runtime is generated deterministically from verified Drive bundles and checked against the fixed 120,662-cell universe.

## Runtime output

The `ecoscape` LocationProfile layer returns:

- P25 aggregate state
- known, favorable, and caution pillar counts
- threshold stability
- robust environmental candidacy
- robust residential candidacy
- 300 m and 500 m candidate continuity
- residential component and core-zone context
- PLATEAU status and explicit source-hole UNKNOWN

Every ECOSCAPE layer has `scoringEffect: none` and `candidateOverride: false`.

## Fixed acceptance fixture

`35.723007, 139.694672` resolves to `g130-240`.

Expected ECOSCAPE state:

- availability: `available`
- dataset: `ECOSCAPE_PROPERTY_PROFILE_INDEX_120662_B120`
- P25 aggregate: `CAUTION`
- known pillars: `4`
- favorable pillars: `1`
- caution pillars: `2`
- legacy theory / modern / combined: `50 / 75 / 75`

The explicit PLATEAU source-hole fixture `g101-269` remains `partial` with `UNKNOWN_SOURCE_TILE_404`; UNKNOWN is never converted to zero, negative evidence, or safety.

## Validation

- deterministic 120,662-cell runtime generation: PASS
- Drive outer SHA-256 and ZIP integrity: PASS
- production build and rendered/API regression suite: PASS
- mobile production-browser E2E: PASS
- address and coordinate routes resolve to the same cell: PASS
- explicit UNKNOWN semantics: PASS
- legacy scores unchanged: PASS
- cross-project write-back: 0

## Git, preview and B127 release record

- Pull request: `#15 Connect ECOSCAPE B120 to LocationProfile`
- Main integration commit: `b2669f6ce3ed30fc878227e97fcfbdaaaa15f86b`
- Previous main release-record commit: `f43d81c701a4c295f9f26234984dcf89f9006b08`
- Final validated preview: `dpl_6U9Hzypqea9HECpyWJQtRmQNs5UD`
- Preview source commit: `f60839806cefbd871e5e4141100c0111a11a46fa`
- Preview state: `READY`
- Authenticated preview API readback: `HTTP 200`
- B127 Drive bundle: `11c04hTNBB7WgxaNk90whQcjME-7Bqivo`
- B127 SHA-256: `46d42792f77c7d7ff0ff978c9a621e761d78f5a8cc419e203594b9bce1cce516`
- Canonical CURRENT: `00_CURRENT_ECOSCAPE_MASTER_v7_B127_20260817.md`
- Canonical HANDOFF: `00_CURRENT_ECOSCAPE_HANDOFF_INDEX_v2_B127_20260817.md`

The preview readback confirmed the fixed cell, ECOSCAPE dataset version, P25 state, pillar counts, no-score/no-override locks, and unchanged legacy scores.

A no-build promotion probe correctly found no repository `VERCEL_TOKEN` secret and skipped promotion without exposing or inventing credentials. The public production domain remained healthy on the previous deployment, where ECOSCAPE was still `not_available`.

This documentation-only main commit deliberately retriggers the Vercel production deployment after preview builds resumed. Application code is unchanged from the validated integration.

## Remaining final gate

Read back the public production domain and require:

- ECOSCAPE availability `available`
- dataset `ECOSCAPE_PROPERTY_PROFILE_INDEX_120662_B120`
- `g130-240` P25 `CAUTION`, pillars `4 / 1 / 2`
- address and coordinate agreement
- `g101-269` explicit PLATEAU UNKNOWN
- legacy `50 / 75 / 75` unchanged
- mobile UI without horizontal overflow
- no release-blocking runtime errors

Only after these pass should the final MW5/NEXUS release be marked complete.

## Guardrails

1. UNKNOWN is neither a score nor an adverse condition.
2. Magnetic, UNDERLAND, history, and terrain shadows do not add to or subtract from ECOSCAPE candidacy.
3. PLATEAU remains a Level B practical approximation; 114 source-hole cells stay explicit.
4. No third-party property URL is guessed when its address or coordinates are unavailable.
5. Source-owned IDs, status, provenance, and coverage limitations remain intact.
