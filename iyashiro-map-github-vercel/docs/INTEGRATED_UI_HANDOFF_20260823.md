# /integrated UI handoff — 2026-08-23

## 完成範囲

- 画面: `/integrated`
- 入力: 住所、緯度・経度、物件URL、物件情報の手動補正
- ポリシー: 寺・墓地・大病院の共通距離閾値 300 / 500 / 650m（既定500m）
- 神社: 既定OFF。ユーザーがONにした場合だけ距離ゲートへ含める
- HCL: 玄関、寝室、仕事机、台所、就寝時の頭方位、築年帯、懸念事項
- 判定: `POST /api/v3/assess`
- 比較: セッション内で最大20候補を保持し、`POST /api/v3/compare`
- 表示: R3 / V15.3 / RYUMYAK / ORBIT / 歴史 / HCLを独立カード化
- 順位: Source-first / Robustness / Pure V15.3 / Pure RYUMYAKを独立表示

## 意図した安全境界

- HARD-VETOは非補償型。別レイヤーの順位や評価で相殺しない。
- UNKNOWN、未接続、API未提供、対象外は「安全」へ変換しない。
- UI独自の総合点、ローカル順位、疑似AI判定を作らない。
- 比較順はサーバーの `tier -> sourceRank` のみを表示する。
- API失敗時はエラー状態だけを表示し、モック・代替結果を表示しない。
- HCLは土地ゲートへ加算せず、bounded fail-closedの別レイヤーとして表示する。
- 健康、資産価値、将来結果の保証は行わない。

## Assess request

```json
{
  "candidateLabel": "任意",
  "address": "任意",
  "lat": 35.0,
  "lon": 139.0,
  "propertyUrl": "https://...",
  "manual": {
    "name": "任意",
    "address": "任意",
    "station": "任意",
    "areaM2": "任意",
    "layout": "任意",
    "memo": "任意"
  },
  "policy": {
    "distanceThresholdM": 500,
    "includeShrines": false
  },
  "hcl": {
    "entranceDirection": "任意",
    "bedroomDirection": "任意",
    "workDeskDirection": "任意",
    "kitchenDirection": "任意",
    "headDirection": "任意",
    "buildingAgeBand": "任意",
    "concerns": "任意"
  }
}
```

住所、緯度・経度の組、物件URL、`manual.address` のいずれかが必要。クライアントでも事前検証し、サーバー検証を代替しない。

## Compare request

```json
{
  "candidates": ["保存済みAssessRequestを2〜20件"],
  "policy": {
    "distanceThresholdM": 500,
    "includeShrines": false
  }
}
```

画面は保存済みのAPI応答を比較材料として再送しない。正本判定を再現するため、元のAssessRequestを送る。

## Response adapter

`app/components/integration/api.ts` は確定V3契約を第一に読み、profile配下のfact envelopeについて以下の別名も許容する。

- R3: `r3`, `R3`, `spiritualGate`, `integratedGate`
- V15.3: `v153`, `v15_3`, `v15`, `terrain`
- RYUMYAK: `ryumyak`, `RYUMYAK`, `dragonVein`
- ORBIT: `orbit`, `ORBIT`, `facilityDistances`, `distances`
- 歴史: `history`, `historical`, `placeGraph`, `veil`
- HCL: `houseCompass`, `hcl`, `HCL`, `houseCompassLab`

レイヤーが見つからない場合は空データを補完せず「API未提供」と表示する。

## Candidate state

候補はReact stateだけに保持する。localStorage、sessionStorage、Cookieへ物件情報を書かない。再読み込みで消えることを画面に明記する。

## Verification

依存関係を使わない静的テスト:

```text
node --test tests/integrated-ui.test.mjs
git diff --check -- app/integrated app/components/integration tests/integrated-ui.test.mjs
rg "?" app/components/integration app/integrated tests/integrated-ui.test.mjs
```

Gドライブ上のnode_modulesは利用しない。TypeScript、lint、Next build、ブラウザ確認はCドライブの隔離コピーで行う。

## Parent integration

`app/page.tsx` のトップ画面から `/integrated` へのLinkを接続済み。
