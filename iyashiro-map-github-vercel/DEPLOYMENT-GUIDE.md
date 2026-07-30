# イヤシロ土地判定マップ 公開手順

このフォルダは、GitHub と Vercel に公開するための完全なソース一式です。

## 1. GitHubへアップロード

1. ZIPを解凍します。
2. `tanakatoki5151-del/iyashiro-map` を開きます。
3. `Add file` → `Upload files` を選びます。
4. このフォルダそのものではなく、フォルダ内のファイルとフォルダをすべてアップロードします。
5. Commit message に `Initial iyashiro map implementation` と入力します。
6. `Commit directly to the main branch` を選んで確定します。

`node_modules`、`.next`、`.env`、`.vercel` はアップロードしません。このZIPには最初から含めていません。

## 2. Vercelへ接続

1. <https://vercel.com/new> を開きます。
2. Team は `tanakatoki5151-del's projects` を選びます。
3. GitHubの `iyashiro-map` を `Import` します。
4. 次の設定を確認します。

| 設定 | 値 |
|---|---|
| Project Name | `iyashiro-map` |
| Framework Preset | Next.js |
| Root Directory | `./` |
| Production Branch | `main` |
| Environment Variables | なし |

5. `Deploy` を押します。

リポジトリ内の `vercel.json` により、Vercelでは次の設定が使われます。

- Install Command: `npm ci`
- Build Command: `npx next build`

以後は、GitHubの `main` が更新されるとVercelの本番環境も自動更新されます。

## ローカル確認

Node.js 22.13以上を使用します。

```bash
npm ci
npx next build
```

## 内容

- 東京23区・横浜市・川崎市の住所・地点検索
- イヤシロ／ケガレ仮説判定
- 現代的土地条件・ハザード判定
- クオレガ4.5km圏の100m事前計算データ
- 田園都市線・渋谷〜二子玉川の100m事前計算データ
- 即時表示用の色分け画像

イヤシロ／ケガレ判定は、伝統的仮説を地形データで再現した参考指標です。科学的効能や安全を保証するものではありません。
