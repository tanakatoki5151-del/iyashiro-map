# Vercel Production Base and Integrated Release Candidate

このフォルダは、2026-08-23時点の公開エイリアス `https://iyashiro-map.vercel.app/` が指していた正確なGitHub commitを取得し、最終統合候補を作るための作業場所です。

## Production base

- Vercel project: `prj_xeJLLwjG9pS8PoPg9i8RNCbeQhF2`
- Team: `team_XHs1MwGtu8tSCPLDZ6zAJx7H`
- Production deployment: `dpl_9Cq7VXj9wsbTp8QZ3GkFQoFDJMm3`
- GitHub repository: `tanakatoki5151-del/iyashiro-map`
- Commit: `38873320d158616ce38f552a28927b1866316ce7`
- Vercel root directory / application: `iyashiro-map-github-vercel/`
- Base build observed: Next.js 16.3.1、TypeScript PASS、production READY

## Local branch

`codex/integrated-r3-20260823`

このbranchは公開commitから分岐したローカル統合候補です。既存production aliasは変更していません。

## Related paths

- portable canonical inputs: `../../00_INBOX_手動取得/DRIVE_CANONICAL_SYNC_20260823/`
- project control: `../../00_START_HERE・最新正本/00_PROJECT_CONTROL_20260823/`
- older reconstructed reference: `../01_CURRENT_INTEGRATED_APP_20260823/`

## Release rule

preview build、data QA、API smoke、browser E2E、manifest readbackがすべて通るまではproductionへ昇格しない。現在のproduction deployment IDをrollback先として保持する。
