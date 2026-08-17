#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import csv
import gzip
import json
from pathlib import Path

GRID_WIDTH = 462
GRID_HEIGHT = 587
RECORD_SIZE = 7
FORMAL_CELLS = 120_662
CHUNK_CHARS = 100_000

AGGREGATE = {"NEUTRAL": 1, "CAUTION": 2, "CANDIDATE": 3, "STRONG": 4, "MIXED": 5}
TIERS = {
    "A_BUILT_UP_CONTINUITY": 1,
    "B_CURRENT_BUILDINGS_HISTORIC_REVIEW": 2,
    "NO_CURRENT_BUILDINGS": 3,
    "HISTORIC_NONRESIDENTIAL_REVIEW": 4,
    "UNKNOWN_PLATEAU_SOURCE_HOLE": 5,
}
PLATEAU = {"PASS": 1, "EXPLICIT_NO_BUILDINGS": 2, "UNKNOWN_SOURCE_TILE_404": 3}

RUNTIME_TEMPLATE = '''import "server-only";
import { gunzipSync } from "node:zlib";
{imports}

const ENCODED_GZIP = {joined};

export const ECOSCAPE_RUNTIME_VERSION = "ECOSCAPE_PROPERTY_PROFILE_INDEX_120662_B120";
export const ECOSCAPE_BUILD_ID = "ecos-mw4-property-profile-adapter-20260817-b120";
export const ECOSCAPE_FORMAL_CELLS = 120662;
export const ECOSCAPE_GRID_WIDTH = 462;
export const ECOSCAPE_GRID_HEIGHT = 587;
const RECORD_SIZE = 7;

export const ecoscapeAggregateStates = ["INVALID", "NEUTRAL", "CAUTION", "CANDIDATE", "STRONG", "MIXED"] as const;
export const ecoscapeResidentialTiers = [
  "INVALID",
  "A_BUILT_UP_CONTINUITY",
  "B_CURRENT_BUILDINGS_HISTORIC_REVIEW",
  "NO_CURRENT_BUILDINGS",
  "HISTORIC_NONRESIDENTIAL_REVIEW",
  "UNKNOWN_PLATEAU_SOURCE_HOLE",
] as const;
export const ecoscapePlateauStatuses = ["INVALID", "PASS", "EXPLICIT_NO_BUILDINGS", "UNKNOWN_SOURCE_TILE_404"] as const;

export type EcoscapeRuntimeRecord = {
  gridIndex: number;
  robustEnvironmentalCandidate: boolean;
  thresholdStable: boolean;
  robustResidentialCandidate: boolean;
  aggregateStateP25: (typeof ecoscapeAggregateStates)[number];
  coreZone3Plus: boolean;
  residentialPlausibilityTier: (typeof ecoscapeResidentialTiers)[number];
  knownPillarsP25: number;
  favorablePillarsP25: number;
  cautionPillarsP25: number;
  plateauStatus: (typeof ecoscapePlateauStatuses)[number];
  robustCandidateShare300m: number;
  robustCandidateShare500m: number;
  residentialComponentId: string | null;
};

let decoded: Buffer | null = null;
function runtimeBuffer(): Buffer {
  if (!decoded) decoded = gunzipSync(Buffer.from(ENCODED_GZIP, "base64"));
  return decoded;
}

export function readEcoscapeRuntime(gridRow: number, gridCol: number): EcoscapeRuntimeRecord | null {
  if (!Number.isInteger(gridRow) || !Number.isInteger(gridCol) || gridRow < 0 || gridCol < 0 || gridRow >= ECOSCAPE_GRID_HEIGHT || gridCol >= ECOSCAPE_GRID_WIDTH) return null;
  const gridIndex = gridRow * ECOSCAPE_GRID_WIDTH + gridCol;
  const offset = gridIndex * RECORD_SIZE;
  const buffer = runtimeBuffer();
  if (offset + RECORD_SIZE > buffer.length) return null;
  const b0 = buffer[offset];
  if ((b0 & 1) === 0) return null;
  const b1 = buffer[offset + 1];
  const b2 = buffer[offset + 2];
  const aggregateStateP25 = ecoscapeAggregateStates[(b0 >> 4) & 0x7];
  const residentialPlausibilityTier = ecoscapeResidentialTiers[b1 & 0x7];
  const plateauStatus = ecoscapePlateauStatuses[(b2 >> 6) & 0x3];
  if (!aggregateStateP25 || aggregateStateP25 === "INVALID" || !residentialPlausibilityTier || residentialPlausibilityTier === "INVALID" || !plateauStatus || plateauStatus === "INVALID") return null;
  const zoneNumber = buffer[offset + 5] | (buffer[offset + 6] << 8);
  return {
    gridIndex,
    robustEnvironmentalCandidate: Boolean(b0 & 0x2),
    thresholdStable: Boolean(b0 & 0x4),
    robustResidentialCandidate: Boolean(b0 & 0x8),
    aggregateStateP25,
    coreZone3Plus: Boolean(b0 & 0x80),
    residentialPlausibilityTier,
    knownPillarsP25: (b1 >> 3) & 0x7,
    favorablePillarsP25: b2 & 0x7,
    cautionPillarsP25: (b2 >> 3) & 0x7,
    plateauStatus,
    robustCandidateShare300m: buffer[offset + 3] / 100,
    robustCandidateShare500m: buffer[offset + 4] / 100,
    residentialComponentId: zoneNumber ? `HRZ${String(zoneNumber).padStart(5, "0")}` : null,
  };
}
'''

