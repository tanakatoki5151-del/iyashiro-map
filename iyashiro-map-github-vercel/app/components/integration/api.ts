import type {
  AssessRequest,
  AssessmentView,
  CompareView,
  DecisionStatus,
  GateView,
  LayerView,
  RankingView,
  SavedCandidate,
} from "./types";

type UnknownRecord = Record<string, unknown>;

const layers: Array<{ id: LayerView["id"]; label: string; keys: string[] }> = [
  { id: "r3", label: "R3 統合ゲート", keys: ["r3", "R3", "spiritualGate", "integratedGate", "R3_PERSONAL_GATE"] },
  { id: "v153", label: "V15.3 地形仮説", keys: ["v153", "v15_3", "v15", "terrain", "V15_3"] },
  { id: "ryumyak", label: "RYUMYAK 龍脈", keys: ["ryumyak", "RYUMYAK", "dragonVein"] },
  { id: "orbit", label: "ORBIT 周辺施設", keys: ["orbit", "ORBIT", "facilityDistances", "distances", "ORBIT"] },
  { id: "history", label: "歴史・土地履歴", keys: ["history", "historical", "placeGraph", "veil", "HISTORY_P8", "LEGACY_CONTEXT"] },
  { id: "hcl", label: "HOUSE COMPASS LAB", keys: ["houseCompass", "hcl", "HCL", "houseCompassLab"] },
];

const rankings: Array<{ id: RankingView["id"]; label: string; keys: string[] }> = [
  { id: "sourceFirst", label: "Source-first", keys: ["sourceFirst", "source_first", "SOURCE_FIRST"] },
  { id: "robustness", label: "Robustness", keys: ["robustness", "ROBUSTNESS"] },
  { id: "pureV15", label: "Pure V15.3", keys: ["pureV15", "v15Pure", "pure_v15", "V15_PURE"] },
  { id: "pureRyumyak", label: "Pure RYUMYAK", keys: ["pureRyumyak", "ryumyakPure", "pure_ryumyak", "RYUMYAK_PURE"] },
];

const detailLabels: Record<string, string> = {
  status: "状態",
  verdict: "判定",
  availability: "接続",
  cellId: "100mセル",
  cell_id: "100mセル",
  zone: "ゾーン",
  zoneName: "ゾーン",
  rank: "順位",
  sourceRank: "正本順位",
  distanceM: "距離",
  distance_m: "距離",
  nearestName: "最寄り",
  nearest_name: "最寄り",
  thresholdM: "閾値",
  coverage: "coverage",
  confidence: "確度",
  eligible: "候補",
  overallVerdict: "HCL判定",
  headline: "要旨",
};

const statusAliases: Record<string, DecisionStatus> = {
  hard_veto: "hard_veto",
  hardveto: "hard_veto",
  veto: "hard_veto",
  fail: "hard_veto",
  failed: "hard_veto",
  fail_current_evidence: "hard_veto",
  pass_current_evidence: "pass",
  excluded: "hard_veto",
  "\u898b\u9001\u308b": "hard_veto",
  "\u78ba\u8a8d\u3059\u308b": "review",
  "\u5019\u88dc\u306b\u6b8b\u3059": "pass",
  見送り: "hard_veto",
  除外: "hard_veto",
  review: "review",
  needs_review: "review",
  caution: "review",
  check: "review",
  out_of_scope: "out_of_scope",
  確認: "review",
  要確認: "review",
  保留: "review",
  pass: "pass",
  passed: "pass",
  eligible: "pass",
  candidate: "pass",
  候補: "pass",
  通過: "pass",
  context_only: "review",
  excluded_from_ranking: "unknown",
  unknown: "unknown",
  unknown_no_lens_record: "unknown",
  unavailable: "unknown",
  not_available: "unknown",
  pending: "unknown",
  不明: "unknown",
  未判定: "unknown",
};

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function record(value: unknown): UnknownRecord | undefined {
  return isRecord(value) ? value : undefined;
}

function firstRecord(...values: unknown[]): UnknownRecord | undefined {
  return values.find(isRecord) as UnknownRecord | undefined;
}

