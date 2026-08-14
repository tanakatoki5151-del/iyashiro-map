# Sites v33 — priority property address recovery (2026-08-14)

This append-only handoff records the production v33 property-location update. It does not merge the Sites-internal repository into this research branch.

## Recovered current properties

| propertyId | building | recovered address | public address source | official address-point result | exact facility point result |
|---|---|---|---|---|---|
| `BLDG-21b1cd29cf39` | ヒルトップ北沢 | 東京都世田谷区北沢1丁目41-12 | https://www.next-life.co.jp/articles/43538/ | GSI exact address match, 35.661644 / 139.670670 | 368.919765 m, review 300–499 m |
| `BLDG-fb7b179e0575` | FAREウエハラノイエEAST | 東京都渋谷区上原2丁目42-10 | https://www.chintai-h.com/rent_view/16826 | GSI exact address match, 35.666481 / 139.681122 | 578.682842 m, pass 500 m |
| `BLDG-0b45ec5d310b` | メティス北沢 | 東京都世田谷区北沢5丁目5-10 | https://www.century21chintai.net/build-3001361/ | GSI exact address match, 35.669395 / 139.670471 | 673.493659 m, pass 500 m |

All three are `address_representative_point_only`. They are not building entrances, footprints, or parcel polygons.

## Canonical counts and builds

- property registry: `74eb94bdc20f2c69`
- representative-point facility exact: `e3f5a12d109d15a3`
- priority queue: `a78794058775977f`
- research KPI: `6c816c8b95549779`
- representative points: 55 total / 52 public
- public exact bands: pass 25 / review 23 / below 300 m 4
- current properties: point 54 / geocode waiting 0 / address recovery 38
- building polygons: 0 / parcel polygons: 0
- saved rank, score, automatic exclusion changes: 0 / 0 / 0

## Drive lineage

Canonical spreadsheet: `1hZdcDj1rxz-WWFG0VpqcAYEj0kjfNVxG7ykM2BdwhRI`

New immutable tabs:
- `物件正規化台帳_v4`
- `サイト同期_v33`

New artifacts:
- geocode cache: `1IbINehB-SHQyV33RtI0FG3FqBgYCXet6`
- registry: `1HmPtJzyBhibwzb98qa7d0T7RUTv8adTM`
- position evidence: `1FMulQqnTrMO_Ygd_flcO4Zgmxqtp_E-Q`
- exact distances: `1I3PXfvaNZJReZ16aBRpO8qkCXRNcXw2E`

Historical 100 m research ledger remains 314 unique / latest 0316 / next 0317; property address recovery was intentionally not inserted into that history log.

## Sites release

- Sites source commit: `e252b4573f88e99aa6ac4f6cc3f0db710d096a57`
- version: 33
- version id: `appgver_a214bdfb0d188191a0772a6e188b9357`
- deployment: `appgdep_6a7e559cd68481919ae56b941289ed0e`
- live: https://iyashiro-map.tomotakaoshi.chatgpt.site
- verification: lint, production build, 59/59 tests, authenticated live health/readback all passed

The next acquisition lane remains the 38 current properties with partial/town-only addresses, followed by building-footprint and parcel evidence. No ranking mutation is allowed before verified geometry and independent QA.
