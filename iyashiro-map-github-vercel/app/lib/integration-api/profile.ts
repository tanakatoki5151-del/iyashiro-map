import { integratedReleaseMetadata, lookupIntegratedCellRecord } from "./data-adapter";
import { ApiError } from "./errors";
import { cellCenter, parseCellId } from "./grid";
import { finiteNumeric } from "./normalization";
import { materializeProfileLayers } from "./profile-shape";
import type {
  CoverageState,
  FactEnvelope,
  FactStatus,
  IntegratedCellRecord,
  PolicyEffect,
  ReleasePointer,
  SourcePointer,
} from "./types";

type NormalizedDistanceValue = {
  distanceM: number | null;
  triggered: boolean | null;
  nearestName: string | null;
  nearestAddress: string | null;
  sourceStatus: string | null;
  decisionStatus: string | null;
  thresholdStatus: string | null;
  coverage: string | null;
  gateRole: string | null;
  thresholdM: number | null;
};

type FactorDefinition = {
  id: string;
  layer: string;
  aliases: string[];
  defaultEffect: PolicyEffect;
};

const FACTORS: FactorDefinition[] = [
  { id: "temple", layer: "ORBIT", aliases: ["temple", "temples", "tera"], defaultEffect: "hard_gate" },
  { id: "cemetery", layer: "ORBIT", aliases: ["cemetery", "cemeteries", "graveyard", "graveyards"], defaultEffect: "hard_gate" },
  { id: "large_hospital", layer: "R3_PERSONAL_GATE", aliases: ["largeHospital", "large_hospital", "largeInpatientHospital"], defaultEffect: "hard_gate" },
  { id: "strong_history", layer: "R3_PERSONAL_GATE", aliases: ["strongHistory", "strong_history", "historicalStrong", "massDeath"], defaultEffect: "hard_gate" },
  { id: "p8", layer: "HISTORY_P8", aliases: ["p8", "p8Gate", "p8_gate"], defaultEffect: "hard_gate" },
  { id: "shrine", layer: "ORBIT", aliases: ["shrine", "shrines", "jinja"], defaultEffect: "off" },
  { id: "general_hospital", layer: "ORBIT", aliases: ["generalHospital", "general_hospital", "hospital"], defaultEffect: "off" },
];

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function normalizedKey(value: string): string {
  return value.replace(/[^a-z0-9]/gi, "").toLowerCase();
}

function booleanValue(value: unknown): boolean | null {
  if (typeof value === "boolean") return value;
  if (typeof value !== "string") return null;
  const normalized = value.trim().toLowerCase();
  if (["true", "yes", "1", "hit", "fail", "hard_veto", "blocked"].includes(normalized)) return true;
  if (["false", "no", "0", "pass", "clear"].includes(normalized)) return false;
  return null;
}

function findAliasedValue(root: unknown, aliases: string[]): unknown {
  const wanted = new Set(aliases.map(normalizedKey));
  const queue: Array<{ value: unknown; depth: number }> = [{ value: root, depth: 0 }];
  let visited = 0;
  while (queue.length && visited < 1_000) {
    const current = queue.shift()!;
    visited += 1;
    const record = asRecord(current.value);
    if (!record) continue;
    for (const [key, value] of Object.entries(record)) {
      if (wanted.has(normalizedKey(key))) return value;
      if (current.depth < 4 && value && typeof value === "object") {
        queue.push({ value, depth: current.depth + 1 });
      }
    }
  }
  return undefined;
}

function coverageIsSourceLimited(value: string | null): boolean {
  if (!value) return true;
  return /(unknown|partial|open|request|required|limited|incomplete|not[_ -]?scanned)/i.test(value);
}

