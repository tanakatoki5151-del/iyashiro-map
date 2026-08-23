import "server-only";

import { diagnoseLocation, type DiagnosisResult } from "@/app/lib/diagnose";
import { ApiError } from "@/app/lib/integration-api/errors";
import { buildCellProfile, type IntegratedCellProfile } from "@/app/lib/integration-api/profile";
import {
  hasMeaningfulRyumyakData,
  hasMeaningfulV153Data,
} from "@/app/lib/integration-api/profile-shape";
import { parseResolveInput, resolveLocation } from "@/app/lib/integration-api/resolution";
import type { LocationResolution } from "@/app/lib/integration-api/types";
import { buildV10Layer } from "@/app/lib/location-profile/v10-adapter";
import type { LocationLayer } from "@/app/lib/location-profile/types";
import type {
  DossierItem,
  DossierStatus,
  LandDossier,
  MissingInformation,
} from "@/app/lib/land-dossier-types";

type UnknownRecord = Record<string, unknown>;
type CandidateEvidence = {
  cellId: string;
  weight: number;
  profile: IntegratedCellProfile;
  v10: LocationLayer;
};

const THRESHOLD_M = 500 as const;
const CELL_CENTER_MAX_POSITION_ERROR_M = 71 as const;

const JAPANESE_CODES: Record<string, string> = {
  PLATEAU: "台地",
  HILL_RIDGE: "丘陵・尾根",
  LOWLAND_PLAIN: "低地・平野",
  VALLEY_LOWLAND: "谷底低地",
  VALLEY: "谷地形",
  HILLSIDE: "斜面地",
  D_MAINTENANCE_UNCERTAINTY: "流れの維持状態は資料不足のため要確認",
  OPEN_NOT_MATERIALIZED: "現在の水路情報は未反映",
  LOW_NO_BOUNDED_SPLIT_SIGNAL: "明確な分断の兆候は弱い",
  MEDIUM_REVIEW: "分断の可能性を追加確認",
  HIGH_REVIEW: "分断の可能性が高く要確認",
  P7_FORMALLY_CLOSED__EVIDENCE_DENSITY_OPEN:
    "P7は形式上完了。ただし証拠密度の拡充余地あり",
  VEIL_WITHIN_100M_NARRATIVE_CONTEXT: "100m以内に物語・伝承系の文脈あり",
  VEIL_WITHIN_300M_NARRATIVE_CONTEXT: "300m以内に物語・伝承系の文脈あり",
  VEIL_WITHIN_500M_NARRATIVE_CONTEXT: "500m以内に物語・伝承系の文脈あり",
  VEIL_MUNICIPAL_UNLOCATED_CONTEXT:
    "自治体単位の文脈はあるが地点を特定できていない",
  L4_NO_KNOWN_RELATION_CURRENT_SNAPSHOT:
    "現在の索引では既知の関連なし。ただし不存在や安全の証明ではない",
  A_BUILT_UP_CONTINUITY: "現在の市街地としての連続性が高い",
  B_CURRENT_BUILDINGS_HISTORIC_REVIEW: "現建物と過去の土地利用の対応を要確認",
  HISTORIC_NONRESIDENTIAL_REVIEW: "過去の非住宅利用を要確認",
  NEUTRAL: "中立",
  MIXED: "良否が混在",
  CAUTION: "注意材料あり",
  low: "低い",
  moderate: "中程度",
  elevated: "高め",
  reference_only: "参考情報のみ",
  upland_5m_model: "台地型・地下水深およそ5mのモデル",
  shallow_model: "浅い地下水を想定するモデル",
  other_materialized_model: "その他の実装済み地下水モデル",
};

const FACT_TITLES: Record<string, string> = {
  temple: "寺院",
  cemetery: "墓地",
  large_hospital: "大規模・入院病院",
  strong_history: "強い歴史事象",
  p8: "P8重大履歴",
  shrine: "神社（参考）",
  general_hospital: "一般病院（参考）",
};

function asRecord(value: unknown): UnknownRecord | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as UnknownRecord)
    : null;
}

function text(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (
    typeof value === "string" &&
    value.trim() &&
    Number.isFinite(Number(value))
  ) {
    return Number(value);
  }
  return null;
}

function japanese(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "資料不足・未確認";
  }
  if (typeof value === "boolean") return value ? "あり" : "なし";
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value !== "string") return "記録あり（詳しい説明は整備中）";
  const normalized = value.trim();
  if (!normalized) return "資料不足・未確認";
  if (JAPANESE_CODES[normalized]) return JAPANESE_CODES[normalized];
  if (/https?:\/\//i.test(normalized)) return "出典リンクあり";
  if (/[ぁ-んァ-ヶ一-龠々]/u.test(normalized)) return normalized;
  if (/^[A-Za-z0-9_ -]+$/.test(normalized)) {
    return "区分記録あり（日本語説明を整備中）";
  }
  return normalized;
}

