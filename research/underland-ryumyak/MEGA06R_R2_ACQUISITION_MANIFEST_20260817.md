# UNDERLAND × RYUMYAK MEGA-06R R2 acquisition manifest

## Scope

Isolated acquisition and validation of current surface-river geometry/topology for Tokyo 23 wards, Yokohama and Kawasaki. This branch does not modify production scoring, ranking, Sites, or the public application.

## Branch

`agent/mega06r-w05-acquisition-20260817`

## Official W05 acquisition

- Source: MLIT National Land Numerical Information W05 River
- Prefectures: Saitama 11, Chiba 12, Tokyo 13, Kanagawa 14
- Fiscal-year archive family: W05-08
- Workflow run: `32019561350`
- Artifact: `mega06r-w05-kanto-boundary-buffer-r2a`
- Artifact ID: `9284807572`
- Artifact digest: `sha256:09a4b1b8bf9302354570b658340e1ed7b1bdc8ce250e25353ca3a93dbd756bca`
- Purpose of four-prefecture buffer: prevent prefecture borders from being mistaken for river outlets or water-mouth termini.

## CSIS stream-topology validation

- Source: University of Tokyo CSIS Infrastructure Base Registry stream data
- Workflow run: `32019234676`
- Artifact: `mega06r-csis-stream-topology-r1`
- Artifact ID: `9284687595`
- Artifact digest: `sha256:f6fced3828b5bcad0f02a59e66791fc51af5226fe6c4bcc87c5e7b3d3ec2aed2`
- Use: independent direction/topology validation only.
- Redistribution boundary: raw CSIS geometry is not included in public or Drive-derived output bundles; only non-reconstructive derived metrics are retained.

## Processing closure

- W05 used as the primary publishable geometry.
- Current-river proximity, local curvature, inner/outer bend, approach/leave, direct-collision, confluence, divergence, outlet and historical-current persistence were computed for all 120,662 canonical cells.
- UNDERLAND groundwater and moisture were excluded from Shui scoring and retained only as physical-habitability context.
- Long, Sha, Shui and Xue were recomputed and existing MEGA-07P zones received an affected-only YANGZHAI_AREA refresh.
- CEMETERY_CONTEXT, VEIL, IYASHIROCHI, PERSONAL_ACCEPTANCE and property-level gates remain open.
- Production score/ranking/Sites write: 0.
- UNDERLAND scientific-vote cross-write: 0.

## Drive authority bundle

`UNDERLAND_RYUMYAK_MEGA06R_R2_MEGA07Y_R1_20260817.zip`

The Drive bundle contains the reproducible cell ledger, zone atlas, summaries, maps, validation, schemas and manifest. Acquisition artifacts in GitHub Actions are temporary and are not the authority copy.