function firstValue(source: UnknownRecord | undefined, keys: string[]): unknown {
  if (!source) return undefined;
  for (const key of keys) {
    const value = source[key];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return undefined;
}

function text(value: unknown): string | undefined {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "はい" : "いいえ";
  return undefined;
}

function numberValue(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return undefined;
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    const single = text(value);
    return single ? [single] : [];
  }
  return value.flatMap((item) => {
    if (typeof item === "string" && item.trim()) return [item.trim()];
    if (!isRecord(item)) return [];
    const rendered = text(firstValue(item, ["reason", "message", "label", "title", "detail", "explanation", "name", "url", "uri", "sourceId", "id"]));
    return rendered ? [rendered] : [];
  });
}

function decisionStatus(value: unknown): DecisionStatus {
  const normalized = text(value)?.toLowerCase().replace(/[\s-]+/g, "_");
  return normalized ? statusAliases[normalized] ?? "unknown" : "unknown";
}

function statusLabel(value: DecisionStatus): string {
  if (value === "hard_veto") return "HARD-VETO / 除外";
  if (value === "review") return "要確認";
  if (value === "pass") return "候補に残す";
  if (value === "out_of_scope") return "対象範囲外 / 判定不能";
  return "UNKNOWN / 未判定";
}

function findLayer(root: UnknownRecord, keys: string[]): UnknownRecord | undefined {
  const profile = record(root.profile);
  const envelope = firstRecord(profile?.factEnvelope, profile?.fact_envelope, profile?.facts);
  const factLayers = firstRecord(profile?.layers, envelope?.layers, envelope, root.layers);
  for (const key of keys) {
    const candidates = [root[key], profile?.[key], envelope?.[key], factLayers?.[key]];
    const found = candidates.find(isRecord);
    if (found) return found as UnknownRecord;
    const primitive = candidates.map(text).find((value) => value !== undefined);
    if (primitive !== undefined) return { value: primitive };
  }
  return undefined;
}

function layerAvailability(value: unknown, present: boolean): LayerView["availability"] {
  const normalized = text(value)?.toLowerCase();
  if (normalized === "available" || normalized === "complete" || normalized === "connected") return "available";
  if (normalized === "partial" || normalized === "limited" || normalized === "source_limited") return "partial";
  if (normalized === "unknown" || normalized === "unknown_no_lens_record") return "unknown";
  if (normalized === "unavailable" || normalized === "missing" || normalized === "not_connected") return "unavailable";
  return present ? "available" : "unavailable";
}

const orbitFactIds = new Set([
  "temple",
  "cemetery",
  "large_hospital",
  "shrine",
  "general_hospital",
]);
const historyFactIds = new Set(["strong_history", "p8"]);
const factLabels: Record<string, string> = {
  temple: "\u5bfa",
  cemetery: "\u5893\u5730",
  large_hospital: "\u5927\u75c5\u9662",
  strong_history: "\u5f37\u3044\u6b74\u53f2\u5c65\u6b74",
  p8: "P8\u91cd\u5927\u5c65\u6b74",
  shrine: "\u795e\u793e",
  general_hospital: "\u4e00\u822c\u75c5\u9662",
};

type FactSummary = {
  details: Array<{ label: string; value: string }>;
  warnings: string[];
  evidence: string[];
  status: DecisionStatus;
};

function layerFacts(root: UnknownRecord, layerId: LayerView["id"]): UnknownRecord[] {
  const profile = record(root.profile);
  const facts = Array.isArray(profile?.facts) ? profile.facts.filter(isRecord) : [];
  if (layerId === "orbit") {
    return facts.filter((fact) => orbitFactIds.has(text(fact.factId) ?? ""));
  }
  if (layerId === "history") {
    return facts.filter((fact) => historyFactIds.has(text(fact.factId) ?? ""));
  }
  return [];
}

