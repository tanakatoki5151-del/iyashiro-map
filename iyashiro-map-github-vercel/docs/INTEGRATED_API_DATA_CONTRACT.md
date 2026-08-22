# Integrated data runtime contract

最終更新: 2026-08-23

APIは `app/lib/integrated-data/runtime.ts` をstatic importし、統合releaseを読み取り専用で参照する。APIから見たdata contractは `integrated-cell-profile/3.0` である。

## Public exports

```ts
export async function ensureIntegratedReleaseReady(): Promise<IntegratedReleaseMetadata>
export async function lookupIntegratedCell(cellId: string): Promise<IntegratedCellRecord | null>
export const releaseMetadata: IntegratedReleaseMetadata
export const INTEGRATED_RELEASE_METADATA: IntegratedReleaseMetadata
export class IntegratedArtifactMissingError extends Error {
  code: "INTEGRATED_ARTIFACT_MISSING"
}
export class IntegratedReleaseNotReadyError extends Error {
  code: "INTEGRATED_RELEASE_NOT_READY"
}
```

`ensureIntegratedReleaseReady` は `release-manifest.json` をstatic metadataと照合し、次を検証する。

- schema versionとrelease ID
- sourceのproject/version/SHA-256/logical pointer
- QA status `PASS` と `allGridRowsMaterialized:true`
- row shard count 624、`rows/g000.json` から `rows/g623.json` までのexact path宣言
- facility shard count 16
- valid/integrated/R3 lens/ORBIT/facility coverage counts

これはmanifest宣言のreadiness検証であり、全624 row artifactの内容やhashをrequestごとに先読みするものではない。対象cellのlookup時に該当row shardを読み、欠損・読取不能・不正JSONをその場でtyped errorにする。

次の3状態を区別する。

- 不正cellId、範囲外、存在row内の非valid cell: `lookupIntegratedCell(...)=null`
- manifestまたはrow shard欠落: `IntegratedArtifactMissingError`
- release QA・manifest整合・artifact読取が不成立: `IntegratedReleaseNotReadyError`

API adapterは後2つを503 `integrated_data_unavailable` に変換する。resolve、assess、live compare、release catalog、profile取得は障害を200の `RUNTIME_UNAVAILABLE`、`NO_VALID_CELL`、review、out-of-scopeへ変換しない。UNKNOWNを安全へ、欠落artifactを不存在へ変換しない。

## Runtime loading

Vercelでは統合corpusをFunction bundleへ重複traceせず、公開assetをself-fetchする。base URLは次の優先順位で決める。

1. `IYASHIRO_INTEGRATED_DATA_BASE_URL`
2. `VERCEL_URL`
3. `VERCEL_PROJECT_PRODUCTION_URL`

`VERCEL_AUTOMATION_BYPASS_SECRET` がある場合はpreview protection用headerを付ける。asset fetchは `force-cache` を使い、404はartifact missing、その他の非2xxとnetwork failureはrelease not readyとして扱う。

ローカル実行では `IYASHIRO_INTEGRATED_DATA_ROOT`、または `<cwd>/public/data/integrated` をNodeのbuiltin `fs` で読む。`fs` は `process.getBuiltinModule` と `turbopackIgnore` を使い、Vercel buildのwhole-project traceへ統合corpusを巻き込まない。

row shardはPromise単位の64-entry LRU cacheで保持する。同一rowの並行readを共有し、失敗したPromiseはcacheから削除して次回再試行を許可する。

## Public release identity

`GET /api/v3/releases` はruntime readiness成功後だけ、次の最小公開情報を返す。

- `schemaVersion:"iyashiro-release-catalog/1.0"`
- request時刻 `checkedAt`
- `readiness:{status:"ready",manifestValidated:true}`
- current evidence `{releaseId,sha256,dataContract}`
- release生成日（`YYYY-MM-DD` またはnull）とsource schema version

内部source、pointer、coverage、policyは公開しない。`manifestValidated:true` はmanifest契約の検証を示し、全row content/hashの先読み完了を示さない。

comparisonとassessmentの `evidenceRelease` は次の完全identityである。

```json
{
  "releaseId":"...",
  "sha256":"64桁hex",
  "dataContract":"integrated-cell-profile/3.0"
}
```