function distanceLabel(distanceM: number | null): string {
  if (distanceM === null) return "距離は未確認";
  if (distanceM < 1_000) return Math.round(distanceM) + "m";
  return (distanceM / 1_000).toFixed(1) + "km";
}

function coverageLabel(value: unknown): string {
  const normalized = text(value)?.toLowerCase() ?? "unknown";
  if (normalized === "complete" || normalized === "complete_for_defined_sources") {
    return "確認対象資料の範囲では確認済み";
  }
  if (normalized === "partial" || normalized === "partial_known_sources") {
    return "一部の資料のみ確認済み";
  }
  if (normalized === "source_limited") return "資料範囲が限定的";
  if (normalized === "not_scanned") return "未走査";
  return "資料不足・未確認";
}

function stabilityLabel(value: string): string {
  if (value === "STABLE") return "選択地点の100m区画は安定";
  if (value === "LEANING") return "主な100m区画は特定済み";
  if (value === "AMBIGUOUS") return "複数の100m区画にまたがる可能性あり";
  return "100m区画を一意に確定できていない";
}

function resolutionCoverageLabel(value: string): string {
  if (value === "VALIDATED") return "対象区画を正本台帳で確認済み";
  if (value === "PARTIAL") return "対象範囲の一部だけ確認済み";
  if (value === "NO_VALID_CELL") return "対象区画なし";
  return "統合データを確認できていない";
}

function profileFact(
  profile: IntegratedCellProfile,
  factId: string,
): UnknownRecord | null {
  for (const raw of profile.facts) {
    const fact = asRecord(raw);
    if (text(fact?.factId) === factId) return fact;
  }
  return null;
}

function sourceTitle(fact: UnknownRecord | null): string {
  const sources = Array.isArray(fact?.sources) ? fact.sources : [];
  for (const raw of sources) {
    const source = asRecord(raw);
    const title = text(source?.title) ?? text(source?.project);
    if (title) return title;
  }
  return "関連する根拠資料は未特定";
}

function aggregateFact(
  candidates: CandidateEvidence[],
  resolution: LocationResolution,
  factId: string,
  options: {
    hardGate: boolean;
    explanation: string;
    title?: string;
  },
): DossierItem {
  const evidence = candidates.flatMap((candidate) => {
    const fact = profileFact(candidate.profile, factId);
    if (!fact) return [];
    const finding = asRecord(fact.finding);
    const value = asRecord(finding?.value);
    const coverage = asRecord(fact.coverage);
    const explicitUncertaintyM = numberValue(
      finding?.uncertaintyMeters ??
      value?.uncertaintyMeters ??
      value?.uncertaintyM ??
      value?.precisionMeters ??
      value?.precisionM,
    );
    return [{
      cellId: candidate.cellId,
      weight: candidate.weight,
      fact,
      value,
      coverage: text(coverage?.state) ?? "unknown",
      distanceM: numberValue(value?.distanceM ?? value?.distance_m),
      uncertaintyM:
        explicitUncertaintyM !== null && explicitUncertaintyM >= 0
          ? explicitUncertaintyM
          : CELL_CENTER_MAX_POSITION_ERROR_M,
    }];
  });
  const distances = evidence
    .filter((item) => item.distanceM !== null)
    .sort((left, right) => left.distanceM! - right.distanceM!);
  const nearest = distances[0] ?? null;
  const hits = distances.filter((item) => item.distanceM! <= THRESHOLD_M);
  const boundaryRisks = distances.filter(
    (item) =>
      item.distanceM! > THRESHOLD_M &&
      item.distanceM! - item.uncertaintyM <= THRESHOLD_M,
  );
  const fullyChecked =
    resolution.coverage.status === "VALIDATED" &&
    evidence.length === candidates.length &&
    evidence.every((item) => item.coverage === "complete") &&
    evidence.every((item) => item.distanceM !== null);
  let status: DossierStatus;
  if (options.hardGate && hits.length) status = "avoid";
  else if (options.hardGate && fullyChecked && boundaryRisks.length === 0) {
    status = "current_clear";
  }
  else if (options.hardGate && evidence.length) status = "review";
  else if (options.hardGate) status = "unknown";
  else status = nearest ? "context" : "unknown";

  const nearestName =
    text(nearest?.value?.nearestName) ??
    text(nearest?.value?.nearest_name) ??
    "名称未収録";
  const nearestAddress =
    text(nearest?.value?.nearestAddress) ??
    text(nearest?.value?.nearest_address);
  const affectedWeight = hits.reduce((sum, item) => sum + item.weight, 0);
  const summary =
    status === "avoid"
      ? nearestName +
        "が最短" +
        distanceLabel(nearest?.distanceM ?? null) +
        "。500m以内のため、第一段階の停止条件に該当します。"
      : status === "current_clear"
        ? "確認できた全候補区画で、最短" +
          distanceLabel(nearest?.distanceM ?? null) +
          "。位置誤差を安全側に差し引いても500mの外側です。"
        : boundaryRisks.length
          ? nearestName +
            "までセル中心基準で最短" +
            distanceLabel(nearest?.distanceM ?? null) +
            "。最大" +
            distanceLabel(nearest?.uncertaintyM ?? null) +
            "の位置誤差を考えると500m以内の可能性があるため、要確認です。"
        : nearest
          ? nearestName +
            "まで最短" +
            distanceLabel(nearest.distanceM) +
            "。距離は分かりますが、資料網羅性が不足しています。"
          : "距離または対象施設を確認できる資料が未接続です。";

  const states = [...new Set(evidence.map((item) => item.coverage))];
  return {
    id: factId,
    title: options.title ?? FACT_TITLES[factId] ?? factId,
    status,
    summary,
    explanation: options.explanation,
    details: [
      { label: "最短距離（セル中心基準）", value: distanceLabel(nearest?.distanceM ?? null) },
      ...(nearest
        ? [
            { label: "位置誤差（最大）", value: distanceLabel(nearest.uncertaintyM) },
            {
              label: "安全側の最短見込み",
              value: distanceLabel(Math.max(0, nearest.distanceM! - nearest.uncertaintyM)),
            },
          ]
        : []),
      { label: "最寄り名称", value: nearestName },
      ...(nearestAddress ? [{ label: "所在地", value: nearestAddress }] : []),
      { label: "確認した候補区画", value: candidates.length + "区画" },
      ...(hits.length
        ? [
            { label: "閾値内の候補区画", value: hits.length + "区画" },
            {
              label: "閾値内となる位置確率",
              value: Math.round(affectedWeight * 100) + "%",
            },
          ]
        : []),
    ],
    coverage:
      states.length === 1
        ? coverageLabel(states[0])
        : "候補区画により資料状態が異なります",
    source: sourceTitle(nearest?.fact ?? evidence[0]?.fact ?? null),
  };
}

