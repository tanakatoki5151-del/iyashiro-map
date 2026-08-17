# ECOSCAPE B122 Runtime Integration

## Purpose

Connect the Drive-canonical ECOSCAPE house-selection data plane to `LocationProfile v2` as a read-only Fact layer.

This runtime exposes the existing B114–B120 facts for a canonical 100 m cell. It does not rescore the legacy diagnosis, rewrite source projects, or allow external lenses to override ECOSCAPE candidacy.

## Canonical source chain

- B114: Core6 four-pillar Level B V4, 120,662 cells
- B115: residential candidate cells and connected components
- B116: official e-Stat area and core-zone aggregation
- B120: static property-profile adapter

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
- address and coordinate routes resolve to the same canonical cell: PASS
- legacy scores unchanged: PASS
- cross-project write-back: 0

## Git and preview release record

- Pull request: `#15 Connect ECOSCAPE B120 to LocationProfile`
- Main integration commit: `b2669f6ce3ed30fc878227e97fcfbdaaaa15f86b`
- Final validated preview: `dpl_6U9Hzypqea9HECpyWJQtRmQNs5UD`
- Preview source commit: `f60839806cefbd871e5e4141100c0111a11a46fa`
- Preview state: `READY`
- Authenticated preview API readback: `HTTP 200`
- Preview readback confirmed the fixed cell, ECOSCAPE dataset version, P25 state, pillar counts, no-score/no-override locks, and unchanged legacy scores.

The remaining B123 gate is production-alias readback and final Drive/NEXUS shipment registration.

## Guardrails

1. UNKNOWN is neither a score nor an adverse condition.
2. Magnetic, UNDERLAND, history, and terrain shadows do not add to or subtract from ECOSCAPE candidacy.
3. PLATEAU remains a Level B practical approximation; 114 source-hole cells stay explicit.
4. No third-party property URL is guessed when its address or coordinates are unavailable.
5. Source-owned IDs, status, provenance, and coverage limitations remain intact.
