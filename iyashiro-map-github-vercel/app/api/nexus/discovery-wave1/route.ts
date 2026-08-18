import { NextRequest, NextResponse } from "next/server";
import { readEcoscapeRuntime } from "@/app/lib/location-profile/ecoscape-runtime";
import { placeGraphSparseCells } from "@/app/lib/location-profile/placegraph-sparse-runtime";
import { readUnderlandRuntime } from "@/app/lib/location-profile/underland-runtime";
import { buildV10Layer } from "@/app/lib/location-profile/v10-adapter";
import {
  NEXUS_FULL_DOMAIN_WAVE1,
  NEXUS_FULL_DOMAIN_WAVE1_AS_OF_JST,
  NEXUS_FULL_DOMAIN_WAVE1_NOTES,
  NEXUS_FULL_DOMAIN_WAVE1_VERSION,
} from "@/app/lib/nexus/full-domain-wave1-v1";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const DEFAULT_LIMIT = 20;
const MAX_LIMIT = 50;

function integerParam(value: string | null, fallback: number, min: number, max: number, name: string) {
  if (value === null || value === "") return fallback;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < min || parsed > max) {
    throw new TypeError(`${name} は ${min}〜${max} の整数で指定してください。`);
  }
  return parsed;
}

function cleanFilter(value: string | null, maxLength: number) {
  const cleaned = value?.trim() ?? "";
  if (cleaned.length > maxLength) throw new TypeError(`フィルターは${maxLength}文字以内にしてください。`);
  return cleaned;
}

function cellParts(cellId: string) {
  const match = /^g(\d+)-(\d+)$/.exec(cellId);
  if (!match) throw new TypeError(`不正な canonical cell ID: ${cellId}`);
  return { row: Number(match[1]), col: Number(match[2]) };
}

function compactV10(layer: Awaited<ReturnType<typeof buildV10Layer>>) {
  const finding = layer.findings[0] ?? null;
  const metadata = (finding?.metadata ?? {}) as Record<string, unknown>;
  return {
    availability: layer.availability,
    coverageStatus: layer.coverageStatus,
    title: finding?.title ?? null,
    originalScore: typeof metadata.originalScore === "number" ? metadata.originalScore : null,
    originalFit: typeof metadata.originalFit === "number" ? metadata.originalFit : null,
    detailScore: typeof metadata.detailScore === "number" ? metadata.detailScore : null,
    neighborhoodScore: typeof metadata.neighborhoodScore === "number" ? metadata.neighborhoodScore : null,
    confidence: typeof metadata.confidence === "number" ? metadata.confidence : null,
    warnings: layer.warnings,
  };
}