function modernCard(
  diagnosis: DiagnosisResult,
  key: string,
  explanation: string,
): DossierItem {
  const item = diagnosis.modern.items.find((candidate) => candidate.key === key);
  if (!item) {
    return {
      id: key,
      title: key,
      status: "unknown",
      summary: "この項目の資料が応答に含まれていません。",
      explanation,
      details: [],
      coverage: "資料不足・未確認",
      source: "出典未確認",
    };
  }
  const status: DossierStatus =
    item.status !== "known" || item.score === null
      ? "unknown"
      : item.score >= 60
        ? "review"
        : "available";
  return {
    id: item.key,
    title: item.label,
    status,
    summary:
      item.detail +
      (item.score === null ? "" : "。参考リスク指数は" + item.score + "/100です。"),
    explanation,
    details: [
      {
        label: "情報状態",
        value: item.status === "known" ? "公開資料で確認" : "資料不足・未確認",
      },
      {
        label: "参考リスク指数",
        value: item.score === null ? "算出不能" : item.score + "/100（高いほど注意）",
      },
    ],
    coverage:
      item.status === "known"
        ? "公開地図の対象地点を照合済み"
        : "未着色・区域外・未整備を区別できません",
    source: item.source,
  };
}

function contextCard(input: {
  id: string;
  title: string;
  values: Array<{ label: string; value: unknown }>;
  explanation: string;
  source: string;
  forceUnknown?: boolean;
}): DossierItem {
  const known = input.values.filter(
    (entry) => entry.value !== null && entry.value !== undefined && entry.value !== "",
  );
  const unknown = input.forceUnknown || !known.length;
  return {
    id: input.id,
    title: input.title,
    status: unknown ? "unknown" : "context",
    summary: unknown
      ? "この項目はまだ十分な資料と接続できていません。"
      : known.map((entry) => entry.label + "は" + japanese(entry.value)).join("。") + "。",
    explanation: input.explanation,
    details: input.values.map((entry) => ({
      label: entry.label,
      value: japanese(entry.value),
    })),
    coverage: unknown
      ? "資料不足・未確認"
      : "統合正本に収録された範囲の参考情報",
    source: input.source,
  };
}

function hasR3LensRecord(candidate: CandidateEvidence): boolean {
  const gate = asRecord(candidate.profile.layers.R3_PERSONAL_GATE);
  return text(gate?.availability) === "available";
}

function hasV153AxisRecord(candidate: CandidateEvidence): boolean {
  return hasR3LensRecord(candidate) &&
    hasMeaningfulV153Data(candidate.profile.layers.V15_3);
}

function hasRyumyakAxisRecord(candidate: CandidateEvidence): boolean {
  return hasR3LensRecord(candidate) &&
    hasMeaningfulRyumyakData(candidate.profile.layers.RYUMYAK);
}