function summarizeFacts(facts: UnknownRecord[], selectedPolicy: { distanceThresholdM?: number; includeShrines: boolean }): FactSummary {
  const details: Array<{ label: string; value: string }> = [];
  const warnings: string[] = [];
  const evidence: string[] = [];
  let anyTriggered = false;
  let anyUnknown = false;

  for (const fact of facts) {
    const factId = text(fact.factId) ?? "fact";
    const label = factLabels[factId] ?? factId;
    const finding = record(fact.finding);
    const value = record(finding?.value);
    const coverage = record(fact.coverage);
    const findingStatus = text(finding?.status)?.toLowerCase() ?? "unknown";
    const coverageState = text(coverage?.state)?.toLowerCase() ?? "unknown";
    const distance = numberValue(firstValue(value, ["distanceM", "distance_m"]));
    const nearest = text(firstValue(value, ["nearestName", "nearest_name"]));
    const nearestAddress = text(firstValue(value, ["nearestAddress", "nearest_address"]));
    const sourceStatus = text(firstValue(value, ["sourceStatus", "decisionStatus", "thresholdStatus"]));
    const normalizedSourceStatus = sourceStatus?.toLowerCase().replace(/[\s-]+/g, "_");
    const sourceTriggered = value?.triggered === true
      || normalizedSourceStatus === "fail"
      || normalizedSourceStatus === "hard_veto"
      || normalizedSourceStatus === "inside_threshold";
    const policy = record(fact.policy);
    const effect = text(policy?.defaultEffect);
    const effectiveHardGate = effect === "hard_gate" || (factId === "shrine" && selectedPolicy.includeShrines);
    const hardTriggered = effectiveHardGate && distance !== undefined && selectedPolicy.distanceThresholdM !== undefined && distance <= selectedPolicy.distanceThresholdM;
    anyTriggered ||= hardTriggered;
    const incompleteCoverage = [
      "partial",
      "source_limited",
      "not_scanned",
      "unknown",
      "unavailable",
    ].includes(coverageState);
    const unknown = !value
      || incompleteCoverage
      || ["unknown", "review", "not_checked", "unavailable"].includes(findingStatus)
      || normalizedSourceStatus === "unknown"
      || (sourceTriggered && distance === undefined);
    anyUnknown ||= unknown;

    const parts: string[] = [];
    if (distance !== undefined) parts.push(Math.round(distance) + " m");
    if (nearest) parts.push(nearest);
    if (nearestAddress && nearestAddress !== nearest) parts.push(nearestAddress);
    if (effectiveHardGate && distance !== undefined && selectedPolicy.distanceThresholdM !== undefined) {
      parts.push(hardTriggered ? `選択${selectedPolicy.distanceThresholdM}m: HARD-VETO` : `選択${selectedPolicy.distanceThresholdM}m: 閾値外`);
    } else if (sourceTriggered) {
      parts.push("正本既定ゲート該当（選択policyとは別）");
    }
    if (sourceStatus) parts.push(sourceStatus);
    if (!parts.length) parts.push(findingStatus || "UNKNOWN");
    details.push({ label, value: parts.join(" / ") });

    if (unknown) {
      const note = text(coverage?.note);
      warnings.push(label + "\u306fUNKNOWN\u3067\u3059\u3002" + (note ? " " + note : ""));
    }
    if (coverage?.absenceClaimAllowed === false && (unknown || !value)) {
      warnings.push(label + "\u306f\u4e0d\u5b58\u5728\u3084\u5b89\u5168\u3092\u65ad\u5b9a\u3067\u304d\u307e\u305b\u3093\u3002");
    }
    evidence.push(...stringList(fact.sources));
  }

  return {
    details,
    warnings: [...new Set(warnings)],
    evidence: [...new Set(evidence)],
    status: anyTriggered ? "hard_veto" : anyUnknown || !facts.length ? "unknown" : "pass",
  };
}

function displayPrimitive(key: string, value: unknown): string | undefined {
  const shown = text(value);
  if (!shown || shown.length > 180) return undefined;
  if ((key.toLowerCase().includes("distance") || key.toLowerCase().includes("threshold")) && /^\d+(\.\d+)?$/.test(shown)) {
    return shown + " m";
  }
  return shown;
}

