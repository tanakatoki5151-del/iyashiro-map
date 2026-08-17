import "server-only";
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
