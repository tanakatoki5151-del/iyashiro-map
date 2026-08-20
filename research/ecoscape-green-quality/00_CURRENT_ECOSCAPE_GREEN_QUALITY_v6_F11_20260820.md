# 00 CURRENT ECOSCAPE GREEN QUALITY v6 F11

Updated: 2026-08-20 JST  
Build: `ecoscape-green-quality-f11-fixed60-fulljoin-ranking-v1-20260820`

## Canonical truth

F11 repaired the green-quality CURRENT and completed the two missing external-validation gates.

- Period-specific 60-area evidence remains the frozen reference cohort.
- NEXUS external cohort: 17 unique canonical cells.
- External percentiles are calculated against the frozen 60-area distribution.
- Recalibration inside the 17-cell cohort is prohibited.
- B114 / B118 / B101 / B120 exact joins: 17/17 each.
- Duplicate external cellId: 0.
- Missing static joins: 0.
- External coverage pass: 17/17.
- Frozen-threshold stability:
  - vitality: 13/17
  - moisture: 13/17
  - heat: 14/17
  - all three: 7/17
- Self-ranked 17-cell labels changed after proper fixed-60 validation:
  - vitality: 9/17
  - moisture: 12/17
  - heat: 9/17

This confirms that the earlier 17-cell internal re-ranking was not a valid external test.

## New outputs

- 17-cell full green-quality cards with temporal and static context.
- Provisional pure-environment ranking for all 120,662 cells.
- Provisional residential-plausibility ranking for all 120,662 cells.
- Existing B116 official-area and 779-zone rankings packaged as human-scale area references.
- Interactive F11 research dashboard.

## Locks

- canonical B114/B115/B116/B120 mutation: 0
- scoringEffect: none
- candidateOverride: 0
- no single total score
- wet-heavy negative label: HOLD
- maintenance/cleanliness: UNKNOWN
- ventilation: potential, not measured wind
- magnetic stability: same-tier tie-break only
- formal NEXUS market ranking: unchanged

## Ranking status

The F11 ranks are `PROVISIONAL_REVIEW_ONLY`.
They are suitable for:
- finding candidate cells and areas,
- comparing reasons,
- selecting Level C targets.

They are not yet suitable for:
- automatic property rejection,
- safety claims,
- replacing current NEXUS decisions.

## Drive anchors

- Bundle: `1eCA9lzCtKpeV-380heOZc56-f4aIknHo`
- CURRENT: `1MrAIJzYlbjEjECN9LoVQDt0NqA4ChFMY`
- Dashboard: `1Q-49HinNHM2LoIRgfDQtV934iVV2R7t0`
- SHA-256: `3fa04149c0dbf40dba8d0cb7da5a578df7e07440211bc75a7e48f28253ff7af3`

## Next gate

1. Calibrate positive wet-heavy examples with field or imagery evidence.
2. Attach limited ground-truth labels to 30-50 locations.
3. Review obvious non-housing false positives in the provisional residential rank.
4. Run preview regression for the research dashboard.
5. Decide separately whether any axis may affect a formal ranking.
