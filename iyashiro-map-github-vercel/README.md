# イヤシロ土地判定マップ

東京23区・横浜市・川崎市を対象に、イヤシロ仮説と現代的な土地リスクを
別々に可視化し、住所または地図上の地点を診断する個人用マップです。

## Integrated decision copilot

The release candidate adds `/integrated`, a single evidence-first surface for area research and property comparison.
It keeps empirical risk, research proxies, traditional lenses, and missing evidence visibly separate.

- Runtime pack: 120,662 canonical 100 m cells across Tokyo 23 wards, Yokohama, and Kawasaki.
- Inputs: address, coordinates, an allowlisted property URL, and explicit manual corrections.
- Policy: 300 / 500 / 650 m thresholds, 500 m default, shrines opt-in, hard vetoes non-compensatory.
- Lenses: R3, V15.3, RYUMYAK, ORBIT, history/P8, and bounded HOUSE COMPASS LAB context.
- Failure semantics: UNKNOWN, PARTIAL, unavailable, and out-of-scope are never presented as safe.
- Comparison: up to 20 candidates using short-lived, current-release-bound signed tokens without raw HCL or listing PII.
- Root map: a clicked pin and an address both open the same `/api/v3/dossier` land dossier.
- Pillar 1 is イヤシロジ（＝テライン仮説）with current V15.3 and comparison-only V10; pillar 2 is independent 龍脈. Their ranks are never averaged.
- The dossier then explains terrain, water, ground, history, nearby facilities, place-name origin, and missing evidence in Japanese. Missing evidence is not safety.

Contracts and operations are documented in `docs/INTEGRATED_API_V3.md`, `docs/INTEGRATED_API_DATA_CONTRACT.md`, and `public/openapi-v3.json`.

This branch does not promote the production alias. Production comparison signing requires `IYASHIRO_COMPARE_SNAPSHOT_SECRET` of at least 32 bytes.
Protected Vercel previews may use the documented deployment-scoped HKDF fallback; all other missing-key cases fail closed.

## Map layers

- 地図を開くと、クオレガ東京本社4.5km圏の6,361区画に加え、田園都市線の
  渋谷〜二子玉川・線路中心1km帯の2,109区画を100m間隔で事前計算した
  色分けを静的PNGとして即時表示します。
- ズーム14以上では、同じ事前計算データから100m区画を重ねます。地点を
  クリックするとピンを立て、その地点の総合土地カルテを開きます。
- 地点クリックと住所検索は、どちらも `/api/v3/dossier` を使います。
  絶対回避条件、イヤシロジ（V15.3・比較用V10）、独立した龍脈、地形、水、
  地盤、歴史、周辺施設、地名由来、まだ足りない情報を同じ順序で表示します。
  取得できない情報は「安全」へ読み替えません。
- 広域色分けの行政区域マスクは国土交通省「国土数値情報 行政区域データ
  2025年版」、標高は国土地理院DEMを使用しています。

`scripts/generate-instant-overlay.py` は広域色分けを再生成する開発用スクリプトです。
`scripts/generate-cuolega-grid.py` は `--region cuolega` または
`--region denentoshi` で、両対象の100mグリッドと即時表示画像を同じ
較正ロジックで再生成します。
詳細な地点診断を広域表示で置き換えるものではありません。

## Runtime