async function enrich(sample: (typeof NEXUS_FULL_DOMAIN_WAVE1)[number]) {
  const { row, col } = cellParts(sample.cellId);
  const [v10] = await Promise.all([buildV10Layer(row, col)]);
  const underland = readUnderlandRuntime(row, col);
  const ecoscape = readEcoscapeRuntime(row, col);
  const placegraph = placeGraphSparseCells()[sample.cellId] ?? null;

  const researchQueueReasons: string[] = [];
  if (!sample.exactWaterGeometryClosed) researchQueueReasons.push("RYUMYAKの正確な水形状が未閉鎖");
  if (sample.hardSplitRisk === "HIGH_EXACT_WATER_REQUIRED") researchQueueReasons.push("龍脈判定が水形状に敏感な反証・不確実地点");
  if (v10.availability !== "available") researchQueueReasons.push("V10が完全接続ではない");
  if (!underland) researchQueueReasons.push("UNDERLANDの地点レコードがない");
  if (!ecoscape) researchQueueReasons.push("ECOSCAPEの地点レコードがない");
  if (!placegraph) researchQueueReasons.push("PLACEGRAPHは当該セルに索引候補なし。不存在や安全を意味しない");
  researchQueueReasons.push("V11・VEIL・LIMEN・EVENTREG・NOMENは別Projectの成熟度を保ったまま追加接続する");

  return {
    ...sample,
    residencePriority: null,
    residenceRecommendation: null,
    lenses: {
      ryumyak: sample.zoneId
        ? {
            availability: "available",
            rank: sample.ryumyakRank,
            score: sample.ryumyakScore,
            long25: sample.long25,
            sha20: sample.sha20,
            shui30: sample.shui30,
            xueMingtang25: sample.xueMingtang25,
            stressClass: sample.stressClass,
            hardSplitRisk: sample.hardSplitRisk,
            decisionConfidence: sample.decisionConfidence,
            exactWaterGeometryClosed: sample.exactWaterGeometryClosed,
          }
        : {
            availability: "not_applicable",
            reason: "RYUMYAK eligible zoneなしの対照地点",
          },
      v10: compactV10(v10),
      underland: underland
        ? { availability: "available", ...underland }
        : { availability: "unknown" },
      ecoscape: ecoscape
        ? { availability: "available", ...ecoscape }
        : { availability: "unknown" },
      placegraph: placegraph
        ? { availability: "partial", ...placegraph, absenceClaimAllowed: false }
        : {
            availability: "partial",
            indexStatus: "NO_INDEXED_CANDIDATE_SOURCE_LIMITED",
            totalLinks: 0,
            absenceClaimAllowed: false,
          },
      staged: {
        v11: "ADAPTER_STAGED_SOURCE_LIMITED",
        veil: "ADAPTER_STAGED_SOURCE_LIMITED",
        limen: "ADAPTER_STAGED_CANDIDATE_NOT_POSITIVE",
        eventreg: "SEPARATE_READ_ONLY_CARD_PENDING_WAVE1_JOIN",
        nomen: "SEPARATE_READ_ONLY_CARD_PENDING_WAVE1_JOIN",
      },
    },
    researchQueueReasons,
  };
}

export async function GET(request: NextRequest) {
  try {
    const offset = integerParam(request.nextUrl.searchParams.get("offset"), 0, 0, NEXUS_FULL_DOMAIN_WAVE1.length, "offset");
    const limit = integerParam(request.nextUrl.searchParams.get("limit"), DEFAULT_LIMIT, 1, MAX_LIMIT, "limit");
    const municipality = cleanFilter(request.nextUrl.searchParams.get("municipality"), 40);
    const stratum = cleanFilter(request.nextUrl.searchParams.get("stratum"), 60);

    const filtered = NEXUS_FULL_DOMAIN_WAVE1.filter((sample) => {
      if (municipality && sample.municipality !== municipality) return false;
      if (stratum && sample.stratum !== stratum) return false;
      return true;
    });
    const page = filtered.slice(offset, offset + limit);
    const results = await Promise.all(page.map(enrich));
    const municipalities = [...new Set(NEXUS_FULL_DOMAIN_WAVE1.map((sample) => sample.municipality))].sort((a, b) => a.localeCompare(b, "ja"));
    const strata = [...new Set(NEXUS_FULL_DOMAIN_WAVE1.map((sample) => sample.stratum))];

    return NextResponse.json(
      {
        schemaVersion: "nexus-full-domain-discovery/1.0",
        waveVersion: NEXUS_FULL_DOMAIN_WAVE1_VERSION,
        asOfJST: NEXUS_FULL_DOMAIN_WAVE1_AS_OF_JST,
        semantics: {
          residenceRanking: false,
          syntheticTotalScore: false,
          marketInfluenceOnLandDiscovery: "none",
          ryumyakRole: "independent_research_lens",
          unknownMeansSafe: false,
        },
        notes: NEXUS_FULL_DOMAIN_WAVE1_NOTES,
        frame: {
          totalSamples: NEXUS_FULL_DOMAIN_WAVE1.length,
          municipalityCount: municipalities.length,
          samplesPerMunicipality: 5,
          municipalities,
          strata,
          filteredSamples: filtered.length,
        },
        pagination: {
          offset,
          limit,
          returned: results.length,
          nextOffset: offset + results.length < filtered.length ? offset + results.length : null,
        },
        results,
      },
      { headers: { "Cache-Control": "public, max-age=0, s-maxage=3600", "Access-Control-Allow-Origin": "*" } },
    );
  } catch (error) {
    return NextResponse.json(
      { error: "invalid_input", message: error instanceof Error ? error.message : "入力を確認してください。" },
      { status: 400 },
    );
  }
}
