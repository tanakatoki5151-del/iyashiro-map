# Sites v36 property address recovery — 2026-08-14

This checkpoint adds three current-rental buildings whose full street-number addresses were independently supported by public property pages and matched exactly by the official GSI address search:

| propertyId | building | verified address | GSI grid | cell facility outcome | exact representative-point minimum |
| --- | --- | --- | ---: | --- | ---: |
| BLDG-149db14d7aa3 | カーサイトウ | 東京都世田谷区代沢1丁目2-8 | 94474 | mixed / recovery | 470.698209 m |
| BLDG-9f86e3c12bf7 | 等々力leaf | 東京都世田谷区等々力7丁目8-3 | 117550 | all fail | 245.587215 m |
| BLDG-ba12a3302314 | ヤクモハウス | 東京都目黒区八雲4丁目6-20 | 111561 | all fail | 330.401136 m |

The source gates were intentionally strict. コムフォート remains unlinked because the candidate address is also published under another building name (Charme東が丘); no coordinate was adopted for that property.

## Resulting coverage

- current buildings with representative points: 72 / 92
- remaining address-recovery queue: 20
- all representative points: 73 (70 public, 3 internal-only)
- public exact-point facility bands: 27 pass500 / 33 review300–499 / 10 below300
- building polygons: 0
- parcel polygons: 0
- saved ranking mutation: 0
- score mutation: 0
- automatic exclusion mutation: 0

All facility distances are point-to-frozen-OSM-geometry calculations in EPSG:6677 for the supplied address representative point only. They do not certify a whole building or parcel.

## Deterministic builds

- Sites source commit: `f23b1ef2757c40f9574d3fb0146e0681a4c9ffb7`
- property registry: `91d38dd57dccb6fb`
- property exact points: `788d96849990cc0b`
- research priority: `c492b4817fe46723`
- research progress KPI: `de664f16968386f6`

The operational research ledger remains 314 unique logs, latest 0316, next 0317. Property address work is not inserted into the historical 100m research log.