metadataに正規SHA-256がない場合、APIはcanonicalized release metadataのSHA-256を生成する。tokenと旧snapshotは3項目すべてが現在値と一致しなければ409とし、release IDだけの一致では受理しない。

## Cell record

必須identityは `cellId, gridRow, gridCol, lat, lon, valid`。存在だけでvalidと推測せず `valid === true` を要求する。

`distances` の正規キー:

- `temple`
- `cemetery`
- `largeHospital`
- `generalHospital`
- `shrine`
- `strongHistory`
- `p8`

各distance factは可能な範囲で `distanceM`、`coverage`、`decisionStatus`、`thresholdStatus`、`thresholdM`、`gateRole`、name/address/source情報を持つ。値がない場合に0や安全値を補わず、null/UNKNOWNを保持する。

ORBITのtemple/cemetery/hospital/shrineは全valid cellへmaterializeされるが、coverageはsource制約を保持する。R3のlargeHospital/strongHistory/P8は84,060 cellsのみ実値で、それ以外はUNKNOWNである。

## Layersとranking

API profileへの明示mapping:

| API layer | Runtime path |
| --- | --- |
| V15_3 | `layers.r3.v15` |
| RYUMYAK | `layers.r3.ryumyak` |
| ORBIT | `layers.orbit` |
| R3_PERSONAL_GATE | `layers.r3` |
| HISTORY_P8 | `distances.p8` |
| LEGACY_CONTEXT | `layers.r3.context` |

recursive alias探索で `sourceRank.v15/ryumyak` のnumberをrich layer objectの代わりに返してはならない。

`sourceRank.v15` と `sourceRank.ryumyak`、または `layers.r3.rankings.v15PureRank/ryumyakPureRank` はcell単位順位である。Source-first/RobustnessはArea Family順位で、全cell family membershipはreleaseにない。`sourceFirstAreaRank/robustnessAreaRank=null`、`areaRankCoverage=not_cell_addressable_in_r3_release` を保持し、APIもrankを推測しない。

## Fact Envelope

APIはruntime factを `fact-envelope/1.0` へ包み、release、sources、coverage、finding、policy effectを残す。

- partial/unknown/open/not-scanned coverageは `source_limited`
- source-limitedで閾値外の距離があっても `triggered:null`、finding review
- 明示fail/insideは `triggered:true`
- 明示pass/outsideかつcomplete evidenceだけ `triggered:false`
- `absenceClaimAllowed:false`
- `aiScoringAllowed:false`

policy判定では既知distanceを選択300/500/650m閾値で再計算する。runtime既定500mのtriggerを異なる閾値へ流用しない。shrineは既定OFFで、`includeShrines:true` の場合だけhard gateへ入れる。hard vetoは他レイヤーで補償しない。

## Comparison data minimization

assessのfull responseはprofile facts、provenance、HCL等を含むため、そのまま20件をcompareへ送る経路を標準にしない。推奨する `iyashiro-comparison-candidate/1.1` tokenは、current evidence releaseと集約済み判定・ranking basis・cell availability要約だけをHMAC署名する。

token payloadは24KiB、wireは32,837文字、寿命は最大24時間である。物件URL、full snapshot、provenance、memo、station、layout、HCL input/report、profile facts、coordinates、disclaimerを含めない。propertyの表示用name/addressは残るため、tokenは暗号化済みデータとして扱わず、ログ保存・第三者共有を避ける。

旧full snapshotは署名済み2〜3件だけを互換経路として受ける。compact token、旧snapshotともcurrent releaseと共有policyの不一致は409であり、live compareだけがruntimeから新規にprofileを読む。

## Packagingとdeploy gate

統合public dataは約156.79MiBである。public assetとして配置し、Vercel Function bundleへ同梱しない。公開前に次を実デプロイで確認する。

- public assetが全件uploadされ、release manifestと624 row pathを取得できる
- production/previewのself-fetch base URLとprotection bypassが意図どおり動く
- `GET /api/v3/releases` が200、未知でない代表cell profileと座標resolveが200
- artifactを意図的に欠いた検証環境では503となり、200 fallbackしない
- token署名secretまたはpreview限定派生鍵が利用でき、current release bindが成立する

artifact欠落を許容したまま公開しない。
