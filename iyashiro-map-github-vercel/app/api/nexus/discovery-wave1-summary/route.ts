import { NextResponse } from "next/server";
import { readEcoscapeRuntime } from "@/app/lib/location-profile/ecoscape-runtime";
import { placeGraphSparseCells } from "@/app/lib/location-profile/placegraph-sparse-runtime";
import { readUnderlandRuntime } from "@/app/lib/location-profile/underland-runtime";
import { buildV10Layer } from "@/app/lib/location-profile/v10-adapter";
import {
  NEXUS_FULL_DOMAIN_WAVE1,
  NEXUS_FULL_DOMAIN_WAVE1_AS_OF_JST,
  NEXUS_FULL_DOMAIN_WAVE1_VERSION,
} from "@/app/lib/nexus/full-domain-wave1-v1";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 60;

function cellParts(cellId: string) {
  const match = /^g(\d+)-(\d+)$/.exec(cellId);
  if (!match) throw new TypeError(`不正な canonical cell ID: ${cellId}`);
  return { row: Number(match[1]), col: Number(match[2]) };
}

function mean(values: number[]) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

function pearson(pairs: Array<[number, number]>) {
  if (pairs.length < 3) return null;
  const xs = pairs.map(([x]) => x);
  const ys = pairs.map(([, y]) => y);
  const mx = mean(xs) ?? 0;
  const my = mean(ys) ?? 0;
  let numerator = 0;
  let dx2 = 0;
  let dy2 = 0;
  for (const [x, y] of pairs) {
    const dx = x - mx;
    const dy = y - my;
    numerator += dx * dy;
    dx2 += dx * dx;
    dy2 += dy * dy;
  }
  const denominator = Math.sqrt(dx2 * dy2);
  return denominator ? numerator / denominator : null;
}

function bump(record: Record<string, number>, key: string | null | undefined) {
  const normalized = key?.trim() || "UNKNOWN";
  record[normalized] = (record[normalized] ?? 0) + 1;
}

function v10Class(title: string | null) {
  if (title?.includes("イヤシロチ候補")) return "CANDIDATE";
  if (title?.includes("ケガレチ候補")) return "CAUTION";
  if (title) return "ORDINARY_OR_WEAK";
  return "UNKNOWN";
}

async function compact(sample: (typeof NEXUS_FULL_DOMAIN_WAVE1)[number]) {
  const { row, col } = cellParts(sample.cellId);
  const v10 = await buildV10Layer(row, col);
  const finding = v10.findings[0] ?? null;
  const metadata = (finding?.metadata ?? {}) as Record<string, unknown>;
  const underland = readUnderlandRuntime(row, col);
  const ecoscape = readEcoscapeRuntime(row, col);
  const placegraph = placeGraphSparseCells()[sample.cellId] ?? null;
  return {
    sampleId: sample.sampleId,
    municipality: sample.municipality,
    metro: sample.metro,
    stratum: sample.stratum,
    zoneNameJa: sample.zoneNameJa,
    townChomeTop: sample.townChomeTop,
    cellId: sample.cellId,
    ryumyakScore: sample.ryumyakScore,
    hardSplitRisk: sample.hardSplitRisk,
    v10Class: v10Class(finding?.title ?? null),
    v10Title: finding?.title ?? null,
    v10Detail: typeof metadata.detailScore === "number" ? metadata.detailScore : null,
    v10Confidence: typeof metadata.confidence === "number" ? metadata.confidence : null,
    underlandClass: underland?.moistureAttentionClass ?? "UNKNOWN",
    underlandConfidence: underland?.confidence ?? "UNKNOWN",
    ecoscapeState: ecoscape?.aggregateStateP25 ?? "UNKNOWN",
    ecoscapeRobust: ecoscape?.robustEnvironmentalCandidate ?? false,
    ecoscapeShare300m: ecoscape?.robustCandidateShare300m ?? null,
    ecoscapeShare500m: ecoscape?.robustCandidateShare500m ?? null,
    placegraphLinks: placegraph?.totalLinks ?? 0,
  };
}

function publicItem(item: Awaited<ReturnType<typeof compact>>) {
  return {
    sampleId: item.sampleId,
    municipality: item.municipality,
    metro: item.metro,
    stratum: item.stratum,
    zoneNameJa: item.zoneNameJa,
    townChomeTop: item.townChomeTop,
    cellId: item.cellId,
    ryumyakScore: item.ryumyakScore,
    v10Class: item.v10Class,
    underlandClass: item.underlandClass,
    ecoscapeState: item.ecoscapeState,
    ecoscapeRobust: item.ecoscapeRobust,
    placegraphLinks: item.placegraphLinks,
  };
}

