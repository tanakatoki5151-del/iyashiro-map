# ECOSCAPE Green Quality F8 Mega10

## Status
F7のNEXUS外部テストを、時系列だけの判定から、B114都市形態・B118地下水文脈・B101磁気背景へexact joinした。
これは正式ランキングではなく、300m中心・500m背景の説明カルテを作るためのF8 holdout gateである。

## Main results
- exact temporal/static join: 10/10
- temporal coverage pass: 10/10
- 3軸すべて20/25/30で安定: 5/10
- wet-heavy supported: 0/10
- stress/decline supported: 0/10
- maintenance/cleanliness known: 0/10

## Important corrections
1. 高い水分だけで湿重いにしない。
2. 熱いだけでも湿重いにしない。湿重さには地下・旧水系と閉鎖/停滞形状を必要とする。
3. 開放形状なのに暑い場所は、風通しと涼しさを分けて説明する。
4. 冬は落葉診断であり活力減点にしない。
5. KartaView 0/30のため、清潔感はUNKNOWNのまま。
6. 磁気は補足・将来の同格tie-breakだけで、順位や候補を変更しない。

## Gate decision
- vitality: holdoutで説明利用PASS、60-area gate待ち。
- moisture: multi-factorで説明利用PASS、60-area gate待ち。
- heat: 説明利用PASS、60-area gate待ち。
- ventilation: context利用PASS、実測風速ではない。
- maintenance: current source NO-GO。
- total score / formal ranking: HOLD。

## Safety locks
- rankingEffect: none
- scoringEffect: none
- candidateOverride: 0
- PR #24 remains draft until the canonical period-specific 60-area artifact passes readback.
