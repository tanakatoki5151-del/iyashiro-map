# Integrated cell runtime: R3 + PROJECT ORBIT v2

Release ID: iyashiro-r3-orbit-v2-20260823

## Outcome

The release turns the frozen R3 and ORBIT ledgers into Vercel-sized row shards
that can address every valid canonical 100 m cell. It does not rescore or edit
either source project.

Expected closure:

| Item | Count |
|---|---:|
| Valid canonical cells | 120,662 |
| R3 lens cells | 84,060 |
| R3 pass lens cells | 20,118 |
| Valid cells without an R3 lens row | 36,602 |
| ORBIT distance rows | 482,648 |
| Distance categories per cell | 4 |
| Canonical facilities | 31,544 |

## Files

- public/data/integrated/release-manifest.json: source hashes, coverage,
  policies, QA, shard hashes and sizes.
- public/data/integrated/schema.json: exact tuple columns and semantics.
- public/data/integrated/rows/gNNN.json: all 624 canonical grid rows. Rows
  without a valid cell are materialized with an empty cells array.
- public/data/integrated/facilities/part-H.json: the complete canonical facility
  ledger in 16 deterministic hash shards.
- app/lib/integrated-data/runtime.ts: server lookup and normalization.
- tests/integrated-data.test.mjs: independent output-count and semantics QA.

## Decision semantics

A known feature at or inside 500 m can fail a hard gate. A measured distance outside
500 m is not automatically a safety claim when source coverage is incomplete.

- Temple: 500 m hard gate; religion location coverage remains partial.
- Cemetery: 500 m hard gate; 25-municipality permit-ledger coverage remains
  unknown.
- Large inpatient hospital: 500 m R3 hard gate on R3-addressable cells.
- General hospital: displayed but excluded from ranking.
- Shrine: displayed as context only.
- Strong history and P8: 500 m R3 current-evidence gates.
- No R3 lens row: R3 status remains UNKNOWN.

Spiritual Pass=true is exposed as pass_current_evidence; it is not named safe,
certified, or complete.

## Ranking boundary

R3 provides V15 and RYUMYAK pure ranks on individual cell rows. Source-first
and robustness are area-family rankings. The release does not provide a full
cell-to-family membership table, so the runtime intentionally returns those
two cell ranks as null with areaRankCoverage set to
not_cell_addressable_in_r3_release.

## Vercel loading

On Vercel, the runtime self-fetches manifest and row shards from the current
VERCEL_URL static asset origin. It does not read public through Node fs, so the
156 MB corpus is not duplicated into every Function trace. Local execution
reads public/data/integrated through the Node built-in fs module. Row promises
are cached in a 64-row LRU per process; rejected promises are removed so
transient failures can retry.

If Vercel system environment variables are not exposed, set
IYASHIRO_INTEGRATED_DATA_BASE_URL to the public static deployment origin.
For protected deployments, the runtime forwards the system-provided
VERCEL_AUTOMATION_BYPASS_SECRET only as the x-vercel-protection-bypass request
header. The secret is never placed in a URL, response, manifest, or log.
Deployment Protection must allow the server-side static fetch; verify both
/data/integrated/release-manifest.json and the profile API after deployment.

Before a lookup, release-manifest.json must pass schema, release ID, source
provenance, QA, coverage-count, and exact 624-row readiness checks. A missing
manifest or declared row raises IntegratedArtifactMissingError; a malformed or
non-PASS release raises IntegratedReleaseNotReadyError. Only a present row shard
whose cells array does not contain the requested in-range cell returns null.
This keeps artifact loss distinct from a canonical invalid cell.