A clean full-stack starter running on
[vinext](https://github.com/cloudflare/vinext), with optional Cloudflare D1 and
Drizzle support.

## Prerequisites

- Node.js `>=22.13.0`
- Linux with `flock`, `curl`, and GNU `timeout`

## Sites Lifecycle

The Sites lifecycle CLI runs the locked dependency install before returning this checkout. Edit the source under `app/`, then checkpoint when a coherent milestone is ready to inspect or share. The remote Sites builder runs `npm run build` against the pushed commit. Do not repeat install or build as a normal pre-checkpoint step.

This starter does not use `wrangler.jsonc`.

`install:ci` is intentionally a single, non-retrying `npm ci`. It refuses a concurrent install for the same project, consumes a matching image-seeded npm cache with `--prefer-offline` while retaining registry fallback for a missing cache object, otherwise downloads and verifies the complete vinext tarball recorded in `package-lock.json`, limits npm to one socket, and terminates a stalled install. `build` applies a short timeout and then validates the Sites artifact. These helpers target Linux and use GNU `timeout`; they are not native macOS scripts.

Scripts that need writable project-scoped home, npm, XDG, and temporary paths use `scripts/sites-env.sh`. The `dev` and `start` scripts honor the caller's runtime environment and keep Wrangler logs inside the checkout. The generated `.sites-runtime/` directory is disposable and ignored by Git.

## Included Shape

- edit site code under `app/`
- `app/chatgpt-auth.ts` provides optional dispatch-owned ChatGPT sign-in helpers
- `.openai/hosting.json` declares optional Sites D1 and R2 bindings
- `vite.config.ts` simulates declared bindings for local development
- `db/index.ts` reads the D1 binding from the Cloudflare Worker environment
- `db/schema.ts` starts intentionally empty
- `examples/d1/` contains an optional D1 example surface
- `drizzle.config.ts` supports local migration generation when needed

## Workspace Auth Headers

OpenAI workspace sites can read the current user's email from
`oai-authenticated-user-email`.

SIWC-authenticated workspace sites may also receive
`oai-authenticated-user-full-name` when the user's SIWC profile has a non-empty
`name` claim. The full-name value is percent-encoded UTF-8 and is accompanied by
`oai-authenticated-user-full-name-encoding: percent-encoded-utf-8`.

Treat the full name as optional and fall back to email when it is absent:

```tsx
import { headers } from "next/headers";

export default async function Home() {
  const requestHeaders = await headers();
  const email = requestHeaders.get("oai-authenticated-user-email");
  const encodedFullName = requestHeaders.get("oai-authenticated-user-full-name");
  const fullName =
    encodedFullName &&
    requestHeaders.get("oai-authenticated-user-full-name-encoding") ===
      "percent-encoded-utf-8"
      ? decodeURIComponent(encodedFullName)
      : null;

  const displayName = fullName ?? email;
  // ...
}
```

## Optional Dispatch-Owned ChatGPT Sign-In

Import the ready-to-use helpers from `app/chatgpt-auth.ts` when the site needs
optional or required ChatGPT sign-in:

- Use `getChatGPTUser()` for optional signed-in UI.
- Use `requireChatGPTUser(returnTo)` for server-rendered pages that should send
  anonymous visitors through Sign in with ChatGPT.
- Use `chatGPTSignInPath(returnTo)` and `chatGPTSignOutPath(returnTo)` for
  browser links or actions.
- Pass a same-origin relative `returnTo` path for the destination after sign-in
  or sign-out. The helper validates and safely encodes it.
- Mark protected pages with `export const dynamic = "force-dynamic"` because
  they depend on per-request identity headers.

Dispatch owns `/signin-with-chatgpt`, `/signout-with-chatgpt`, `/callback`, the
OAuth cookies, and identity header injection. Do not implement app routes for
those reserved paths. Routes that do not import and call the helper remain
anonymous-compatible.

SIWC establishes identity only; it does not prove workspace membership. Use the
Sites hosting platform's access policy controls for workspace-wide restrictions,
or enforce explicit server-side membership or allowlist checks.

Use SIWC for account pages, user-specific dashboards, saved records, and write
actions tied to the current ChatGPT user. Leave public content anonymous.

## Diagnostic Commands

- `npm run install:ci`: perform the one bounded lockfile install
- `npm run dev`: start the Vite/Vinext development server
- `npm run build`: build and validate the deployable Sites artifact
- `npm run start`: start the built Vinext application
- `npm test`: build, validate, and verify the rendered development-preview metadata
- `npm run validate:artifact`: recheck an existing artifact's manifest and ESM `default.fetch` export
- `npm run db:generate`: generate Drizzle migrations after schema changes

Use build and validation commands for targeted diagnosis after a remote failure, not as part of the normal checkpoint path.

The timeout defaults can be overridden for a controlled canary with `SITES_INSTALL_TIMEOUT`, `SITES_INSTALL_KILL_AFTER`, `SITES_BUILD_TIMEOUT`, and `SITES_BUILD_KILL_AFTER`. A timeout fails the command; the helpers never retry an unchanged install or build.

## Learn More

- [vinext Documentation](https://github.com/cloudflare/vinext)
- [Drizzle D1 Guide](https://orm.drizzle.team/docs/get-started/d1-new)
