# 物件住所回収 v39 — 2026-08-14

## 結論

公開物件ページで番地号まで確認でき、国土地理院住所検索が同一住所を返した12件を、住所代表点 `G6/E1` として追加した。

- 現行建物: 92
- 住所代表点あり: 85（92.391%）
- 公開代表点: 83
- 住所回収待ち: 7
- building / parcel Polygon: 0
- ランキング変更: 0
- 点数変更: 0
- 自動除外変更: 0

住所代表点は建物入口・建物形状・敷地ではない。以下の施設距離は固定2026-07-30 OSM geometryとEPSG:6677による「代表点だけ」の計算値である。

## 今回閉じた12件

| propertyId | 物件・公開ページ同定 | 確認住所 | 100mセル効果 | 代表点の施設帯 / 最短距離 |
|---|---|---|---|---|
| BLDG-7f1edc74e493 | いなげやアパート | 世田谷区代沢2-44-9 | recovery | review 483.4m |
| BLDG-cef1a041caab | 栄荘 | 目黒区目黒本町5-26-23 | recovery | review 481.2m |
| BLDG-8cd2c023f66b | レガリス武蔵小山（source page） | 品川区小山台2-2-27 | all-fail | review 389.9m |
| BLDG-a2af4fb5be02 | アネトス武蔵小山 | 品川区小山台2-3-11 | reversal | pass 537.7m |
| BLDG-271131457705 | XEBEC馬込（source page） | 大田区中馬込1-5-3 | all-fail | review 317.4m |
| BLDG-6583382c8322 | LES CINQ SENS（source page） | 目黒区目黒本町5-29-12 | recovery | review 493.2m |
| BLDG-8bafd187bc1e | パークマンション（source page） | 目黒区東が丘2-13-11 | reversal | pass 508.9m |
| BLDG-b17de9a4e781 | ハーヴェスト八雲（source page） | 目黒区八雲5-4-5 | all-fail | below300 273.5m |
| BLDG-954b245eee08 | プラージュ（source page） | 大田区久が原4-16-15 | all-fail | review 359.9m |
| BLDG-e54072a84de4 | スパシエステージ北沢（source page） | 世田谷区北沢1-19-6 | all-pass | pass 554.4m |
| BLDG-e84ff7865c06 | プレミアムキューブ下北沢（source page） | 世田谷区北沢3-23-5 | all-fail | below300 196.1m |
| BLDG-870d0ad061dc | ザ・レジデンス・オブ・トーキョーOM06（source page） | 大田区中馬込1-1-20 | all-fail | review 417.1m |

セル効果 `recovery/reversal` と代表点の厳密距離結果は別軸。セル内に逆転地点があることは、当該住所代表点が逆転側にあることを意味しない。

## 残る7件

番地不足または物件同定競合のため、推測で点化しない。

- 代沢2丁目ハウス
- MELLAS馬込
- 北沢4丁目の建物名未確認物件
- 柿の木坂2丁目の学生向け物件
- 富ヶ谷2丁目の建物名未確認物件
- コムフォート（同住所別名競合）
- KS HOUSE

## 再現物

- property registry build: `8170dd74d57f3803`
- property exact build: `08bcc41153eb21a4`
- research priority build: `fa9a79ab66a845bf`
- research KPI build: `8a6fd715e5a5fe4e`
- Sites production: version 40, commit `efa56ec58389de7b5bf467dbe24fd40538189f8c`
- Drive folder: `10qH5u2Yhfwr65EcCHBZjyuctzAmAFv7E`
- Drive geocode artifact: `1M6IjH09Grw1GZlrl0VQBcX7yjHQwepGq`
- Drive registry artifact: `14f4WweqHMQocJB8UY0gk1evMZXPGk7FF`
- Drive evidence artifact: `18MqRAjkYxfhSLqKPeW6pRt5wbe7p6K0G`
- Drive exact artifact: `1xNxrh8Mw2trkgZfEhQdydOi1jYBV5cy-`

## QA

- full test: 59/59
- lint: pass
- verified production build: pass
- authenticated live API: registry `8170dd74d57f3803`, exact `08bcc41153eb21a4`, public counts 30/41/12
- scoringEffect: none
