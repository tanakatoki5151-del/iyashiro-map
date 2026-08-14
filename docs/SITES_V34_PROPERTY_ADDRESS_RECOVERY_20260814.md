# Sites v34 — property address recovery batch (2026-08-14)

## Outcome

The unified execution lane recovered seven additional current-property addresses from public property pages, required exact municipality/town/chome/ban/go matches from the GSI address search, and recomputed representative-point distances against the frozen 2026-07-30 OSM temple/shrine/cemetery geometry.

This is an append-only integration checkpoint. It does **not** change the saved town ranking, any score, or automatic exclusion.

## Recovered properties

| propertyId | building | normalized address | representative-point result |
|---|---|---|---|
| BLDG-4e6c9a14c783 | レオパレス駒場東大前 | 東京都目黒区駒場4-3-21 | 481.7m / review |
| BLDG-46aa82ef4602 | プラウドフラット代々木八幡 | 東京都渋谷区富ヶ谷2-16-11 | 559.2m / pass |
| BLDG-4fba2f3f2b3d | REVE下北沢 | 東京都世田谷区北沢4-10-4 | 254.1m / below 300m |
| BLDG-93938ded8937 | フォルム代沢 | 東京都世田谷区代沢2-25-18 | 172.5m / below 300m |
| BLDG-5a68c03a1947 | T's garden都立大学II | 東京都目黒区八雲5-14-7 | 268.6m / below 300m |
| BLDG-a280b5e1be92 | コロナビレッヂ | 東京都目黒区目黒本町5-8-6 | 367.0m / review |
| BLDG-c404c81c08a5 | プリュメゾン駒沢 | 東京都目黒区東が丘1-16-26 | 480.2m / review |

All results are for the address representative point only. They are not building- or parcel-wide conclusions.

## Deterministic artifacts

- property registry build: `362a0bf3614cf7ba`
- representative-point facility build: `8ab531abc4317f8f`
- research priority build: `bec5398421d81b35`
- research KPI build: `9f21fff28d552368`
- total representative points: 62
- public representative points: 59
- current properties with a point: 61 / 92
- current address-recovery queue: 31
- building polygons: 0
- parcel polygons: 0
- public bands: 26 pass (>=500m), 26 review (300–499m), 7 below 300m

## QA and publication

- 59 / 59 tests passed
- lint passed
- production build passed
- authenticated live API verified 59 public points and withheld all 3 internal-only points
- Sites source commit: `88bd287830bcdeba35e6abd7436ff05c92222f01`
- Sites version: 34
- deployment: `appgdep_6a7e5a9d95788191aa71c077aff238ff`
- live URL: https://iyashiro-map.tomotakaoshi.chatgpt.site

## Drive lineage

New immutable tabs:

- `物件正規化台帳_v5`
- `サイト同期_v34`

New v34 artifacts:

- geocode: `161unCm8pQhqunftFgqvEpDGGp1GLWCsC`
- registry: `1L5u8wZIJeFRmKjfbCcfAXIu7CHa1Yui1`
- evidence: `1VsS4pbWF1oTcwkzjAoNbK4zfU9puB02d`
- exact distance: `1YsP8KqYKk91-rfxdz0hJyfh7eTA_8SZI`

The historical 100m research log remains 314 unique / latest 0316 / next 0317 because this property acquisition batch belongs to the P5 property registry, not the historical cell-research denominator.