function distanceFromValue(value: unknown): NormalizedDistanceValue {
  if (typeof value === "number") {
    return {
      distanceM: Number.isFinite(value) ? value : null,
      triggered: null,
      nearestName: null,
      nearestAddress: null,
      sourceStatus: null,
      decisionStatus: null,
      thresholdStatus: null,
      coverage: null,
      gateRole: null,
      thresholdM: null,
    };
  }
  const record = asRecord(value);
  if (!record) {
    return {
      distanceM: null,
      triggered: null,
      nearestName: null,
      nearestAddress: null,
      sourceStatus: null,
      decisionStatus: null,
      thresholdStatus: null,
      coverage: null,
      gateRole: null,
      thresholdM: null,
    };
  }
  const distanceKeys = [
    "distanceM",
    "distance_m",
    "nearestDistanceM",
    "nearest_distance_m",
    "minimumDistanceM",
    "min_distance_m",
  ];
  const triggerKeys = ["triggered", "hardGate", "hard_gate", "within500m", "within_500m", "hit", "veto"];
  const decisionStatus = typeof record.decisionStatus === "string" ? record.decisionStatus : null;
  const thresholdStatus = typeof record.thresholdStatus === "string" ? record.thresholdStatus : null;
  const coverage = typeof record.coverage === "string" ? record.coverage : null;
  const gateRole = typeof record.gateRole === "string" ? record.gateRole : null;
  const status = typeof record.status === "string"
    ? record.status
    : typeof record.gateStatus === "string"
      ? record.gateStatus
      : decisionStatus;
  let distanceM: number | null = null;
  for (const key of distanceKeys) {
    if (key in record) {
      distanceM = finiteNumeric(record[key]);
      if (distanceM !== null) break;
    }
  }
  let triggered: boolean | null = null;
  for (const key of triggerKeys) {
    if (key in record) {
      triggered = booleanValue(record[key]);
      if (triggered !== null) break;
    }
  }
  triggered ??= booleanValue(status);
  if (triggered === null) {
    if (decisionStatus === "fail" || thresholdStatus === "inside_threshold") {
      triggered = true;
    } else if (
      !coverageIsSourceLimited(coverage) &&
      (decisionStatus === "pass_current_evidence" || thresholdStatus === "outside_threshold")
    ) {
      triggered = false;
    }
  }
  return {
    distanceM,
    triggered,
    nearestName: typeof record.nearestName === "string"
      ? record.nearestName
      : typeof record.nearest_name === "string"
        ? record.nearest_name
        : typeof record.name === "string"
          ? record.name
          : null,
    nearestAddress: typeof record.nearestAddress === "string"
      ? record.nearestAddress
      : typeof record.nearest_address === "string"
        ? record.nearest_address
        : typeof record.address === "string"
          ? record.address
          : null,
    sourceStatus: status,
    decisionStatus,
    thresholdStatus,
    coverage,
    gateRole,
    thresholdM: finiteNumeric(record.thresholdM ?? record.threshold_m),
  };
}

function coverageStateFromValue(value: NormalizedDistanceValue, checked: boolean): CoverageState {
  if (!checked) return "unknown";
  if (value.decisionStatus === "unknown" || coverageIsSourceLimited(value.coverage)) return "source_limited";
  if (
    value.decisionStatus === "pass_current_evidence" ||
    value.decisionStatus === "fail" ||
    value.thresholdStatus === "inside_threshold" ||
    value.thresholdStatus === "outside_threshold" ||
    /complete|current[_ -]?evidence/i.test(value.coverage ?? "")
  ) return "complete";
  return "source_limited";
}

function releasePointer(layer: string): ReleasePointer {
  const metadata = integratedReleaseMetadata();
  return {
    releaseId: metadata.releaseId,
    project: layer,
    version: typeof metadata.version === "string" ? metadata.version : null,
    publishedAt: typeof metadata.generatedAt === "string" ? metadata.generatedAt : null,
    sha256: typeof metadata.sha256 === "string" ? metadata.sha256 : null,
    pointer: typeof metadata.pointer === "string" ? metadata.pointer : null,
  };
}

function sourcePointers(): SourcePointer[] {
  const metadata = integratedReleaseMetadata();
  if (!Array.isArray(metadata.sources)) return [];
  return metadata.sources.flatMap((source) => {
    const record = asRecord(source);
    if (!record) return [];
    const project = typeof record.project === "string" ? record.project : "INTEGRATED_DATA";
    return [{
      project,
      title: typeof record.title === "string" ? record.title : project,
      version: typeof record.version === "string" ? record.version : null,
      pointer: typeof record.pointer === "string" ? record.pointer : null,
      sha256: typeof record.sha256 === "string" ? record.sha256 : null,
      sourceDate: typeof record.sourceDate === "string" ? record.sourceDate : null,
    }];
  });
}

