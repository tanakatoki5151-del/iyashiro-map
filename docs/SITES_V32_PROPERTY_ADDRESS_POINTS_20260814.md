# Sites v32 property address-point integration — 2026-08-14

This handoff records the independently verified runtime integration completed after the external research lane stopped.

## Immutable runtime checkpoint

- Sites project: `appgprj_6a69e17f5f7481919e4fb39c4b3d282c`
- Production version: **32**
- Sites source commit: `57e270e8e2bf4248e3c26cf6d4f00113c3c5be24`
- Production deployment: `appgdep_6a7e4fe88bdc8191aa62973bad8a8c3d`
- Live URL: https://iyashiro-map.tomotakaoshi.chatgpt.site
- Release QA: **59/59 tests**, lint, production build, authenticated live `/api/health` readback all passed.

## Property position results

- Property registry build: `5d07ae0815b78dd1`
- Representative-point exact-distance build: `c36bd05e27bc7a6b`
- Priority queue build: `2ef0f43759a7f3e5`
- Research KPI build: `9e6d21d215ac1e5c`
- Current properties: 92
- Current representative points: 51
- Full-address geocode backlog: 0
- Address-recovery backlog: 41
- Building polygons: 0
- Parcel polygons: 0
- Cached GSI address representative points: 38/38 exact municipality/town/chome/ban/go matches.
- Frozen-geometry direct distances: 52 total points / 49 public points.
- Public point bands: 23 at least 500m, 22 at 300–499m, 4 below 300m.

These are **representative-point-only** results. They do not prove that an entire building or parcel passes.

## Drive lineage

Canonical spreadsheet: `1hZdcDj1rxz-WWFG0VpqcAYEj0kjfNVxG7ykM2BdwhRI`

New append-only tabs:
- `物件正規化台帳_v3`
- `サイト同期_v32`

Uploaded artifacts:
- GSI cache: `1ruu0lP40zl8ZbhHzAdho8jHApiOsS0dZ`
- Registry: `1NYk_N6Wz1p8SxEYVRd3cJRJHTSpKn5-i`
- Position evidence: `1fpmzwIcSaBpxbfL39Ve5o4z_97PIuJEK`
- Exact point distances: `1Ls3auTHIa5ZuJFT9V5721gUlrCDiB6S0`

The operational history ledger remains 314 unique logs, latest `RLOG-V10-0316`, next `RLOG-V10-0317`. Address geocoding was not mixed into the historical 100m research log.

## Decision gate

Ranking order changed: **false**  
Score changed: **false**  
Automatic exclusion changed: **false**

The next acquisition lane is the remaining 41 addresses and then building/parcel geometry, while independent join/QA remains separately gated.