ADAPTER = '''import "server-only";
import type { LocationLayer } from "./types";
import {
  ECOSCAPE_BUILD_ID,
  ECOSCAPE_FORMAL_CELLS,
  ECOSCAPE_RUNTIME_VERSION,
  readEcoscapeRuntime,
  type EcoscapeRuntimeRecord,
} from "./ecoscape-runtime";

const SOURCE_REGISTRY = "ECOSCAPE_CONTROL_REGISTRY_v1_20260816";
const SOURCE_B114 = "ECOSCAPE_LEVELB_V4_CORE6_FULL_B114";
const SOURCE_B115 = "ECOSCAPE_MW3_RESIDENTIAL_CANDIDATE_ZONES_B115";
const SOURCE_B116 = "ECOSCAPE_MW3_OFFICIAL_CHOME_ZONE_RANKING_B116";
const SOURCE_B120 = "ECOSCAPE_MW4_PROPERTY_PROFILE_ADAPTER_B120";

const aggregateLabel: Record<EcoscapeRuntimeRecord["aggregateStateP25"], string> = {
  INVALID: "不明",
  NEUTRAL: "中立",
  CAUTION: "注意条件が優勢",
  CANDIDATE: "候補",
  STRONG: "強い候補",
  MIXED: "好条件と注意条件が混在",
};
const tierLabel: Record<EcoscapeRuntimeRecord["residentialPlausibilityTier"], string> = {
  INVALID: "不明",
  A_BUILT_UP_CONTINUITY: "現況住宅地として連続性あり",
  B_CURRENT_BUILDINGS_HISTORIC_REVIEW: "現況建物あり・土地履歴を確認",
  NO_CURRENT_BUILDINGS: "現況建物なし",
  HISTORIC_NONRESIDENTIAL_REVIEW: "過去の非住宅利用を確認",
  UNKNOWN_PLATEAU_SOURCE_HOLE: "PLATEAU資料穴のため不明",
};
const percent = (value: number) => `${Math.round(value * 100)}%`;

export function buildEcoscapeLayer(gridRow: number, gridCol: number): LocationLayer {
  const record = readEcoscapeRuntime(gridRow, gridCol);
  if (!record) {
    return {
      layerId: "ecoscape", project: "ECOSCAPE", availability: "not_applicable", coverageStatus: "unknown", scoringEffect: "none",
      datasetVersion: ECOSCAPE_RUNTIME_VERSION, sourceRegistryVersion: SOURCE_REGISTRY, findings: [],
      warnings: ["この位置はECOSCAPEの120,662セル正本外、またはruntimeで解決できません。UNKNOWNを安全・悪条件へ変換しません。"],
      metadata: { formalCellCount: ECOSCAPE_FORMAL_CELLS, buildId: ECOSCAPE_BUILD_ID },
    };
  }
  const plateauUnknown = record.plateauStatus === "UNKNOWN_SOURCE_TILE_404";
  const candidateLabel = record.robustResidentialCandidate
    ? record.coreZone3Plus
      ? `頑健な住宅候補・3セル以上の連続ゾーン ${record.residentialComponentId ?? ""}`.trim()
      : `頑健な住宅候補・局所spot ${record.residentialComponentId ?? ""}`.trim()
    : record.robustEnvironmentalCandidate ? "環境候補だが住宅候補ゲートは未通過" : "頑健な環境候補には非該当";
  const explanation = [
    `P25判定は「${aggregateLabel[record.aggregateStateP25]}」。好条件${record.favorablePillarsP25}、注意${record.cautionPillarsP25}、判明${record.knownPillarsP25}/4柱。`,
    `${candidateLabel}。`,
    `周囲の頑健候補比率は300m ${percent(record.robustCandidateShare300m)}、500m ${percent(record.robustCandidateShare500m)}。`,
    `住宅文脈は「${tierLabel[record.residentialPlausibilityTier]}」。`,
    plateauUnknown ? "都市開放性はPLATEAU資料穴のためUNKNOWNで、悪条件として扱いません。" : record.plateauStatus === "EXPLICIT_NO_BUILDINGS" ? "PLATEAU上は交差建物なしとして明示されています。物件存在の否定ではありません。" : "PLATEAU実用Level B近似が接続済みです。",
  ].join(" ");
  return {
    layerId: "ecoscape", project: "ECOSCAPE", availability: plateauUnknown ? "partial" : "available",
    coverageStatus: plateauUnknown ? "partial_known_sources" : "complete_for_defined_sources", scoringEffect: "none",
    datasetVersion: ECOSCAPE_RUNTIME_VERSION, sourceRegistryVersion: SOURCE_REGISTRY,
    findings: [{
      findingId: `ECOSCAPE-CELL-${gridRow}-${gridCol}`, project: "ECOSCAPE", globalFeatureId: null,
      localPointer: `${SOURCE_B120}:g${gridRow}-${gridCol}`, title: `ECOSCAPE環境・住宅候補: ${aggregateLabel[record.aggregateStateP25]}`,
      category: "environmental_and_residential_candidate_context",
      status: record.robustResidentialCandidate || record.robustEnvironmentalCandidate ? "candidate" : "context",
      evidenceMaturity: "context_only", geometryRole: "canonical_100m_cell", spatialRelation: "cell_context",
      distanceMeters: 0, uncertaintyMeters: 100, validFrom: null, validTo: null, publicPrecision: "100m_cell",
      independenceGroup: "ECOSCAPE_B114_B116_CANONICAL_RUNTIME",
      canonicalSourceIdentity: `ECOSCAPE:${ECOSCAPE_RUNTIME_VERSION}:g${gridRow}-${gridCol}`,
      explanation,
      sourcePointers: [
        { project: "ECOSCAPE", pointer: SOURCE_B114, title: "Core6 four-pillar Level B V4", version: "B114" },
        { project: "ECOSCAPE", pointer: SOURCE_B115, title: "Residential candidate zones", version: "B115" },
        { project: "ECOSCAPE", pointer: SOURCE_B116, title: "Official chome and zone ranking", version: "B116" },
        { project: "ECOSCAPE", pointer: SOURCE_B120, title: "Static property profile adapter", version: "B120" },
      ],
      metadata: { ...record, candidateOverride: false, externalShadowScoringEffect: "none", plateauLevel: "LEVEL_B_APPROX" },
    }],
    warnings: [
      "ECOSCAPEは4本柱の環境候補を表示します。磁気・地下・歴史・地形shadowをこの候補へ加点・減点しません。",
      "頑健候補に非該当でも、安全・不適・悪い土地を意味しません。UNKNOWNは0点でも悪条件でもありません。",
      "PLATEAUはLevel B実用近似で、114セルのsource-holeは明示的UNKNOWNです。",
    ],
    metadata: { formalCellCount: ECOSCAPE_FORMAL_CELLS, buildId: ECOSCAPE_BUILD_ID, scoringEffect: "none", candidateOverride: false, runtimeConnected: true },
  };
}
'''