function envelopeForFactor(cellId: string, record: IntegratedCellRecord, definition: FactorDefinition): FactEnvelope<NormalizedDistanceValue> {
  const raw = findAliasedValue(record.distances ?? record, definition.aliases);
  const value = distanceFromValue(raw);
  const checked = value.distanceM !== null || value.triggered !== null || value.decisionStatus !== null;
  const coverageState = coverageStateFromValue(value, checked);
  const findingStatus: FactStatus = coverageState === "complete" ? "confirmed" : checked ? "review" : "unknown";
  return {
    schemaVersion: "fact-envelope/1.0",
    factId: definition.id,
    layer: definition.layer,
    subject: { kind: "canonical_cell", id: cellId },
    release: releasePointer(definition.layer),
    sources: sourcePointers(),
    coverage: {
      state: coverageState,
      checked,
      absenceClaimAllowed: false,
      note: coverageState === "complete"
        ? "正本runtimeの明示値です。地点座標ではなくcanonical cell中心基準の距離を含む場合があります。"
        : checked
          ? "距離値はありますが、coverageまたはdecisionStatusが限定的です。閾値外でも安全・不存在として確定しません。"
          : "未収録・未走査・不明を区別できないためUNKNOWNです。安全または不存在を意味しません。",
    },
    finding: {
      status: findingStatus,
      value: checked ? value : null,
      uncertaintyMeters: null,
    },
    policy: {
      defaultEffect: definition.defaultEffect,
      aiScoringAllowed: false,
    },
  };
}


export interface RankingView {
  rank: number | null;
  scope: "canonical_cell" | "area_family";
  coverage: "complete" | "unknown";
  note: string;
}

function rankingView(
  record: IntegratedCellRecord,
  aliases: string[],
  scope: RankingView["scope"],
  missingNote: string,
): RankingView {
  const rank = finiteNumeric(findAliasedValue(record, aliases));
  return {
    rank,
    scope,
    coverage: rank === null ? "unknown" : "complete",
    note: rank === null
      ? missingNote
      : scope === "canonical_cell"
        ? "canonical cellに明示された正本順位です。"
        : "Area Family成果物に明示された順位です。cellへの推測配賦はしていません。",
  };
}

export interface IntegratedCellProfile {
  schemaVersion: "integrated-cell-profile/3.0";
  generatedAt: string;
  cell: {
    cellId: string;
    row: number;
    col: number;
    center: { lat: number; lon: number };
    municipality: unknown;
    address: string | null;
    sourceRank: number | null;
  };
  release: ReturnType<typeof integratedReleaseMetadata>;
  coverage: {
    validCell: true;
    absenceClaimAllowed: false;
    note: string;
  };
  layers: {
    V15_3: unknown;
    RYUMYAK: unknown;
    ORBIT: unknown;
    R3_PERSONAL_GATE: unknown;
    HISTORY_P8: unknown;
    LEGACY_CONTEXT: unknown;
  };
  rankings: {
    sourceFirst: RankingView;
    robustness: RankingView;
    v15Pure: RankingView;
    ryumyakPure: RankingView;
  };
  facts: FactEnvelope<NormalizedDistanceValue>[];
}

export async function buildCellProfile(cellId: string): Promise<IntegratedCellProfile> {
  const parsed = parseCellId(cellId);
  if (!parsed) throw new ApiError(400, "invalid_cell_id", "cellId は g{row}-{col} 形式で指定してください。");
  const record = await lookupIntegratedCellRecord(cellId);
  if (!record || record.valid !== true) {
    throw new ApiError(404, "cell_not_found", "canonical valid-cell台帳に一致しません。");
  }
  const center = cellCenter(parsed.row, parsed.col);
  const layers = materializeProfileLayers(record);
  const rankings = {
    sourceFirst: rankingView(
      record,
      ["sourceFirstAreaRank", "source_first_area_rank"],
      "area_family",
      "Source-firstはArea Family順位で、全cellへのmembership対応がないためUNKNOWNです。",
    ),
    robustness: rankingView(
      record,
      ["robustnessAreaRank", "robustness_area_rank"],
      "area_family",
      "RobustnessはArea Family順位で、全cellへのmembership対応がないためUNKNOWNです。",
    ),
    v15Pure: rankingView(
      record,
      ["v15PureRank", "v15", "V15 Rank"],
      "canonical_cell",
      "このcellにV15 pure順位が明示されていません。",
    ),
    ryumyakPure: rankingView(
      record,
      ["ryumyakPureRank", "ryumyak", "RY Rank"],
      "canonical_cell",
      "このcellにRYUMYAK pure順位が明示されていません。",
    ),
  };
  return {
    schemaVersion: "integrated-cell-profile/3.0",
    generatedAt: new Date().toISOString(),
    cell: {
      cellId,
      row: parsed.row,
      col: parsed.col,
      center,
      municipality: record.municipality ?? null,
      address: typeof record.address === "string" ? record.address : null,
      sourceRank: rankings.sourceFirst.rank,
    },
    release: integratedReleaseMetadata(),
    coverage: {
      validCell: true,
      absenceClaimAllowed: false,
      note: "UNKNOWN・未走査・source-limitedは安全または不存在へ変換しません。",
    },
    layers,
    rankings,
    facts: FACTORS.map((definition) => envelopeForFactor(cellId, record, definition)),
  };
}
