# 本所被服廠 p83 現代座標化・品質ゲート

更新日: 2026-08-12

## 目的

1932年『被服廠跡』p83「元陸軍被服廠分割図」を、現代地物と比較可能な研究候補へ進める。ただし、形状合わせと出典付き歴史境界を混同しない。

## 時点を分離する

- 旧陸軍被服廠全敷地: 20,430坪余
- 1922年に東京市が取得した公園用地: 6,279.06坪
- 1928年区画整理後の換地: 5,922.81坪
- 現横網町公園: 19,579.53㎡

1928年換地の換算面積と現公園面積はほぼ一致する。一方、現公園は旧被服廠全敷地ではない。

## p83ソース空間の解釈

凡例は A=公園、B=社会事業、C=道路、D=逓信省、E=学校、F=電気局。Aは大区画と小区画2つに分かれる。

大A区画の画素面積比と、公表された 5,922.81 / 6,279.06 の比を比較する。公表面積はデジタイズ品質管理にも使うため、この一致は内部整合チェックであり独立証拠ではない。

## 許される研究Geometry

- `source_space_digitisation_not_georeferenced`
- `modern_reference_geometry`
- `outer_constraint_not_historical_boundary`
- `shape_alignment_not_control_point_georeference`

全Geometryで次を固定する。

- `scoringEffect = none`
- `verifiedHistoricalSitePolygonCountEffect = 0`
- `sourceBackedReviewPolygonCountEffect = 0`
- `doNotAutoExclude = true`
- `doNotApplyDistancePenalty = true`
- `doNotChangeRanking = true`

## 今回の変換

大A区画を現横網町公園の参照Polygonへ方向別支持点でaffine shape alignmentし、同一変換をp83外周へ適用する。これは歴史地物と現代地物の対応点を使う地理補正ではない。

評価値として、RMS、Hausdorff距離、IoU、変換後外周面積、現代公園・ホテル・学校・博物館との重なり率を保存する。

## verified/review Polygonへの昇格条件

1. p83と別系統の旧版地図・区画整理図・旧公図を取得する。
2. 道路交差点、道路屈曲、区画角など6点以上の独立コントロールポイントを同定する。
3. 点別残差、全体RMS、CRS、変換式を保存する。
4. 1922公園用地、1928換地、旧被服廠全敷地を別Geometryにする。
5. 独立担当が頂点と根拠をレビューする。

この条件を満たすまで、公開サイトの自動判定・距離減点・ランキングへ接続しない。