TEST = '''\n\ntest("connects ECOSCAPE B120 to the LocationProfile without rescoring", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("ecoscape", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const response = await worker.fetch(
    new Request("http://localhost/api/profile?lat=35.723007&lng=139.694672", { headers: { accept: "application/json" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(payload.spatialContext.cellId, "g130-240");
  assert.equal(payload.layers.ecoscape.availability, "available");
  assert.equal(payload.layers.ecoscape.scoringEffect, "none");
  assert.equal(payload.layers.ecoscape.datasetVersion, "ECOSCAPE_PROPERTY_PROFILE_INDEX_120662_B120");
  const finding = payload.layers.ecoscape.findings[0];
  assert.equal(finding.metadata.aggregateStateP25, "CAUTION");
  assert.equal(finding.metadata.knownPillarsP25, 4);
  assert.equal(finding.metadata.favorablePillarsP25, 1);
  assert.equal(finding.metadata.cautionPillarsP25, 2);
  assert.equal(finding.metadata.candidateOverride, false);
  assert.equal(payload.legacyRuntime.theory.score, 50);
  assert.equal(payload.legacyRuntime.modern.score, 75);
  assert.equal(payload.legacyRuntime.combined.score, 75);
});
'''

DOC = '''# ECOSCAPE B120 LocationProfile runtime integration\n\n- Source: Drive canonical B120 bundle, SHA-256 `add1d47e2b06b12ad8fbc69027a3cb50d18c867b044583576a6d2536822e47c1`.\n- Runtime: deterministic seven-byte dense record over the frozen 462-column canonical grid.\n- Formal cells: 120,662.\n- Candidate counts: environmental 21,549; residential 12,616; threshold-stable 89,365.\n- Guardrails: `scoringEffect: none`, `candidateOverride: false`, UNKNOWN is not negative evidence.\n- Fixed fixture: `東京都豊島区目白五丁目8-1` -> `g130-240`, P25 CAUTION, favorable 1, caution 2, known 4.\n'''


