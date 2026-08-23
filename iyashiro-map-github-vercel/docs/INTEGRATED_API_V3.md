# Integrated API v3

最終更新: 2026-08-23

住所・座標・物件URLをcanonical 100m cell、統合データ、R3 personal policy、HOUSE_COMPASS_LABへ接続する本番APIである。AIによる自由採点は行わず、UNKNOWNを安全・不存在へ変換しない。機械可読な正本は `/openapi-v3.json` とする。

## Endpoint

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v3/releases` | 検証済みの現行evidence release identityを公開 |
| GET | `/api/v3/dossier` | 地図ピンまたは住所から、同じ形式の総合土地カルテを作成 |
| POST | `/api/v3/resolve` | 住所または座標を不確実性付きcanonical cell集合へ解決 |
| GET | `/api/v3/cells/{cellId}/profile` | release/source/coverage付きFact Envelopeと各レイヤーを取得 |
| GET/POST | `/api/v3/properties/intake` | 対応サイト一覧／単一物件ページの安全な取込と手動fallback |
| POST | `/api/v3/assess` | intake、resolve、profile、固定policy、任意HCLを一括実行 |
| POST | `/api/v3/compare` | compact token、署名済み旧snapshot、またはlive入力を比較 |
| POST | `/api/v3/house-compass` | bounded HCL engineのみ実行 |

POSTは `Content-Type: application/json` または `application/*+json` を必須とする。cross-site `Sec-Fetch-Site` と不一致Originを拒否する。body上限はcompare以外64KiB、compareは2MiBである。

## Release catalog

`GET /api/v3/releases` は次の公開最小情報だけを `Cache-Control: no-store` で返す。

```json
{
  "schemaVersion":"iyashiro-release-catalog/1.0",
  "checkedAt":"2026-08-23T00:00:00.000Z",
  "readiness":{"status":"ready","manifestValidated":true},
  "current":{
    "evidence":{
      "releaseId":"...",
      "sha256":"64桁hex",
      "dataContract":"integrated-cell-profile/3.0"
    },
    "generatedAt":"2026-08-23",
    "sourceSchemaVersion":"..."
  }
}
```

内部source、pointer、coverage、policyは公開しない。`manifestValidated:true` はmanifestのrelease/source/QA宣言、期待する624 row path宣言、coverage countの整合を確認した意味であり、全row artifactの内容やhashを毎回先読みしたという意味ではない。readinessを確認できない場合は503 `integrated_data_unavailable` とし、後続lookupで欠落rowを検出した場合もfail-closedする。

## 土地カルテ：地図と住所の共通入口

`GET /api/v3/dossier` は、最初の地図でピンを立てた場合と、住所を入力した場合を、同じ `land-dossier/1.0` 応答へ集約する。旧来の番号中心の診断を入口にせず、一地点について現在見られる情報と、まだ足りない情報を一続きで返す。

座標入力:

```text
/api/v3/dossier?lat=35.6895&lng=139.6917&label=選択地点
```

住所入力:

```text
/api/v3/dossier?q=東京都新宿区西新宿2丁目8-1
```

- `lon` は `lng` の別名、`address` は `q` の別名である。
- 座標は `lat` と `lng`（または `lon`）を必ず組にする。片方だけなら400で停止する。
- 座標と住所が同時に来た場合は座標を地点証拠として使い、`label` や住所文字列は表示用の補助名に限る。
- 住所だけの場合は既存のcanonical resolveを通し、住所の誤差で生じた最大25候補区画を同じ基準で確認する。
- 応答は `Cache-Control: no-store` で返す。

読み順は次のとおり固定する。

1. 第一段階の絶対回避条件
2. 一本目の土地軸「イヤシロジ（＝テライン仮説）」
3. 二本目の独立した土地軸「龍脈」
4. 地形、水、地盤、歴史、周辺施設
5. 地名・土地名の由来
6. まだ足りない情報と次に調べること

第一段階は500mを固定基準とし、寺院、墓地、大規模・入院病院、強い歴史事象、P8重大履歴を確認する。一つでも閾値内なら `avoid` であり、後段の好材料で相殺しない。全候補区画・全対象資料の確認が揃った場合だけ `current_clear` とし、UNKNOWN、source-limited、未走査、未接続、住所範囲の一部欠落は `review` に残す。未発見を「存在しない」「安全」とは読まない。

土地そのものの二本柱は混ぜない。

- イヤシロジ（＝テライン仮説）は、現行 `V15.3` と変化を見るための比較用 `V10` だけを返す。版と計算方法が違うため平均しない。
- 龍脈は独立した順位・ゾーン・水系状態として返し、イヤシロジ順位と合算しない。
- V11〜V14は削除せず `versionGuide.archivedFromNormalView` に記録するが、通常画面の現行判断には表示しない。

`sections` は `terrain`、`water`、`ground`、`history`、`facilities` の5区分である。各項目は日本語の要約、意味、確認範囲、根拠を持つ。地名由来を地点へ確実に結び付けられない場合は推測で文章を作らず、画面では情報不足、`missingInformation` では追加探索対象として示す。公開応答はこの構造化済み情報だけを返し、内部監査用の元応答やDrive内の保存先は返さない。

## Resolve

入力例:

```json
{"address":"東京都新宿区西新宿2丁目8-1","sigmaM":80}
```

```json
{"lat":35.6895,"lon":139.6917}
```

`routeId` は入力契約に存在せず、クライアント指定を証拠として信頼しない。座標は `USER_COORDINATE`、通常住所は `GSI_JUKYO_BASE_NUMBER`、物件ページ抽出住所は `PROPERTY_PAGE_ADDRESS` とサーバーが決める。requested `sigmaM` は証拠下限より大きくする場合だけ有効で、各routeの下限は順に5m、50m、65mである。

住所と座標を併記した場合は両方を検証し、GSI結果との距離が250mを超えると422 `address_coordinate_mismatch` で停止する。広域住所や丁目・番地等がない住所は422 `address_precision_insufficient`、住所町域・番号tupleが一致しない検索結果は422 `address_match_inconsistent` とする。

canonical gridはround-to-nearestを使う。

- `A_LAT=35.839647862019405`
- `B_LAT=-0.0008983111749910168`
- `A_LON=139.43`
- `B_LON=0.0011042452218025757`
- 624×462、valid 120,662 cells、JGD2011 / EPSG:6668

Gaussian massは再正規化しない。最大25候補だけを返し、切り捨てtailは `coverage.omittedWeight`、valid台帳で棄却したmassは `rejectedWeight` に残す。`VALIDATED` はvalid候補のraw massが0.95以上で棄却がない場合だけで、`PARTIAL` と `NO_VALID_CELL` はpassへ昇格しない。

統合runtimeのreadinessまたはartifactが欠損した場合、resolve、assess、live compareは200の `RUNTIME_UNAVAILABLE` や `NO_VALID_CELL` へ変換せず503で停止する。`RUNTIME_UNAVAILABLE` は既存型・署名済み互換artifactの識別値として残るが、現行APIのruntime障害fallbackではない。

## Cell profileとFact Envelope

`profile.layers` はruntimeのrich objectを保つ。

- `V15_3`: `layers.r3.v15`
- `RYUMYAK`: `layers.r3.ryumyak`
- `ORBIT`: `layers.orbit`
- `R3_PERSONAL_GATE`: `layers.r3`
- `HISTORY_P8`: `distances.p8`
- `LEGACY_CONTEXT`: `layers.r3.context`

`profile.rankings` は `sourceFirst`、`robustness`、`v15Pure`、`ryumyakPure` の4 viewを分離する。V15/RYUMYAKはcell順位である。Source-first/RobustnessはArea Family順位で、全cell membershipがないため推測配賦せず `rank:null, coverage:"unknown"` とする。

各factはrelease、sources、coverage、finding、policy effectを持つ。距離が閾値外でもcoverageがpartial/unknownなら `finding.status:"review"`、`finding.value.triggered:null` を保つ。不存在主張は許可しない。

## R3 personal policy

```json
{"distanceThresholdM":500,"includeShrines":false}
```

閾値は300/500/650m。距離既知時は選択閾値で再計算し、境界値を含む `distanceM <= threshold` がhard vetoである。runtime既定500mの `triggered` を別閾値へ流用しない。

- hard gate: temple、cemetery、large hospital、strong history、P8
- off: shrine、general hospital
- `includeShrines:true` の場合だけshrineをhard gateへ追加
- hard gateは非補償で、他の好材料と相殺しない
- UNKNOWN、source-limited、location partialはreview
- `NO_VALID_CELL` は地理的out-of-scope
- runtime/readiness障害は判定に含めず503

応答の適用済みpolicyは入力2項目に加え、`id:"R3_DEFAULT"`、`hardGateNonCompensatory:true`、`unknownDisposition:"review"` を必ず含む。

## Property intake

入力は `propertyUrl` と任意の `manual`。manualはname、address、station、areaM2（numberまたは非空numeric string）、layout、memoを受ける。

結果は次を分離して保存する。

- `snapshot.requestedUrl`、`finalUrl`、`fetchedAt`
- `provenance.extracted` と `manualOverrides`
- 最終マージ値と `extraction.status`

自動取得はexact allowlistのHTTPSだけである。URL 2,048文字、総時間8秒、redirect 3回、HTML 1.25MBを上限とし、各redirectでhostとDNSを再検証する。credentials、fragment、非標準port、localhost、private/reserved IP、IPv4-mapped IPv6、特殊IPv6帯、multicastを拒否する。blocked、timeout、HTTP/DNS/size失敗は推測値へせず、200の明示的manual fallbackとして返す。

assessでは物件ページが丁目までの粗い住所でも、同一町域のmanual番地による精緻化は許可する。別町域・別住所の証拠混在は422 `address_evidence_conflict` で停止する。

## Assess

主な入力:

```json
{
  "clientCandidateId":"saved-001",
  "propertyUrl":"https://suumo.jp/...",
  "manual":{"address":"東京都新宿区西新宿2丁目8-1","areaM2":"42.5"},
  "policy":{"distanceThresholdM":500,"includeShrines":false},
  "hcl":{"entranceDirection":"南","kitchenDirection":"東","concerns":["騒音"]}
}
```

応答は `candidateId`、client identity、`evidenceRelease`、property、resolution、primary profile、最大25件のweighted `candidateCellProfiles`、適用済みpolicy、decision、任意houseCompassを返す。同一建物の別部屋もclient id、物件条件、ordinalをcandidate identityへ含める。

`evidenceRelease` は `{releaseId, sha256, dataContract:"integrated-cell-profile/3.0"}` の完全identityである。`sha256` はrelease metadataに正規のdigestがあればそれを使い、なければcanonical metadataからAPIが生成した64桁SHA-256を使う。

比較署名secretを利用できる場合、assessは次の2つを付ける。

- `comparisonToken`: `iyashiro-comparison-candidate/1.1` のcompact HMAC token
- `snapshotSignature`: full assessment互換経路のHMAC署名

compact tokenは `ct1` 形式、payload最大24KiB、wire最大32,837文字、発行から最大24時間である。tokenは署名済みだが暗号化されていない。含む値はcandidate/client IDs、発行・失効時刻、evidence release、propertyの表示用name/address、resolutionのprimary cellとcoverage要約、candidate cellのcellId/weight/profile availability、共有policy、集約decision、ranking basisだけである。

物件URL、full snapshot、provenance、memo、station、layout、HCL入力・report、profile facts、座標、disclaimerはtokenへ入れない。表示用name/addressも秘匿情報として扱い、tokenをログへ記録したり第三者へ共有したりしない。

## Compare

4 modeのうち、入力collectionはちょうど1つだけ指定する。

### Compact token mode（推奨）

```json
{
  "tokens":["ct1....","ct1...."],
  "policy":{"distanceThresholdM":500,"includeShrines":false}
}
```

2〜20 tokenと共有 `policy` が必須である。HMAC、24時間window、現在の `evidenceRelease` 3項目、共有policyを検証し、外部URL、GSI、profile artifactを再取得しない。同じtokenの重複、または復元後の同じ `clientCandidateId` は400で拒否する。

### Signed legacy snapshot mode

`snapshots` またはalias `assessments` に、assessが返したfull responseを2〜3件だけ渡す。full assessment全体のHMAC、現在のevidence release、共有policyを検証する。4〜20件はcompact tokenを使う。署名対象外のfieldを反射する互換経路ではない。

### Live mode

`candidates` にAssess入力を2〜20件渡す。最大8 workerで各候補を新規assessmentし、URLやGSIも必要に応じて取得する。body level policyを省略する場合は全候補のpolicyが同一でなければ400とする。

### Conflict、partial failure、応答最小化

期限切れ・改ざん・形式不正は400、tokenまたはsnapshotのpolicy conflict、stale/current不一致、cross-releaseはtop-level 409である。署名secretが使えないtoken/snapshot比較と、runtime readinessがないlive比較は503である。

409 conflict以外の候補単位エラーは、成功候補を失わせず200応答の `failures` に入力ordinal、client id、error、status、messageを残す。`requestedCount/completedCount/failedCount` と入力順を保持する。

各 `results[]` は表示に必要な最小値だけを返す。propertyはname/address、resolutionはprimary cellとcoverage、`profile:null`、`houseCompass:null`、candidateCellsはcellId/weight/profileAvailable/`profileIncludedInResponse:false` である。物件URL、memo、HCL、profile factsを再掲しない。

明示的なcell-addressable Source-first根拠がなければ `ordering.rank:null`、`tie:true` とし、根拠のない1位・2位を作らない。hard vetoは非補償、UNKNOWNはreviewのままである。

## HOUSE_COMPASS_LAB

方向fieldは8方位label、または0〜359度を含むstringだけを受ける。JSON numberはcompact入力でもfull `form` でも拒否する。寝室、机、枕、築年帯、自由懸念はcontext-onlyとして扱う。合計点、多数決、健康・財運予測を生成しない。

## Statusと運用境界

| Status | Meaning |
| --- | --- |
| 400 | 不正JSON/input、曖昧collection、重複token/client id、期限切れ・不正署名 |
| 403 | cross-siteまたはOrigin不一致 |
| 404 | cell不存在など |
| 409 | stale/cross release、token/snapshot policy conflict |
| 413 | body上限超過 |
| 415 | JSON以外のPOST |
| 422 | 住所精度・座標・住所証拠の不一致 |
| 500 | 予期しない内部失敗 |
| 502 | geocoder等upstream応答失敗 |
| 503 | integrated data/readinessまたは比較署名機能が利用不能 |
| 504 | upstream timeout |

property fetch fallbackとcompareの候補単位failureは、上記top-level errorと区別して200応答内で明示する。

比較署名secretは `IYASHIRO_COMPARE_SNAPSHOT_SECRET`（32文字以上）を優先する。専用secretがない場合の派生鍵はpreview限定で、`VERCEL_ENV=preview`、32文字以上の `VERCEL_AUTOMATION_BYPASS_SECRET`、project identity、`VERCEL_URL` がすべて揃う場合だけ、domain-separated HKDFで生成する。production fallbackはない。

Vercel Firewall、rate limit、または認証で高コストPOSTを保護する。exact host allowlistとredirect再検証を行うが、標準fetchではDNS lookupから接続先IPをpinできないためDNS rebinding TOCTOUは残留制約である。

このAPIは候補整理・調査支援であり、科学的効能、健康、財運、資産価値、法令適合、契約判断を保証しない。現地、募集元、公的台帳、重要事項説明で確認する。
