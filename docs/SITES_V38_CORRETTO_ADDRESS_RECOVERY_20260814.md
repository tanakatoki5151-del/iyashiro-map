# Sites v38 — Corretto address recovery (2026-08-14)

## Result

The v38 P5 property-location batch safely recovered one additional current property:

| propertyId | building | verified address | public source | official address point | frozen-geometry result |
|---|---|---|---|---|---|
| `BLDG-5e2ba6610c41` | Corretto | 東京都目黒区東が丘2丁目3-3 | https://www.homes.co.jp/archive/b-34402177/ | GSI exact address match, 35.630569 / 139.665039 | 426.672243 m, review 300–499 m |

The assigned frozen-grid cell is `107859`. Its fixed-geometry outcome is witnessed `mixed / recovery`: the cell contains a >=500 m witness, while this actual address representative point is below 500 m. This is exactly why cell-center exploration and property-point assessment must remain separate.

The point distances are:

- temple: 472.401046 m
- shrine: 530.102459 m
- cemetery: 426.672243 m
- minimum: 426.672243 m

This is an **address representative point only**. It is not a building entrance, building footprint, parcel polygon, or whole-property conclusion.

## Canonical counts and deterministic builds

- current properties: 92
- current representative points: 73
- remaining address recovery: 19
- full-address point wait: 0
- total representative points: 74
- public representative points: 71
- internal-only points withheld: 3
- cached GSI address representative points: 60
- public bands: pass >=500 m 27 / review 300–499 m 34 / below 300 m 10
- all-point bands: 28 / 35 / 11
- building polygons: 0
- parcel polygons: 0
- property registry build: `91986c6b229ee3bf`
- representative-point facility build: `193f4c86e38a8b62`
- research priority build: `9c9291e83dfc8c31`
- research KPI build: `bc7588158a52762a`
- coordination version: `research-coordination-v1-20260814-batch31-address-recovery`

## Sites release

- Sites project: `appgprj_6a69e17f5f7481919e4fb39c4b3d282c`
- Sites internal source commit: `8286b89fbb9cbaf96d5ca83c23bfe3dbdf9ee2ad`
- version: 38
- version id: `appgprj_6a69e17f5f7481919e4fb39c4b3d282c~appgver_e1df2f4ca8a48191bafeaaf90851c324`
- deployment: `appgdep_6a7e688050248191b9148d8e28de26fb`
- live: https://iyashiro-map.tomotakaoshi.chatgpt.site
- QA: lint, production build, 59/59 tests, deployment success, and authenticated live API readback passed

## Drive lineage

Canonical spreadsheet: `1hZdcDj1rxz-WWFG0VpqcAYEj0kjfNVxG7ykM2BdwhRI`

New immutable tabs:

- `物件正規化台帳_v8` (sheetId `1620677072`)
- `サイト同期_v38` (sheetId `1172373929`)

New immutable artifacts:

- geocode source: `10xbtZIGFlxiWTiABu2zPql0jZnQvP5HL`
- registry: `1BDHD295A6HTTZoMf9H5cJaUH4OcuCWA3`
- position evidence: `188Xg6Zp-D4D1BTMvI14ium2lxfaJPvhw`
- exact representative-point assessment: `1kTNcQ5Pw6jqEqjc7xb313VhyhRThhkat`

`並行研究管制_v1` was updated to current readiness 73/92 (79.348%) and address recovery 19. The historical research ledger remains 314 unique, latest `RLOG-V10-0316`, next `RLOG-V10-0317`; property-address work is intentionally not mixed into the historical-cell denominator.

## Decision gate

- saved ranking order changed: **false**
- score changed: **false**
- automatic exclusion changed: **false**

Next non-blocking lane: evidence-gated recovery of the remaining 19 property addresses, then building-footprint and parcel evidence. Identity-conflicted candidates remain withheld rather than being forced into the registry.