export async function GET() {
  try {
    const rows = await Promise.all(NEXUS_FULL_DOMAIN_WAVE1.map(compact));
    const strata = [...new Set(rows.map((row) => row.stratum))];
    const byStratum = Object.fromEntries(strata.map((stratum) => {
      const subset = rows.filter((row) => row.stratum === stratum);
      const v10Classes: Record<string, number> = {};
      const underlandClasses: Record<string, number> = {};
      const ecoscapeStates: Record<string, number> = {};
      subset.forEach((row) => {
        bump(v10Classes, row.v10Class);
        bump(underlandClasses, row.underlandClass);
        bump(ecoscapeStates, row.ecoscapeState);
      });
      return [stratum, {
        samples: subset.length,
        ryumyakMean: mean(subset.flatMap((row) => typeof row.ryumyakScore === "number" ? [row.ryumyakScore] : [])),
        v10DetailMean: mean(subset.flatMap((row) => typeof row.v10Detail === "number" ? [row.v10Detail] : [])),
        v10Classes,
        underlandClasses,
        ecoscapeStates,
        ecoscapeRobustCount: subset.filter((row) => row.ecoscapeRobust).length,
        ecoscapeShare300mMean: mean(subset.flatMap((row) => typeof row.ecoscapeShare300m === "number" ? [row.ecoscapeShare300m] : [])),
        ecoscapeShare500mMean: mean(subset.flatMap((row) => typeof row.ecoscapeShare500m === "number" ? [row.ecoscapeShare500m] : [])),
        placegraphIndexedCount: subset.filter((row) => row.placegraphLinks > 0).length,
      }];
    }));

    const eligible = rows.filter((row) => typeof row.ryumyakScore === "number");
    const correlationPairsV10 = eligible.flatMap((row) => typeof row.v10Detail === "number" ? [[row.ryumyakScore as number, row.v10Detail] as [number, number]] : []);
    const correlationPairsEco = eligible.flatMap((row) => typeof row.ecoscapeShare300m === "number" ? [[row.ryumyakScore as number, row.ecoscapeShare300m] as [number, number]] : []);

    const isHigh = (row: (typeof rows)[number]) => row.stratum === "A_LOCAL_TOP" || row.stratum === "B_UPPER_QUARTILE";
    const isLow = (row: (typeof rows)[number]) => row.stratum === "E_LOCAL_BOTTOM_CONTROL";
    const ecoPositive = (row: (typeof rows)[number]) => row.ecoscapeRobust || row.ecoscapeState === "CANDIDATE";
    const ecoCaution = (row: (typeof rows)[number]) => row.ecoscapeState === "CAUTION";
    const underlandAttention = (row: (typeof rows)[number]) => row.underlandClass !== "low" && row.underlandClass !== "LOW";

    const convergence = rows.filter((row) => isHigh(row) && row.v10Class === "CANDIDATE" && ecoPositive(row) && !underlandAttention(row));
    const contradiction = rows.filter((row) => isHigh(row) && (row.v10Class === "CAUTION" || ecoCaution(row) || underlandAttention(row)));
    const counterexample = rows.filter((row) => isLow(row) && (row.v10Class === "CANDIDATE" || ecoPositive(row)));
    const uncertainty = rows.filter((row) => row.stratum === "D_UNCERTAINTY_REVIEW" || row.stratum === "F_NO_RYUMYAK_ELIGIBLE_ZONE_CONTROL");

    const placegraphIndexed = rows.filter((row) => row.placegraphLinks > 0);
    const v10Available = rows.filter((row) => row.v10Title !== null);
    const underlandAvailable = rows.filter((row) => row.underlandClass !== "UNKNOWN");
    const ecoscapeAvailable = rows.filter((row) => row.ecoscapeState !== "UNKNOWN");

    return NextResponse.json({
      schemaVersion: "nexus-full-domain-wave1-summary/1.0",
      waveVersion: NEXUS_FULL_DOMAIN_WAVE1_VERSION,
      asOfJST: NEXUS_FULL_DOMAIN_WAVE1_AS_OF_JST,
      semantics: {
        residenceRanking: false,
        syntheticTotalScore: false,
        queuesAreResearchPrioritiesNotResidenceRecommendations: true,
        correlationIsDescriptiveNotCausal: true,
        unknownMeansSafe: false,
      },
      frame: {
        samples: rows.length,
        municipalities: new Set(rows.map((row) => row.municipality)).size,
        eligibleRyumyakSamples: eligible.length,
        noEligibleZoneControls: rows.length - eligible.length,
      },
      coverage: {
        v10Available: v10Available.length,
        underlandAvailable: underlandAvailable.length,
        ecoscapeAvailable: ecoscapeAvailable.length,
        placegraphIndexed: placegraphIndexed.length,
        placegraphSourceLimitedOrNoIndex: rows.length - placegraphIndexed.length,
        stagedLenses: ["V11", "VEIL", "LIMEN", "EVENTREG", "NOMEN"],
      },
      byStratum,
      descriptiveRelationships: {
        ryumyakVsV10DetailPearson: pearson(correlationPairsV10),
        ryumyakVsEcoscape300mSharePearson: pearson(correlationPairsEco),
        note: "相関は探索標本内の記述値で、因果・効能・居住適性を意味しません。",
      },
      researchQueues: {
        convergence: { count: convergence.length, items: convergence.slice(0, 30).map(publicItem) },
        contradiction: { count: contradiction.length, items: contradiction.slice(0, 30).map(publicItem) },
        counterexample: { count: counterexample.length, items: counterexample.slice(0, 30).map(publicItem) },
        uncertainty: { count: uncertainty.length, items: uncertainty.slice(0, 60).map(publicItem) },
      },
      nextGate: "Wave2は収束・矛盾・反例・不確実の各群から均衡抽出し、V11・VEIL・LIMEN・EVENTREG・NOMENを追加接続する。",
    }, { headers: { "Cache-Control": "public, max-age=0, s-maxage=3600", "Access-Control-Allow-Origin": "*" } });
  } catch (error) {
    return NextResponse.json({ error: "summary_failed", message: error instanceof Error ? error.message : "集計に失敗しました。" }, { status: 500 });
  }
}