function v153Card(
  candidates: CandidateEvidence[],
  primaryCellId: string,
): DossierItem {
  const layers = candidates.flatMap((candidate) => {
    if (!hasV153AxisRecord(candidate)) return [];
    const layer = asRecord(candidate.profile.layers.V15_3);
    return layer ? [{ candidate, layer }] : [];
  });
  const primaryCandidate =
    candidates.find((candidate) => candidate.cellId === primaryCellId) ?? null;
  const primary =
    primaryCandidate && hasV153AxisRecord(primaryCandidate)
      ? asRecord(primaryCandidate.profile.layers.V15_3)
      : null;
  const secondaryLayerCount = layers.filter(
    ({ candidate }) => candidate.cellId !== primaryCellId,
  ).length;
  const ranks = layers
    .map(({ layer }) => numberValue(layer.rank))
    .filter((rank): rank is number => rank !== null);
  const zoneIds = [...new Set(layers.flatMap(({ layer }) => {
    const zoneId = text(layer.zone);
    return zoneId ? [zoneId] : [];
  }))];
  const regimes = [...new Set(layers.map(({ layer }) => japanese(layer.regime)))];
  const primaryRank = numberValue(primary?.rank);
  return {
    id: "iyashiro-v153",
    title: "V15.3 現行版",
    status: primary ? "available" : "unknown",
    summary: primary
      ? "現行のイヤシロジ／テライン仮説です。主区画の順位は" +
        (primaryRank === null ? "未収録" : primaryRank + "位") +
        "、地形・地勢区分は" +
        japanese(primary.regime) +
        "です。"
      : secondaryLayerCount > 0
        ? "主区画のV15.3地点情報は未収録です。隣接する候補" +
          secondaryLayerCount +
          "区画には参考値がありますが、主区画の現行値としては扱いません。"
        : "V15.3の地点情報が主区画にも隣接候補にも収録されていません。",
    explanation:
      "土地そのものを見る一本目の主軸です。順位・V15.3区画ID・地形や地勢の区分を、龍脈とは混ぜずに読みます。",
    details: [
      { label: "主区画の正本順位", value: primaryRank === null ? "未収録" : primaryRank + "位" },
      { label: "候補区画の順位幅", value: ranks.length ? Math.min(...ranks) + "〜" + Math.max(...ranks) + "位" : "未収録" },
      { label: "V15.3区画ID", value: zoneIds.join("／") || "資料不足・未確認" },
      { label: "地形・地勢区分", value: regimes.join("／") || "資料不足・未確認" },
      { label: "確認した候補区画", value: candidates.length + "区画" },
      { label: "V15.3収録済み候補区画", value: layers.length + "／" + candidates.length + "区画" },
    ],
    coverage: primary
      ? "主区画のV15.3統合正本を確認"
      : secondaryLayerCount > 0
        ? "主区画は資料不足。副候補の値は参考表示のみ"
        : "資料不足・未確認",
    source: "ALL_PROJECT_INTEGRATED_TOP20 R3 / V15.3",
  };
}

function v10Card(
  candidates: CandidateEvidence[],
  primaryCellId: string,
): DossierItem {
  const findings = candidates.flatMap((candidate) => {
    const finding = candidate.v10.findings[0];
    return finding
      ? [{ candidate, finding, metadata: asRecord(finding.metadata) }]
      : [];
  });
  const primary =
    findings.find(({ candidate }) => candidate.cellId === primaryCellId) ?? null;
  const titles = [...new Set(findings.map(({ finding }) => finding.title))];
  const originalScores = [
    ...new Set(findings.map(({ metadata }) => japanese(metadata?.originalScore))),
  ];
  const explanations = [
    ...new Set(findings.map(({ finding }) => finding.explanation)),
  ];
  const hasCandidateVariation =
    titles.length > 1 || originalScores.length > 1 || explanations.length > 1;
  return {
    id: "iyashiro-v10",
    title: "V10 比較用・過去基準",
    status: findings.length ? "context" : "unknown",
    summary: primary
      ? "候補" +
        findings.length +
        "区画のV10を確認し、" +
        (hasCandidateVariation
          ? "候補区画間で判定または説明に差異があります。"
          : "候補区画間の判定は一致しています。") +
        primary.finding.explanation
      : findings.length
        ? "主候補のV10は未収録です。副候補" +
          findings.length +
          "区画の値は比較用の参考として表示します。"
        : "V10の凍結データを取得できませんでした。推測値は作っていません。",
    explanation:
      "V15.3へ移る前の比較用基準です。現行判定へ混ぜたり平均したりせず、判断がどう変わったかを見るために残します。",
    details: [
      { label: "候補区画の凍結判定幅", value: titles.join("／") || "資料不足・未確認" },
      { label: "候補区画の原典判定幅", value: originalScores.join("／") || "資料不足・未確認" },
      {
        label: "候補区画間の差異",
        value: hasCandidateVariation ? "あり（区画ごとの内訳を確認）" : "なし",
      },
      {
        label: "区画ごとの判定",
        value: findings.length
          ? findings
              .map(({ candidate, finding, metadata }) =>
                candidate.cellId + ": " + finding.title + "／原典 " + japanese(metadata?.originalScore),
              )
              .join("、")
          : "資料不足・未確認",
      },
      { label: "主候補の原典適合", value: japanese(primary?.metadata?.originalFit) },
      { label: "主候補の補助地形", value: japanese(primary?.metadata?.auxiliaryTerrainScore) },
      { label: "主候補の地点詳細", value: japanese(primary?.metadata?.detailScore) },
      { label: "主候補の周辺", value: japanese(primary?.metadata?.neighborhoodScore) },
      { label: "主候補の信頼度", value: japanese(primary?.metadata?.confidence) },
    ],
    coverage: primary
      ? findings.length === candidates.length
        ? "主候補を含む全候補区画のV10凍結データを確認"
        : "主候補は確認済み。一部副候補のV10が資料不足"
      : findings.length
        ? "主候補は資料不足。副候補のV10は参考表示のみ"
        : "V10は資料不足・未確認",
    source: "V10 frozen regional catalog v4",
  };
}

