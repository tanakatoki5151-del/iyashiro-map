# ECOSCAPE F11 暫定ランキングロジック

Build: `ecoscape-green-quality-f11-fixed60-fulljoin-ranking-v1-20260820`

## 原則

このランキングは **審査用の暫定順位** であり、B114/B115/B116/B120の正本を変更しない。
単純な100点加算ではなく、まず帯を決め、同じ帯の中だけを並べる。

## 1. 純環境セル順位 120,662

### 帯
1. `S_ROBUST_STRONG_REDUNDANT`
   - 20/25/30%の全設定で候補
   - P25でSTRONG
   - 注意柱0
   - 4本柱のどれを外しても候補が残る
   - 一要因依存でない
2. `A1_ROBUST_STRONG`
3. `A2_ROBUST_CANDIDATE_REDUNDANT`
4. `B_ROBUST_CANDIDATE`
5. `C_POINT_CANDIDATE_NOT_ROBUST`
6. `D_NEUTRAL`
7. `E_MIXED`
8. `F_CAUTION`
9. `U_UNKNOWN`

### 同じ帯の中の順番
- P25状態
- 閾値安定性
- 注意柱の少なさ
- 好条件柱の多さ
- 1柱を外しても残る回数
- 一要因依存でないこと
- 500m、300mの候補連続性
- 4柱の周辺好条件率
- データ充足
- 磁気背景の尺度安定性
- cellId

磁気は帯を跨がせず、最後のタイブレークにしか使わない。
`environmentRankNoMagF11`も同時出力し、磁気による並べ替え量を監査可能にする。

## 2. 住宅セル順位 120,662

### 帯
1. `S_RESIDENTIAL_ROBUST_STRONG_ZONE_A`
2. `A_RESIDENTIAL_ROBUST_ZONE`
3. `B_RESIDENTIAL_ROBUST_SPOT`
4. `C_RESIDENTIAL_PLAUSIBLE_ENV_ROBUST`
5. `D_RESIDENTIAL_PLAUSIBLE_POINT`
6. `E_RESIDENTIAL_PLAUSIBLE_OTHER`
7. `F_NONRESIDENTIAL_OR_UNKNOWN`

住宅順位でも市場の空室、家賃、住戸条件は入れない。
公園・空港・事業所などが住宅可能性ゲートをすり抜ける場合があるため、NEXUS市場ゲート前の地理的候補順である。

## 3. 17外部セルの緑質順位

60生活圏の分布を固定し、17セル内で基準を作り直さない。

- 活力: 盛夏NDVI/EVI/NDREを60生活圏の経験分布へ照合
- 水分: 盛夏NDMIを同じ固定分布へ照合
- 熱: 複数夏LSTを同じ固定分布へ照合
- 季節安定、秋の回復、長期傾向
- B114都市形状と300m/500m連続性
- B118地下・水
- B101磁気背景
- B120住所・住宅候補状態

正式な湿重い負ラベル、清潔感点、実測風速は含めない。

## 4. 同格群

細かな順位の過剰解釈を防ぐため、磁気とcellIdを除く主要条件が同じセルを `EquivalenceGroup` として併記する。
同格群内の1位と2位は、意思決定上ほぼ同等である。
