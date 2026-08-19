# HANDOFF ECOSCAPE GREEN QUALITY F11

Start from build `ecoscape-green-quality-f11-fixed60-fulljoin-ranking-v1-20260820`.

## Read first

1. `00_CURRENT_ECOSCAPE_GREEN_QUALITY_v6_F11_20260820.md`
2. `F11_MASTER_AUDIT.json`
3. `F11_RANKING_LOGIC.md`
4. Drive `ECOSCAPE_GREEN_QUALITY_F11_EXTERNAL17_CARDS.csv`
5. Drive `ECOSCAPE_F11_RESIDENTIAL_CELL_RANKING_120662.csv.gz`

## Closed gates

- 60-area reference frozen.
- 17 external cells re-evaluated without cohort recalibration.
- B114/B118/B101/B120 exact join 17/17.
- Provisional 120,662-cell environment and residential ranks created.
- Research dashboard generated.
- Duplicate F9 CURRENT and handoff files archived.
- Phantom F10 registry entries superseded.

## Do not

- recompute percentiles within the external cohort;
- treat high moisture alone as adverse;
- treat ventilation proxy as measured wind;
- treat rank as safety or suitability;
- use magnetic high/low as a good/bad score;
- overwrite B114/B115/B116/B120;
- merge into main before preview checks.

## Next action

1. Ground-truth calibration for 30-50 points.
2. Review obvious non-housing false positives in the residential rank.
3. Preview-test `/research/ecoscape-green-quality-f11`.
4. Decide separately whether any axis may affect the formal ECOSCAPE or NEXUS ranking.