function ryumyakCard(
  candidates: CandidateEvidence[],
  primaryCellId: string,
): DossierItem {
  const layers = candidates.flatMap((candidate) => {
    if (!hasRyumyakAxisRecord(candidate)) return [];
    const layer = asRecord(candidate.profile.layers.RYUMYAK);
    return layer ? [{ candidate, layer }] : [];
  });
  const primaryCandidate =
    candidates.find((candidate) => candidate.cellId === primaryCellId) ?? null;
  const primary =
    primaryCandidate && hasRyumyakAxisRecord(primaryCandidate)
      ? asRecord(primaryCandidate.profile.layers.RYUMYAK)
      : null;
  const secondaryLayerCount = layers.filter(
    ({ candidate }) => candidate.cellId !== primaryCellId,
  ).length;
  const ranks = layers
    .map(({ layer }) => numberValue(layer.rank))
    .filter((rank): rank is number => rank !== null);
  const primaryRank = numberValue(primary?.rank);
  return {
    id: "ryumyak-current",
    title: "龍脈 現行正本",
    status: primary ? "available" : "unknown",
    summary: primary
      ? "主区画の龍脈順位は" +
        (primaryRank === null ? "未収録" : primaryRank + "位") +
        "。ゾーンは" +
        japanese(primary.zone) +
        "です。"
      : secondaryLayerCount > 0
        ? "主区画の龍脈地点情報は未収録です。隣接する候補" +
          secondaryLayerCount +
          "区画には参考値がありますが、主区画の龍脈値としては扱いません。"
        : "龍脈の地点情報が主区画にも隣接候補にも収録されていません。",
    explanation:
      "土地そのものを見る二本目の独立した主軸です。イヤシロジとは別の順位・ゾーン・水系や分断の状態として読みます。",
    details: [
      { label: "主区画の正本順位", value: primaryRank === null ? "未収録" : primaryRank + "位" },
      { label: "候補区画の順位幅", value: ranks.length ? Math.min(...ranks) + "〜" + Math.max(...ranks) + "位" : "未収録" },
      { label: "龍脈ゾーン", value: japanese(primary?.zone) },
      { label: "エリア", value: japanese(primary?.area) },
      { label: "確度", value: japanese(primary?.confidence) },
      { label: "現在の水路", value: japanese(primary?.currentWater) },
      { label: "分断の状態", value: japanese(primary?.hardSplit) },
      { label: "確認した候補区画", value: candidates.length + "区画" },
      { label: "龍脈収録済み候補区画", value: layers.length + "／" + candidates.length + "区画" },
    ],
    coverage: primary
      ? "主区画の龍脈統合正本を確認"
      : secondaryLayerCount > 0
        ? "主区画は資料不足。副候補の値は参考表示のみ"
        : "資料不足・未確認",
    source: "ALL_PROJECT_INTEGRATED_TOP20 R3 / RYUMYAK",
  };
}

function httpPointer(value: unknown): string | null {
  const pointer = text(value);
  if (!pointer) return null;
  try {
    const url = new URL(pointer);
    return url.protocol === "https:" || url.protocol === "http:"
      ? pointer
      : null;
  } catch {
    return null;
  }
}

function sourceList(profile: IntegratedCellProfile): LandDossier["sources"] {
  const release = asRecord(profile.release);
  const sources = Array.isArray(release?.sources) ? release.sources : [];
  return sources.flatMap((raw) => {
    const source = asRecord(raw);
    if (!source) return [];
    const project = text(source.project) ?? "INTEGRATED_DATA";
    return [{
      title: text(source.title) ?? project,
      project,
      version: text(source.version),
      pointer: httpPointer(source.pointer),
    }];
  });
}