def parse_bool(value: str) -> bool:
    return value.lower() == "true"


def build(args: argparse.Namespace) -> None:
    repo = Path(args.repo_root).resolve()
    b120 = Path(args.b120).resolve()
    b116 = Path(args.b116).resolve()
    out = repo / "app/lib/location-profile"

    core_zones: set[str] = set()
    with b116.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if parse_bool(row["isZone"]) and int(row["coreCellCount"]) >= 3:
                core_zones.add(row["zoneId"])
    if len(core_zones) != 779:
        raise RuntimeError(f"expected 779 core zones, got {len(core_zones)}")

    buffer = bytearray(GRID_WIDTH * GRID_HEIGHT * RECORD_SIZE)
    counts = {"rows": 0, "robustEnvironmental": 0, "thresholdStable": 0, "robustResidential": 0, "plateauUnknown": 0}
    fixture = None
    with gzip.open(b120, "rt", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            grid_row, grid_col = int(row["gridRow"]), int(row["gridColumn"])
            if not (0 <= grid_row < GRID_HEIGHT and 0 <= grid_col < GRID_WIDTH):
                raise RuntimeError(f"grid out of range: {grid_row},{grid_col}")
            robust_environmental = parse_bool(row["robustCandidate"])
            threshold_stable = parse_bool(row["thresholdStable"])
            robust_residential = parse_bool(row["robustResidentialCandidate"])
            zone = row["residentialRobustZoneId"]
            zone_number = int(zone[3:]) if zone else 0
            aggregate = AGGREGATE[row["aggregateState_P25"]]
            tier = TIERS[row["residentialPlausibilityTier"]]
            known = int(row["knownPillars_P25"])
            favorable = int(row["favorablePillars_P25"])
            caution = int(row["cautionPillars_P25"])
            plateau = PLATEAU[row["plateauStatus"]]
            share300 = round(float(row["robustCandidateShare_300m"]) * 100)
            share500 = round(float(row["robustCandidateShare_500m"]) * 100)
            b0 = 1 | (int(robust_environmental) << 1) | (int(threshold_stable) << 2) | (int(robust_residential) << 3) | (aggregate << 4) | (int(bool(zone and zone in core_zones)) << 7)
            b1 = tier | (known << 3)
            b2 = favorable | (caution << 3) | (plateau << 6)
            offset = (grid_row * GRID_WIDTH + grid_col) * RECORD_SIZE
            buffer[offset:offset + RECORD_SIZE] = bytes([b0, b1, b2, share300, share500, zone_number & 0xFF, zone_number >> 8])
            counts["rows"] += 1
            counts["robustEnvironmental"] += int(robust_environmental)
            counts["thresholdStable"] += int(threshold_stable)
            counts["robustResidential"] += int(robust_residential)
            counts["plateauUnknown"] += int(row["plateauStatus"] == "UNKNOWN_SOURCE_TILE_404")
            if row["canonicalCellId"] == "g130-240":
                fixture = {"aggregate": row["aggregateState_P25"], "known": known, "favorable": favorable, "caution": caution}

    expected = {"rows": 120662, "robustEnvironmental": 21549, "thresholdStable": 89365, "robustResidential": 12616, "plateauUnknown": 114}
    if counts != expected:
        raise RuntimeError(f"count mismatch: {counts} != {expected}")
    if fixture != {"aggregate": "CAUTION", "known": 4, "favorable": 1, "caution": 2}:
        raise RuntimeError(f"fixture mismatch: {fixture}")

    encoded = base64.b64encode(gzip.compress(bytes(buffer), compresslevel=9, mtime=0)).decode("ascii")
    chunks = [encoded[index:index + CHUNK_CHARS] for index in range(0, len(encoded), CHUNK_CHARS)]
    for old in out.glob("ecoscape-runtime-chunk-*.ts"):
        old.unlink()
    for index, chunk in enumerate(chunks):
        (out / f"ecoscape-runtime-chunk-{index}.ts").write_text(f"export default {json.dumps(chunk)};\n", encoding="utf-8")
    imports = "\n".join(f'import c{index} from "./ecoscape-runtime-chunk-{index}";' for index in range(len(chunks)))
    joined = " + ".join(f"c{index}" for index in range(len(chunks)))
    (out / "ecoscape-runtime.ts").write_text(RUNTIME_TEMPLATE.format(imports=imports, joined=joined), encoding="utf-8")
    (out / "ecoscape-adapter.ts").write_text(ADAPTER, encoding="utf-8")

    route_path = repo / "app/api/profile/route.ts"
    route = route_path.read_text(encoding="utf-8")
    import_anchor = 'import { buildUnderlandLayer } from "@/app/lib/location-profile/underland-adapter";\n'
    if 'buildEcoscapeLayer' not in route:
        if import_anchor not in route:
            raise RuntimeError("route import anchor missing")
        route = route.replace(import_anchor, import_anchor + 'import { buildEcoscapeLayer } from "@/app/lib/location-profile/ecoscape-adapter";\n')
    const_anchor = '    const underland = buildUnderlandLayer(cell.gridRow, cell.gridCol);\n'
    if 'const ecoscape = buildEcoscapeLayer' not in route:
        if const_anchor not in route:
            raise RuntimeError("route const anchor missing")
        route = route.replace(const_anchor, const_anchor + '    const ecoscape = buildEcoscapeLayer(cell.gridRow, cell.gridCol);\n')
    old_block = '''      readinessLayer(\n        "ecoscape",\n        "ECOSCAPE",\n        "not_available",\n        "ECOSCAPE formal release is pending; unreleased source families remain UNKNOWN.",\n      ),'''
    if old_block in route:
        route = route.replace(old_block, "      ecoscape,")
    elif "      ecoscape," not in route:
        raise RuntimeError("ECOSCAPE readiness block missing")
    route = route.replace(
        '"V10 frozen-cell facts and UNDERLAND practical water/moisture context are connected read-only; V11/VEIL/LIMEN detailed fact adapters continue incrementally.",',
        '"V10, UNDERLAND and ECOSCAPE B120 facts are connected read-only; V11/VEIL/LIMEN detailed fact adapters continue incrementally.",',
    )
    route_path.write_text(route, encoding="utf-8")

    test_path = repo / "tests/rendered-html.test.mjs"
    tests = test_path.read_text(encoding="utf-8")
    if 'connects ECOSCAPE B120 to the LocationProfile' not in tests:
        test_path.write_text(tests.rstrip() + TEST, encoding="utf-8")
    (repo / "docs/ECOSCAPE_B120_LOCATION_PROFILE_INTEGRATION_20260817.md").write_text(DOC, encoding="utf-8")
    meta = {**counts, "coreZones": len(core_zones), "rawBytes": len(buffer), "gzipBase64Chars": len(encoded), "chunkCount": len(chunks), "fixture": fixture}
    (repo / "docs/ECOSCAPE_B120_RUNTIME_BUILD_META.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--b120", required=True)
    parser.add_argument("--b116", required=True)
    parser.add_argument("--repo-root", required=True)
    build(parser.parse_args())
