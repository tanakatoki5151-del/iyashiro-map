# ECOSCAPE B120 LocationProfile runtime integration

## Canonical source and runtime

- Source: Drive canonical B120 bundle, SHA-256 `add1d47e2b06b12ad8fbc69027a3cb50d18c867b044583576a6d2536822e47c1`.
- Zone source: Drive canonical B116 bundle, SHA-256 `d13a33f369012dbd472bfcf9d6ba65baac72a525d3f61949bff64506871e09ef`.
- Runtime: deterministic seven-byte dense record over the frozen 462-column canonical grid.
- Formal cells: 120,662.
- Candidate counts: environmental 21,549; residential 12,616; threshold-stable 89,365.
- Core zones with three or more cells: 779.
- Explicit PLATEAU source-hole UNKNOWN cells: 114.

## LocationProfile contract

The ECOSCAPE adapter exposes the P25 aggregate state, known/favorable/caution pillar counts, threshold stability, environmental and residential candidacy, 300m and 500m continuity, PLATEAU status and residential component context.

Guardrails are fixed:

- `scoringEffect: none`
- `candidateOverride: false`
- no cross-project averaging
- no source-project write-back
- UNKNOWN is neither zero nor negative evidence
- magnetic, UNDERLAND, history and terrain shadows do not modify the ECOSCAPE candidate state

## Acceptance fixtures

### Mejiro address and coordinate

- Address: `東京都豊島区目白五丁目8-1`
- Coordinate: `35.723007, 139.694672`
- Canonical cell: `g130-240`
- P25 state: `CAUTION`
- Known / favorable / caution pillars: `4 / 1 / 2`
- Legacy theory / modern / combined scores: `50 / 75 / 75`, unchanged

### Explicit UNKNOWN

- Coordinate: `35.74891843334531, 139.7270419646649`
- Canonical cell: `g101-269`
- Availability: `partial`
- PLATEAU state: `UNKNOWN_SOURCE_TILE_404`

## Verification evidence

### Deterministic generation and API regression

GitHub Actions run `32026393246`:

- Drive outer SHA-256 and ZIP integrity: PASS
- deterministic 120,662-cell generation: PASS
- production build: PASS
- rendered/API tests: 7 pass, 0 fail

### Security patch

GitHub Actions run `32029980143`:

- Next.js upgraded within the same major line to `16.3.1`
- production build and all seven tests: PASS
- production dependency audit: info 0, low 0, moderate 0, high 0, critical 0

### Production-browser and mobile readback

GitHub Actions run `32030552737`, artifact `9288757330`:

- production `vinext start` health: PASS
- coordinate, address and explicit-UNKNOWN API routes: HTTP 200 JSON
- iPhone 13 Chromium view: ECOSCAPE card visible
- horizontal overflow: 0px
- console errors: 0
- artifact digest: `sha256:b1a42fc64f38e14199f9b544bc0799f58f3f3e7bf7ed3352cbb0c5ced8e57aa0`
- Drive QA bundle: `ECOSCAPE_MW5_RUNTIME_BROWSER_QA_B122R.zip`

Vercel Deployment Protection remains enabled. A protected preview build was READY with no error/fatal runtime logs; public production readback is the post-merge release gate.