function missingItems(
  v10: DossierItem,
  resolution: LocationResolution,
): MissingInformation[] {
  const items: MissingInformation[] = [
    {
      id: "cemetery-permits",
      priority: "high",
      title: "25自治体の墓地許可台帳",
      currentState:
        "現在は公開地図由来の位置情報が中心で、自治体の許可台帳を全件照合した状態ではありません。",
      nextAction:
        "各自治体への照会・公開簿の取得後、施設正本へ重複確認付きで追加します。",
    },
    {
      id: "waterways",
      priority: "high",
      title: "現在の水路・暗渠の形状",
      currentState:
        "龍脈正本には未反映という状態が記録され、専用の水路形状を地点へ重ねる処理はまだありません。",
      nextAction:
        "河川・水路・暗渠の正本を100m区画へ接続し、現在水系と旧水系を分けて表示します。",
    },
    {
      id: "p8-p18",
      priority: "high",
      title: "P8と「P18」の対応確認",
      currentState:
        "現在のサイト契約と統合正本にあるのはP8です。P18という土地履歴レイヤーは確認できていません。",
      nextAction:
        "元プロジェクトの目録・成果物名・仕様を照合し、同じものか別成果物かを確定します。",
    },
    {
      id: "place-name-origin",
      priority: "medium",
      title: "地名の由来",
      currentState:
        "NOMENには全区画対応データがありますが、複数差分の適用順を確定しておらずサイトへ未接続です。",
      nextAction:
        "NOMEN現行masterとR2/R6/R7差分の優先順を固定し、由来本文と一次出典を100m区画へ接続します。",
    },
    {
      id: "facility-official-linkage",
      priority: "medium",
      title: "寺院・神社の公式情報との突合",
      currentState:
        "位置は公開地図を中心に確認済みですが、公式サイトや宗教法人名簿との全件突合は一部です。",
      nextAction:
        "名称なし施設と同名施設を公式情報で照合し、誤同定を減らします。",
    },
  ];
  if (v10.status === "unknown") {
    items.push({
      id: "v10-runtime",
      priority: "high",
      title: "V10比較データ",
      currentState: "V10の凍結カタログを今回の応答では取得できませんでした。",
      nextAction: "Drive上の凍結正本とSHA-256を確認し、読取経路を復旧します。",
    });
  }
  if (resolution.stability !== "STABLE") {
    items.push({
      id: "cell-boundary",
      priority: "medium",
      title: "選択地点の100m区画境界",
      currentState:
        "住所や座標の誤差により複数区画が候補です。停止条件は全候補をまとめて確認しています。",
      nextAction:
        "建物入口または敷地代表点を確認すると、主区画をより安定して選べます。",
    });
  }
  return items;
}