function collectDetails(source: UnknownRecord | undefined): Array<{ label: string; value: string }> {
  if (!source) return [];
  const preferredKeys = [
    "status", "verdict", "availability", "cellId", "cell_id", "zone", "zoneName",
    "rank", "sourceRank", "distanceM", "distance_m", "nearestName", "nearest_name",
    "thresholdM", "coverage", "confidence", "eligible", "overallVerdict", "headline",
  ];
  const output: Array<{ label: string; value: string }> = [];
  for (const key of preferredKeys) {
    const shown = displayPrimitive(key, source[key]);
    if (shown && !output.some((item) => item.label === (detailLabels[key] ?? key) && item.value === shown)) {
      output.push({ label: detailLabels[key] ?? key, value: shown });
    }
  }
  if (output.length >= 8) return output.slice(0, 8);
  for (const [key, value] of Object.entries(source)) {
    if (preferredKeys.includes(key) || Array.isArray(value) || isRecord(value)) continue;
    const shown = displayPrimitive(key, value);
    if (shown) output.push({ label: detailLabels[key] ?? key, value: shown });
    if (output.length >= 8) break;
  }
  return output;
}

function normalizeLayer(root: UnknownRecord, definition: (typeof layers)[number]): LayerView {
  const profileLayer = findLayer(root, definition.keys);
  const source = definition.id === "hcl"
    ? firstRecord(root.houseCompass, root.hcl, profileLayer)
    : definition.id === "r3"
      ? firstRecord(profileLayer, root.decision)
      : profileLayer;
  const report = firstRecord(source?.report, source);
  const facts = layerFacts(root, definition.id);
  const appliedPolicy = record(root.policy);
  const factSummary = summarizeFacts(facts, {
    distanceThresholdM: numberValue(appliedPolicy?.distanceThresholdM),
    includeShrines: appliedPolicy?.includeShrines === true,
  });
  const details = [...collectDetails(report), ...factSummary.details].slice(0, 16);
  const hasSubstantiveData = details.length > 0 || facts.length > 0;
  const factCoverageLimited = facts.some((fact) => text(record(fact.coverage)?.state)?.toLowerCase() !== "complete");
  const declaredAvailability = layerAvailability(firstValue(source, ["availability", "coverageStatus"]), hasSubstantiveData);
  const availability = factCoverageLimited && declaredAvailability === "available" ? "partial" : declaredAvailability;
  const statusValue = firstValue(report, ["currentEvidenceDecision", "decisionStatus", "status", "verdict", "overallVerdict", "gateStatus"]);
  const reportedStatus = decisionStatus(statusValue);
  const layerStatus = reportedStatus === "unknown" && facts.length ? factSummary.status : reportedStatus;
  const headline = text(firstValue(report, ["headline", "summary", "label", "explanation", "message"]))
    ?? (hasSubstantiveData ? "APIから事実レイヤーを取得しました。" : "このレイヤーはAPIから提供されていません。");
  return {
    id: definition.id,
    label: definition.label,
    status: layerStatus,
    availability,
    headline,
    details,
    warnings: [
      ...stringList(firstValue(report, ["warnings", "cautions", "missing", "unknowns"])),
      ...stringList(firstValue(source, ["warnings", "cautions", "missing", "unknowns"])),
      ...factSummary.warnings,
    ],
    evidence: [
      ...stringList(firstValue(report, ["evidence", "sources", "sourceRefs", "provenance"])),
      ...factSummary.evidence,
    ],
    raw: source,
  };
}

function findRanking(root: UnknownRecord, keys: string[]): unknown {
  const profile = record(root.profile);
  const r3 = firstRecord(profile?.r3, profile?.R3);
  const containers = [
    record(root.rankings),
    record(root.rankingViews),
    record(profile?.rankings),
    record(profile?.rankingViews),
    record(r3?.rankings),
  ];
  for (const key of keys) {
    if (root[key] !== undefined) return root[key];
    if (profile?.[key] !== undefined) return profile[key];
    for (const container of containers) {
      if (container?.[key] !== undefined) return container[key];
    }
  }
  return undefined;
}

