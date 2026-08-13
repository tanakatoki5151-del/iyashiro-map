# Tokyo Archives execution-ground acquisition gate — 2026-08-13

Purpose: turn the Tokyo Metropolitan Archives public-catalog discovery into an exact reproduction / reading request list. Catalog metadata is **not** boundary geometry. Do not promote any polygon until original folios, attachments and independent cadastral/map evidence agree.

## Kozukappara — P0

### 1. pkey 517320
- 公開件名: 千住南組旧刑場払下の義に付伺
- year: 1887 (明治20)
- collection: collection_04
- source book id: 000118624
- request no.: 616.D4.14
- 16mm MF: 府明II明20-007
- electronic medium: D309-RAM
- public / copy allowed / photography allowed

Acquire: full item, immediately preceding/following folios, every attachment/map/別紙. Extract parcel/lot number, area, dimensions, adjoining land/road/rail/water, applicants/recipients, dates and stamps.

### 2. pkey 737372
- 公開件名: 払下 旧刑場 北豊島郡千住南組 矢仲藤七
- year: 1887 (明治20)
- source book: 地種目変換簿〈庶務課〉明治20年起
- source book id: 000118608
- request no.: 616.C4.16
- 16mm MF: 府明II明20-039
- electronic medium: D049-RAM
- public / copy allowed / photography allowed

Use as an independent land-disposition / land-category cross-check against pkey 517320. Do not assume both refer to identical geometry until the original entries prove it.

### 3. pkey 496452
- 公開件名: 小塚原火葬地墓地の義
- year: 1873
- request no.: 606.D7.17

Use to distinguish execution-ground, cremation-ground and cemetery transitions. Never merge these roles merely because they are geographically or historically adjacent.

### Additional context items
- pkey 549995, 1870: 千住小塚原仕置場で仕置の件
- pkey 557458, 1873: 元焼場回向院下屋敷 listed as an animal carcass skinning site. This is **animal-processing land use**, not human cremation/burial evidence.
- pkey 716723, 1883: 千住屯所管轄小塚原外…巡査派出所, context only.

## Suzugamori — P0

### 1. pkey 531418
- 公開件名: 荏原郡大井村旧刑場払下の義に付伺
- catalog year: 1888 (明治21)
- collection: collection_04
- source book id: 000119049
- source book: 普通第1種 稟申録・地籍・1〈庶務課地籍掛〉
- request no.: 616.A5.06
- 16mm MF: 府明II明21-011
- electronic medium: D314-RAM
- public / copy allowed / photography allowed

Acquire full item + adjacent folios + every map/attachment. Extract parcel numbers, sale/disposal area, dimensions, old Tokaido adjacency, coast/water adjacency, temple/settlement adjacency, applicants/recipients and all dates.

### Date discrepancy — preserve, do not normalize
Tokyo City History index had 1887-12-15 for “旧鈴ヶ森刑場払下”; the direct Archives detail record pkey 531418 gives 起案年 1888. Possible differences include application, approval, filing and drafting dates. Keep as `date_discrepancy_pending_original` until the folio is read.

### Independent disposal chain
- pkey 313497, 1876: 大井村地内鈴ヶ森元御仕置場払下の義に付司法省へ伺本紙指令
- pkey 313498, 1876: 同伺案
- pkey 322882, 1876: 荏原郡大井村地内払下之件 元鈴ヶ森
- pkey 326830, 1877: 鈴ヶ森元刑罪場番小屋跡地…払下出願
- pkey 1636974, 1877-02-09: 大井村字鈴ヶ森元死刑場番小屋地所落札人へ払下に付引渡

The 1877 hut-lot geometry is not the full execution ground. Keep it as a separate geometry candidate / control-point source.

## QC after acquisition
1. Scan/copy every page and attachment, not just the title folio.
2. Hash each received file with SHA-256.
3. Double-transcribe parcel numbers, area, dimensions and dates.
4. Separate facility function, disposal parcel, later cemetery/cremation use and modern monument/temple boundaries.
5. Georeference only with independently identifiable control points.
6. Compare affine/projective models; save leave-one-out residuals, RMS, median, 95th percentile and max error.
7. `scoringEffect = none` until review geometry passes the project’s promotion gate.

Reproduction search workflow: `research/search_tokyo_archives_boundary_records.py`
Source run: GitHub Actions `31685719604`, artifact digest `sha256:eef33426500c6c46d04fac0949076b12b80e1dccc0d74f08250630ca234f88b5`.