export async function buildLandDossier(input: {
  lat?: number;
  lng?: number;
  address?: string;
  labelHint?: string;
}): Promise<LandDossier> {
  const hasCoordinates = Number.isFinite(input.lat) && Number.isFinite(input.lng);
  const resolution = await resolveLocation(
    parseResolveInput(
      hasCoordinates
        ? { lat: input.lat, lon: input.lng }
        : { address: input.address },
    ),
  );
  if (!resolution.primaryCellId || !resolution.cells.length) {
    throw new ApiError(422, "no_valid_cell", "対象となる100m区画を確定できませんでした。");
  }

  const lat = resolution.query.lat;
  const lng = resolution.query.lon;
  const diagnosisPromise = diagnoseLocation(lat, lng);
  const candidates = await Promise.all(
    resolution.cells.map(async (cell): Promise<CandidateEvidence> => {
      const [profile, v10] = await Promise.all([
        buildCellProfile(cell.cellId),
        buildV10Layer(cell.row, cell.col),
      ]);
      return { cellId: cell.cellId, weight: cell.weight, profile, v10 };
    }),
  );
  const diagnosis = await diagnosisPromise;
  const primary =
    candidates.find((candidate) => candidate.cellId === resolution.primaryCellId) ??
    candidates[0];
  const context = asRecord(primary.profile.layers.LEGACY_CONTEXT);

  const hardAvoids = [
    aggregateFact(candidates, resolution, "temple", {
      hardGate: true,
      explanation:
        "寺院との距離を500m基準で確認します。位置資料が限定的な場合は、閾値外でも安全とは断定しません。",
    }),
    aggregateFact(candidates, resolution, "cemetery", {
      hardGate: true,
      explanation:
        "墓地との距離です。公開位置で見つかった近接は停止条件に使いますが、許可台帳未接続のため未発見を不存在とは扱いません。",
    }),
    aggregateFact(candidates, resolution, "large_hospital", {
      hardGate: true,
      explanation:
        "死亡を伴う入院機能を持つ可能性が高い大規模病院を、一般診療所と分けて確認します。",
    }),
    aggregateFact(candidates, resolution, "strong_history", {
      hardGate: true,
      explanation:
        "大量死・重大事件・火葬場など、強い歴史事象として位置を確認できた資料との距離です。",
    }),
    aggregateFact(candidates, resolution, "p8", {
      hardGate: true,
      title: "P8重大履歴",
      explanation:
        "現行正本でP8と呼ばれる埋葬・旧施設等の重大履歴です。「P18」という別レイヤーは未確認です。",
    }),
  ];
  const stageStatus: LandDossier["stageOne"]["status"] =
    hardAvoids.some((item) => item.status === "avoid")
      ? "avoid"
      : hardAvoids.every((item) => item.status === "current_clear")
        ? "current_clear"
        : "review";

  const v153 = v153Card(candidates, primary.cellId);
  const v10 = v10Card(candidates, primary.cellId);
  const ryumyak = ryumyakCard(candidates, primary.cellId);
  const currentWater = asRecord(primary.profile.layers.RYUMYAK)?.currentWater;

  const historyItems = [
    hardAvoids[3],
    hardAvoids[4],
    contextCard({
      id: "event-history",
      title: "死亡事象の登録",
      values: [
        { label: "登録死者数", value: context?.eventregFatalities },
        { label: "500m以内の登録件数", value: context?.eventregWithin500m },
      ],
      explanation:
        "位置を特定できた死亡事象の登録です。0件は未調査・未登録の可能性があり、安全の証明ではありません。",
      source: "R3 EVENTREG context",
    }),
    contextCard({
      id: "p7-history",
      title: "P7時代別履歴",
      values: [
        { label: "確認できた時代数", value: context?.p7KnownEras },
        { label: "資料状態", value: context?.p7State },
      ],
      explanation:
        "時代別に土地履歴の資料がどこまで揃っているかを見る補助情報です。",
      source: "R3 P7 context",
    }),
    contextCard({
      id: "veil-history",
      title: "伝承・事件文脈",
      values: [
        { label: "500m以内の記録数", value: context?.veilWithin500mCount },
        { label: "状態", value: context?.veilState },
      ],
      explanation:
        "伝承・事件・語りの文脈です。物理的事実とは分け、記録なしを安全とは扱いません。",
      source: "R3 VEIL context",
    }),
    contextCard({
      id: "placegraph",
      title: "場所どうしの関係索引",
      values: [
        { label: "索引状態", value: context?.placegraphStatus },
        { label: "同一性の衝突", value: context?.identityConflicts },
      ],
      explanation:
        "同じ場所の別名や、場所と出来事の関係を結ぶ索引です。未発見は不存在を意味しません。",
      source: "R3 PLACEGRAPH context",
    }),
    contextCard({
      id: "place-name-origin",
      title: "地名の由来",
      values: [],
      forceUnknown: true,
      explanation:
        "NOMENには由来データがありますが、現行差分の適用順を固定してから接続します。",
      source: "NOMEN（接続準備中）",
    }),
  ];

  const sections: LandDossier["sections"] = [
    {
      id: "terrain",
      title: "地形",
      intro: "V15.3の地形区分と、公開標高・土砂災害資料を分けて確認します。",
      items: [
        v153,
        modernCard(diagnosis, "slope", "地点周辺の標高差から傾斜角を計算した参考値です。"),
        modernCard(
          diagnosis,
          "landslide",
          "国の土砂災害公開レイヤーです。未着色は区域外と未整備を区別できません。",
        ),
      ],
    },
    {
      id: "water",
      title: "水",
      intro: "洪水・内水・高潮・津波・低湿地と、地下水・現在水系を別々に表示します。",
      items: [
        modernCard(diagnosis, "flood", "洪水浸水想定の公開着色を確認します。"),
        modernCard(diagnosis, "innerWater", "内水浸水の公開着色を確認します。"),
        modernCard(diagnosis, "highTide", "高潮浸水想定の公開着色を確認します。"),
        modernCard(diagnosis, "tsunami", "津波浸水想定の公開着色を確認します。"),
        modernCard(
          diagnosis,
          "wetland",
          "明治期の低湿地着色です。現在の状態ではなく土地履歴として読みます。",
        ),
        contextCard({
          id: "groundwater",
          title: "湿潤・地下水の傾向",
          values: [
            { label: "湿潤傾向", value: context?.moisture },
            { label: "地下水モデル", value: context?.groundwaterBand },
            { label: "低湿地履歴", value: context?.wetHistory },
          ],
          explanation:
            "統合正本の補助モデルです。現地ボーリング調査の代わりにはなりません。",
          source: "R3 UNDERLAND context",
        }),
        contextCard({
          id: "current-waterway",
          title: "現在の水路・暗渠",
          values: [{ label: "接続状態", value: currentWater }],
          forceUnknown: text(currentWater) === "OPEN_NOT_MATERIALIZED",
          explanation:
            "龍脈を読むうえで必要な現在水系です。専用形状はまだ地点へ重ねられていません。",
          source: "RYUMYAK current-water geometry（未実装）",
        }),
      ],
    },
    {
      id: "ground",
      title: "地盤",
      intro: "J-SHISの微地形・揺れやすさと、統合正本の補助情報を表示します。",
      items: [
        modernCard(
          diagnosis,
          "ground",
          "防災科研J-SHISの250mメッシュによる微地形・地盤増幅率の参考情報です。",
        ),
        contextCard({
          id: "jshis-context",
          title: "統合正本の地盤文脈",
          values: [
            { label: "参考リスク", value: context?.jshisRisk },
            { label: "微地形の説明", value: context?.jshisDetail },
          ],
          explanation:
            "R3統合時点で保持しているJ-SHIS由来の文脈です。最新照合結果と並べて見ます。",
          source: "R3 / J-SHIS context",
        }),
      ],
    },
    {
      id: "history",
      title: "歴史",
      intro: "重大履歴・死亡事象・伝承・場所索引・地名由来を、事実と文脈に分けます。",
      items: historyItems,
    },
    {
      id: "facilities",
      title: "周辺施設",
      intro: "寺院・墓地・病院を第一段階で確認し、神社と一般病院は参考として分けます。",
      items: [
        ...hardAvoids.slice(0, 3),
        aggregateFact(candidates, resolution, "general_hospital", {
          hardGate: false,
          explanation: "一般病院は第一段階停止条件には入れず、周辺環境の参考として表示します。",
        }),
        aggregateFact(candidates, resolution, "shrine", {
          hardGate: false,
          explanation: "神社は現時点で保留のため、停止条件へ入れず参考距離として表示します。",
        }),
      ],
    },
  ];

  const v15Rank = numberValue(asRecord(primary.profile.layers.V15_3)?.rank);
  const ryRank = numberValue(asRecord(primary.profile.layers.RYUMYAK)?.rank);
  const label =
    resolution.matchedAddress ||
    input.labelHint?.trim() ||
    diagnosis.point.addressHint ||
    primary.profile.cell.address ||
    diagnosis.point.coordinate;

  return {
    schemaVersion: "land-dossier/1.0",
    generatedAt: new Date().toISOString(),
    location: {
      label,
      lat,
      lng,
      coordinate: diagnosis.point.coordinate,
      cellId: primary.cellId,
      cellStability: stabilityLabel(resolution.stability),
      coverageStatus: resolutionCoverageLabel(resolution.coverage.status),
      coverageNote:
        resolution.coverage.note +
        " 候補" +
        candidates.length +
        "区画を同じ規則で確認しました。",
    },
    stageOne: {
      thresholdM: THRESHOLD_M,
      status: stageStatus,
      title:
        stageStatus === "avoid"
          ? "第一段階：避けたい条件に該当"
          : stageStatus === "current_clear"
            ? "第一段階：現時点の確認資料では閾値内なし"
            : "第一段階：資料不足を含むため要確認",
      summary:
        stageStatus === "avoid"
          ? "寺院・墓地・大規模病院・強い歴史・P8のうち、500m以内に確認できた項目があります。後段の点数で相殺しません。"
          : stageStatus === "current_clear"
            ? "接続済み資料の全候補区画で500m以内の該当はありません。ただし資料追加で変わる可能性があります。"
            : "資料網羅性が足りない項目があるため、第一段階を通過したとは断定しません。",
      items: hardAvoids,
    },
    axes: {
      iyashiroji: {
        title: "イヤシロジ（＝テライン仮説）",
        summary:
          "一本目の土地軸です。現行V15.3と比較用V10を並べ、現在の判断と過去基準からの変化を分けて確認します。",
        current: v153,
        legacy: v10,
        comparisonNote:
          "V15.3とV10は版と計算方法が違うため平均しません。V10は過去基準との変化を見るためだけに使います。",
      },
      ryumyak: {
        title: "龍脈",
        summary:
          "二本目の独立軸です。V15.3順位" +
          (v15Rank === null ? "未収録" : v15Rank + "位") +
          "、龍脈順位" +
          (ryRank === null ? "未収録" : ryRank + "位") +
          "を別々に表示します。順位表が異なるため合算しません。",
        current: ryumyak,
      },
    },
    sections,
    missingInformation: missingItems(v10, resolution),
    versionGuide: {
      visible: ["V15.3", "V10"],
      archivedFromNormalView: ["V11", "V12", "V13", "V14"],
      note:
        "イヤシロジの現行はV15.3、V10は比較用です。V11〜V14は削除せず、通常の現行判断と利用者画面から外しています。",
    },
    sources: [
      ...sourceList(primary.profile),
      {
        title: "V10 frozen regional catalog v4",
        project: "V10",
        version: primary.v10.datasetVersion,
        pointer: primary.v10.findings[0]?.sourcePointers[0]?.pointer ?? null,
      },
      ...diagnosis.sources.map((source) => ({
        title: source.name,
        project: source.name,
        version: source.version,
        pointer: source.url,
      })),
    ],
    cautions: [
      "イヤシロジ／龍脈は研究仮説であり、科学的な安全性や効能を保証するものではありません。",
      "資料不足・未走査・未着色は、問題なしや施設不存在へ読み替えていません。",
      "住所・座標の誤差がある場合は複数候補区画を確認し、停止条件を一つの主区画だけで判断していません。",
      "購入・賃貸の最終判断では、自治体の最新資料、現地確認、専門家調査を優先してください。",
    ],
    rawEvidence: {
      resolution,
      integratedProfile: {
        primary: primary.profile,
        candidates: candidates.map((candidate) => ({
          cellId: candidate.cellId,
          weight: candidate.weight,
          profile: candidate.profile,
        })),
      },
      v10: candidates.map((candidate) => ({
        cellId: candidate.cellId,
        weight: candidate.weight,
        layer: candidate.v10,
      })),
      legacyDiagnosis: diagnosis,
    },
  };
}