function rankingValue(source: unknown): { value?: string; detail?: string } {
  if (!isRecord(source)) return { value: text(source) };
  const rank = text(firstValue(source, ["sourceRank", "rank", "rankOverall", "position"]));
  const total = text(firstValue(source, ["total", "population", "denominator"]));
  const score = text(firstValue(source, ["value", "score", "index"]));
  const scope = text(firstValue(source, ["scope"]));
  const coverage = text(firstValue(source, ["coverage"]));
  const note = text(firstValue(source, ["note", "explanation"]));
  return {
    value: rank ? (total ? rank + " / " + total : rank + "位") : score,
    detail: [scope, coverage, note].filter((value): value is string => Boolean(value)).join(" / ") || undefined,
  };
}

function normalizeRankings(root: UnknownRecord): RankingView[] {
  return rankings.map((definition) => {
    const found = findRanking(root, definition.keys);
    const shown = rankingValue(found);
    return {
      id: definition.id,
      label: definition.label,
      status: shown.value ? "available" : found === undefined ? "unavailable" : "unknown",
      value: shown.value,
      detail: shown.detail,
    };
  });
}

function hardGate(value: unknown, index: number): GateView | null {
  if (!isRecord(value)) return null;
  const factorId = text(firstValue(value, ["factor", "category", "gateId", "id"]));
  const factor = text(firstValue(value, ["label", "name"])) ?? (factorId ? factLabels[factorId] ?? factorId : "hard gate " + (index + 1));
  return {
    id: (factorId ?? "gate") + "-" + index,
    label: factor,
    status: "hard_veto",
    detail: text(firstValue(value, ["reason", "detail", "explanation", "message"])) ?? "非補償型の除外条件に該当しました。",
    distanceM: numberValue(firstValue(value, ["distanceM", "distance_m", "nearestDistanceM"])),
    thresholdM: numberValue(firstValue(value, ["thresholdM", "threshold_m", "cutoffM"])),
    nearestName: text(firstValue(value, ["nearestName", "nearest_name", "facilityName"])),
  };
}

function reviewGate(value: unknown, index: number): GateView | null {
  const gate = hardGate(value, index);
  return gate ? { ...gate, id: "review-" + gate.id, status: "review" } : null;
}

function resolutionRecord(root: UnknownRecord): UnknownRecord | undefined {
  const resolution = record(root.resolution);
  return firstRecord(
    resolution?.primary,
    resolution?.resolved,
    resolution?.location,
    resolution,
    record(root.profile)?.location,
  );
}

