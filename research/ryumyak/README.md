# RYUMYAK-LENS

**流脈レンズ／龍脈として解釈する価値がある地形・水系候補図**

RYUMYAK-LENS is a reproducible translation layer between East Asian form-school feng-shui concepts and modern terrain, hydrology, underground, historical and ritual-landscape evidence.

## Research stance

This project does not begin by denying `気`, `生気`, `龍脈`, `穴` or `イヤシロチ`. These ideas are treated as legitimate objects of spiritual, historical and cultural inquiry.

At the same time:

- a DEM-derived ridge is not automatically a detected spiritual dragon vein;
- a historical channel is not automatically bad land;
- a shrine count is not an automatic good score;
- a road, tunnel, cemetery or incident is not automatically `邪気`;
- symbolic proxies are never inserted as independent scientific votes into UNDERLAND strict A4.

The project preserves five separate layers: physical observation, historical documentation, computational proxy, symbolic/spiritual interpretation and personal sense.

## Shared spatial base

The project uses the same canonical universe as the IYASHIRO and UNDERLAND systems:

- 120,662 valid 100 m cells
- 48 municipal units
- Tokyo 23 wards, Yokohama 18 wards and Kawasaki 7 wards
- multi-scale reading at 3,000 m, 1,000 m, 300 m and 100 m

The existing IYASHIRO terrain score remains the domain-of-record for the current directional-line-crossing engine. RYUMYAK-LENS is a new derived layer and does not overwrite it.

## Modules

1. **M1 Mountain Dragon**: ridge hierarchy, continuity, direction persistence, relief, curvature, saddles, branching and severance.
2. **M2 Surface Water Dragon**: present rivers, historical channels, culverts, springs, valleys, flow accumulation, embrace, approach/departure and relative height.
3. **M3 Subsurface Water Continuity**: UNDERLAND groundwater model, comparable observed borehole water, geology, lithology and epoch.
4. **M4 Xue / Node Candidate**: rear support, side enclosure, front opening, local convergence and stable bench.
5. **M5 Ming Tang / Wind Shelter**: viewshed, opening, enclosure, solar access, prevailing wind and ventilation.
6. **M6 Severance / Stagnation**: artificial cuts, cut-and-fill, closed depressions, old channel plus shallow observed water, low sun and low ventilation.
7. **M7 Ritual / Land Memory**: shrines, temples, water deities, Inari, hokora, Koshin, boundary features, memorials, legends and relocation.

## Nanjing 2021 translation

The 2021 Nanjing mausoleum GIS study is used as a methodological seed. Its useful contribution is the architecture:

`traditional concept → measurable geographic factor → factor-level sensitivity → independent validation → case explanation`.

Its Nanjing thresholds, AHP weights and mausoleum labels are not transferred to Tokyo. Tokyo requires relative elevation, multi-scale ridge continuity, artificial terrain, culverted and historical waterways, observed groundwater, housing dampness, parcel/building orientation and spatial-block holdout validation.

See `config/NANJING_2021_TO_TOKYO_TRANSLATION_SPEC_v1.json`.

## Shrine and ritual relation

House-selection output records distance bands at 100, 300, 500, 1,000 and 3,000 m, but distance is not the interpretation itself. Current, original and historical positions are separated. The model also checks same ridge, valley, watershed, upstream/downstream relation, line of sight, orientation, relocation and identity conflict.

The nearest shrine can be meaningful as a historical landscape relation without being a universal positive. A water deity can mark a protected water source, a boundary, flood memory or a dangerous torrent context. The feature's identity and historical function must be read before interpretation.

## Validation order

1. Freeze source registry and classical concept codebook.
2. Materialize transparent factor layers without one final score.
3. Run a 240-cell stratified pilot and 120-cell spatial holdout.
4. Audit false positives and false negatives by municipality and landform.
5. Compare personal sense only after the first proxy output is frozen.
6. Freeze definitions and thresholds.
7. Run the full 120,662 cells.
8. Expose five site cards: physical/damp, water memory, ryumyak interpretation, spiritual-cultural context and personal sense.

## Current state

`BOOTSTRAPPED_RESEARCH_ACTIVE`

Initial project contract, Nanjing-to-Tokyo translation specification, output schema and pilot design are materialized on the research branch. Literature review and UNDERLAND B22 observed-borehole expansion run in parallel.
