# Sites v35 property address recovery — 2026-08-14

## Result

Recovered eight additional number-level property addresses from public property pages, verified exact municipality/town/chome/ban/go token matches with the official GSI address search, assigned each representative point to the frozen 100 m grid, and recomputed point-to-feature distances against the frozen 2026-07-30 OSM temple/shrine/cemetery geometries.

- Current-snapshot properties: 92
- Representative points: 69 (up from 61)
- Remaining address recovery: 23 (down from 31)
- Total point evidence: 70; public: 67; internal-only withheld: 3
- Public point-distance bands: >=500 m 27; 300–499 m 31; <300 m 9
- Building polygons: 0; parcel polygons: 0
- Ranking, score, and automatic-exclusion changes: 0 / 0 / 0

## Newly recovered addresses

| Property | Verified address | Cell model result |
|---|---|---|
| エクセル河原 | 東京都大田区中馬込1丁目20-3 | witnessed mixed / reversal |
| サンハイツ | 東京都世田谷区代沢2丁目48-9 | model all-pass |
| クロスロード | 東京都世田谷区代沢2丁目12-12 | model all-fail |
| パルムハイツ | 東京都目黒区目黒本町5丁目27-3 | witnessed mixed / recovery |
| デュエル・ヤト | 東京都目黒区東が丘1丁目2-9 | witnessed mixed / recovery |
| ザ・クラス下北沢 | 東京都世田谷区北沢4丁目8-29 | model all-fail |
| レオパレス参丁目 | 東京都世田谷区北沢3丁目29-6 | model all-fail |
| blooming NAKAMAGOME | 東京都大田区中馬込1丁目6-9 | model all-fail |

These are address representative points only. They are not building entrances, building footprints, or parcel geometries.

## Reproducible builds

- Property registry: `f35f13a5a9778da6`
- Representative-point exact facility distances: `7548e6f6af9bdc11`
- Research priority queue: `0c7d8dca41db2977`
- Research KPI: `c1c2a9e457143178`
- Sites source commit: `02bcc9c9d471492127a771d667183df9686260c4`
- Sites version: 35
- Deployment: `appgdep_6a7e5f4ec2908191a62096b5f637bb77`
- Live URL: https://iyashiro-map.tomotakaoshi.chatgpt.site

## Drive checkpoint

- Immutable Sheet tab: `物件正規化台帳_v6`
- Immutable Sheet tab: `サイト同期_v35`
- Address geocodes: `1R_w_50JPbZb7h-H2vVjX2av8oH0XEHhf`
- Registry: `1AdIvqGQlf9hOyGh_B9gvRmQb6kdlDOF9`
- Position evidence: `1YtKEbcQrYGn5McsVRT43FjwNjt1wcKrM`
- Exact point distances: `1P3iPtRpcxza0PDXlkqjIK70gW5NpSKDU`

## Verification

- `npm run lint`: pass
- `npm test`: 59/59 pass
- Deterministic registry, exact-distance, priority-queue, and KPI checks: pass
- Authenticated live APIs: 69 current representative points, 23 address-recovery items, 67 public point rankings, 3 internal-only records withheld