export function normalizeAssessment(payload: unknown, fallbackLabel: string): AssessmentView {
  const root: UnknownRecord = isRecord(payload) ? payload : {};
  const decision = record(root.decision);
  const property = record(root.property);
  const resolution = resolutionRecord(root);
  const profile = record(root.profile);
  const resolutionRoot = record(root.resolution);
  const query = record(resolutionRoot?.query);
  const resolutionCoverage = record(resolutionRoot?.coverage);
  const center = record(record(profile?.cell)?.center);
  const release = record(profile?.release);
  const spatial = firstRecord(
    profile?.spatialContext,
    profile?.cell,
    resolution?.spatialContext,
    record(root.resolution)?.spatialContext,
  );
  const overallStatus = decisionStatus(firstValue(decision, ["status", "verdict", "decisionStatus"]));
  const hardGatesValue = firstValue(decision, ["hardGates", "gates"]);
  const reviewGatesValue = firstValue(decision, ["reviews"]);
  const hardGates = Array.isArray(hardGatesValue)
    ? hardGatesValue.map(hardGate).filter((gate): gate is GateView => Boolean(gate))
    : [];
  const reviewGates = Array.isArray(reviewGatesValue)
    ? reviewGatesValue.map(reviewGate).filter((gate): gate is GateView => Boolean(gate))
    : [];
  const gates = [...hardGates, ...reviewGates];
  const reviews = stringList(firstValue(decision, ["reviews", "warnings", "unknowns"]));
  const hardReasons = gates.map((gate) => gate.detail);
  const lat = numberValue(firstValue(resolution, ["lat", "latitude"]) ?? firstValue(query, ["lat", "latitude"]) ?? firstValue(center, ["lat", "latitude"]));
  const lon = numberValue(firstValue(resolution, ["lon", "lng", "longitude"]) ?? firstValue(query, ["lon", "lng", "longitude"]) ?? firstValue(center, ["lon", "lng", "longitude"]));
  const propertyLabel = text(firstValue(property, ["name", "address"]));
  return {
    assessmentId: text(firstValue(root, ["candidateId", "assessmentId", "id"])),
    generatedAt: text(firstValue(root, ["generatedAt", "timestamp"])),
    status: overallStatus,
    label: text(firstValue(decision, ["summary", "label", "headline"])) ?? statusLabel(overallStatus),
    reasons: [...new Set([...hardReasons, ...reviews])],
    nextActions: stringList(firstValue(decision, ["nextActions", "actions", "next_steps"])),
    warnings: [
      ...reviews,
      ...stringList(firstValue(root, ["warnings", "cautions"])),
      ...stringList(firstValue(record(property?.extraction), ["warnings"])),
    ],
    location: {
      label: propertyLabel ?? text(firstValue(resolution, ["label", "matchedAddress", "address", "query"])) ?? fallbackLabel,
      address: text(firstValue(property, ["address"]) ?? firstValue(resolution, ["matchedAddress", "address"])),
      lat,
      lon,
      cellId: text(firstValue(spatial, ["cellId", "cell_id", "canonicalCellId"]) ?? firstValue(resolution, ["primaryCellId", "cellId", "cell_id"])),
      uncertaintyM: numberValue(firstValue(resolution, ["sigmaM", "uncertaintyM", "uncertaintyMeters", "precisionM"])),
      coverageStatus: text(firstValue(resolutionCoverage, ["status"])),
      coveredWeight: numberValue(firstValue(resolutionCoverage, ["coveredWeight"])),
      coverageNote: text(firstValue(resolutionCoverage, ["note"])),
    },
    gates,
    rankings: normalizeRankings(root),
    layers: layers.map((definition) => normalizeLayer(root, definition)),
    sources: stringList(firstValue(profile, ["sources", "sourceRefs", "provenance", "evidence"]) ?? release?.sources),
    raw: root,
  };
}

function errorMessage(payload: unknown, fallback: string): string {
  return isRecord(payload) ? text(firstValue(payload, ["message", "error", "detail", "reason"])) ?? fallback : fallback;
}

async function readJson(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    const body = await response.text();
    throw new Error(body.trim() || "APIがJSONを返しませんでした（HTTP " + response.status + "）。");
  }
  return response.json() as Promise<unknown>;
}

export async function requestAssessment(request: AssessRequest, signal?: AbortSignal): Promise<AssessmentView> {
  const response = await fetch("/api/v3/assess", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(request),
    signal,
  });
  const payload = await readJson(response);
  if (!response.ok) {
    throw new Error(errorMessage(payload, "統合判定APIを利用できません（HTTP " + response.status + "）。"));
  }
  return normalizeAssessment(payload, request.candidateLabel || request.address || request.manual?.address || "候補地点");
}

export async function requestComparison(candidates: SavedCandidate[], signal?: AbortSignal): Promise<CompareView> {
  const tokens = candidates.map((candidate) => {
    const token = text(candidate.assessment.raw.comparisonToken);
    if (!token) throw new Error("比較用tokenがありません。サーバーの比較署名設定を確認してください。");
    return token;
  });
  const response = await fetch("/api/v3/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      tokens,
      policy: candidates[0]?.request.policy,
    }),
    signal,
  });
  const payload = await readJson(response);
  if (!response.ok) {
    throw new Error(errorMessage(payload, "比較APIを利用できません（HTTP " + response.status + "）。"));
  }
  const root: UnknownRecord = isRecord(payload) ? payload : {};
  const ordering = Array.isArray(root.ordering) ? root.ordering : [];
  const results = Array.isArray(root.results) ? root.results : [];
  const rows = ordering.flatMap((item) => {
    if (!isRecord(item)) return [];
    const clientCandidateId = text(firstValue(item, ["clientCandidateId"]));
    const candidateId = text(firstValue(item, ["candidateId", "id"]));
    const candidateOrdinal = numberValue(firstValue(item, ["candidateOrdinal"]));
    const matching = results.find((candidate) => {
      if (!isRecord(candidate)) return false;
      const resultClientId = text(firstValue(candidate, ["clientCandidateId"]));
      const resultCandidateId = text(firstValue(candidate, ["candidateId", "id"]));
      return clientCandidateId
        ? resultClientId === clientCandidateId
        : candidateId !== undefined && resultCandidateId === candidateId;
    });
    const matchingRecord = record(matching);
    const property = record(matchingRecord?.property);
    const fallback = (clientCandidateId
      ? candidates.find((candidate) => candidate.localId === clientCandidateId)
      : undefined) ?? (candidateOrdinal !== undefined ? candidates[candidateOrdinal] : undefined);
    const tie = item.tie === true;
    const rankingBasis = text(firstValue(item, ["rankingBasis"]));
    const sourceRank = numberValue(firstValue(item, ["sourceRank"]));
    const notes = stringList(firstValue(item, ["reasons", "notes", "warnings"]));
    if (sourceRank === undefined) notes.push("cell-addressableな正本順位がないため順位なし");
    if (tie && sourceRank !== undefined) notes.push("同じ正本順位の候補があります");
    return [{
      id: clientCandidateId ?? candidateId ?? fallback?.localId ?? "candidate-" + (candidateOrdinal ?? 0),
      label: text(firstValue(property, ["name", "address"])) ?? fallback?.label ?? "候補" + ((candidateOrdinal ?? 0) + 1),
      status: decisionStatus(firstValue(item, ["tier", "status"])),
      displayOrder: numberValue(firstValue(item, ["displayOrder"])) ?? (candidateOrdinal !== undefined ? candidateOrdinal + 1 : undefined),
      rank: numberValue(firstValue(item, ["rank"])),
      sourceRank,
      tie,
      rankingBasis,
      notes: [...new Set(notes)],
    }];
  });
  const failureItems = Array.isArray(root.failures) ? root.failures : [];
  const failures = failureItems.flatMap((item, failureIndex) => {
    if (!isRecord(item)) return [];
    const clientCandidateId = text(firstValue(item, ["clientCandidateId"]));
    const candidateOrdinal = numberValue(firstValue(item, ["candidateOrdinal"]));
    const fallback = (clientCandidateId
      ? candidates.find((candidate) => candidate.localId === clientCandidateId)
      : undefined) ?? (candidateOrdinal !== undefined ? candidates[candidateOrdinal] : undefined);
    return [{
      id: "failed-" + (clientCandidateId ?? candidateOrdinal ?? failureIndex),
      label: fallback?.label ?? "候補" + ((candidateOrdinal ?? 0) + 1),
      candidateOrdinal,
      error: text(firstValue(item, ["error", "code"])),
      status: numberValue(item.status),
      message: text(firstValue(item, ["message", "detail", "reason"])) ?? "比較処理に失敗しました。",
    }];
  });
  const requestedCount = numberValue(root.requestedCount);
  const completedCount = numberValue(root.completedCount);
  const failedCount = numberValue(root.failedCount) ?? failures.length;
  const summary = stringList(firstValue(root, ["notes", "summary", "warnings"]));
  if (failedCount > 0) {
    summary.unshift(
      "比較対象" + (requestedCount ?? candidates.length) + "件のうち" +
      (completedCount ?? rows.length) + "件完了、" + failedCount +
      "件失敗。失敗候補は順位表から除外されています。",
    );
  }
  return {
    title: "候補比較",
    summary,
    rows,
    failures,
    raw: root,
  };
}
