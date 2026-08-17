import "server-only";
import type { LocationLayer } from "./types";
import { UNDERLAND_FORMAL_CELLS, UNDERLAND_RUNTIME_VERSION, readUnderlandRuntime } from "./underland-runtime";

const SOURCE_POINTER = "UNDERLAND_MEGA05_WATER_MOISTURE_CARD_120662_v1";
const SOURCE_REGISTRY = "CURRENT_UNDERLAND_MASTER_v1";

const attentionLabel: Record<string, string> = {
  insufficient: "資料不足",
  historical_water_attention_model_unavailable: "歴史的な水の文脈あり・地下水モデル値なし",
  low: "低め",
  low_to_moderate: "低〜中程度",
  moderate: "中程度",
  elevated: "やや高め",
  high_attention: "重点確認",
  reference_only: "参考情報のみ",
};
const groundwaterLabel: Record<string, string> = {
  unavailable: "モデル値なし",
  upland_5m_model: "台地・丘陵地 5m設定モデル",
  other_materialized_model: "その他の公開モデル区分",
  shallow_model: "浅いモデル区分",
  very_shallow_model: "非常に浅いモデル区分",
  moderately_shallow_model: "やや浅いモデル区分",
  moderate_model: "中程度のモデル区分",
};
const a2Label: Record<string, string> = {
  defined_sources_no_direct_water_signal: "定義済み資料では直接の水シグナルなし",
  wet_context_only: "水・湿地の文脈あり",
  within_family_historical_water_convergence: "同一資料系列内で歴史的水文脈が重なる",
  old_water_geomorph_candidate: "旧水系・地形候補",
  historical_water_landuse_candidate: "歴史的な水系土地利用候補",
};

function publicCoverage(coverageStatus: string) {
  if (coverageStatus === "full_single_class") return "complete_for_defined_sources" as const;
  if (coverageStatus === "outside_jurisdiction_adapter_coverage") return "source_limited" as const;
  return "partial_known_sources" as const;
}

export function buildUnderlandLayer(gridRow: number, gridCol: number): LocationLayer {
  const record = readUnderlandRuntime(gridRow, gridCol);
  if (!record) {
    return {
      layerId: "underland", project: "UNDERLAND", availability: "not_applicable", coverageStatus: "unknown", scoringEffect: "none",
      datasetVersion: UNDERLAND_RUNTIME_VERSION, sourceRegistryVersion: SOURCE_REGISTRY, findings: [],
      warnings: ["This grid position is outside the 120,662-cell UNDERLAND practical runtime universe. No absence or safety inference is allowed."],
      metadata: { formalCellCount: UNDERLAND_FORMAL_CELLS },
    };
  }
  const sourceMaterialized = record.publicEvidenceStatus === "materialized";
  const outsideAdapter = record.coverageStatus === "outside_jurisdiction_adapter_coverage";
  const attention = attentionLabel[record.moistureAttentionClass] ?? record.moistureAttentionClass;
  const groundwater = groundwaterLabel[record.groundwaterRegionalBand] ?? record.groundwaterRegionalBand;
  const waterContext = a2Label[record.historicalWaterContext] ?? record.historicalWaterContext;
  return {
    layerId: "underland", project: "UNDERLAND", availability: outsideAdapter ? "partial" : "available",
    coverageStatus: publicCoverage(record.coverageStatus), scoringEffect: "none", datasetVersion: UNDERLAND_RUNTIME_VERSION,
    sourceRegistryVersion: SOURCE_REGISTRY,
    findings: [{
      findingId: `UNDERLAND-CELL-${gridRow}-${gridCol}`, project: "UNDERLAND", globalFeatureId: null,
      localPointer: `${SOURCE_POINTER}:g${gridRow}-${gridCol}`, title: `UNDERLAND 水・湿気カード: ${attention}`,
      category: "underground_water_moisture_context", status: "context", evidenceMaturity: "context_only",
      geometryRole: "canonical_100m_cell", spatialRelation: "cell_context", distanceMeters: 0, uncertaintyMeters: 100,
      validFrom: null, validTo: null, publicPrecision: "100m_cell", independenceGroup: "UNDERLAND_MEGA05_PUBLIC_RUNTIME",
      canonicalSourceIdentity: `UNDERLAND:${UNDERLAND_RUNTIME_VERSION}:g${gridRow}-${gridCol}`,
      explanation: `水・湿気の確認目安は「${attention}」。地域地下水は「${groundwater}」、歴史水・地形の文脈は「${waterContext}」。これは100mセルの居住確認用contextで、地下水モデル値を敷地直下の実測水位とは扱いません。`,
      sourcePointers: [
        { project: "UNDERLAND", pointer: SOURCE_POINTER, title: "UNDERLAND MEGA-05 water/moisture practical card", version: UNDERLAND_RUNTIME_VERSION },
        { project: "UNDERLAND", pointer: SOURCE_REGISTRY, title: "UNDERLAND CURRENT MASTER", version: "v1" },
      ],
      metadata: {
        moistureAttentionClass: record.moistureAttentionClass, confidence: record.confidence,
        groundwaterRegionalBand: record.groundwaterRegionalBand, historicalWaterContext: record.historicalWaterContext,
        coverageStatus: record.coverageStatus, publicEvidenceStatus: record.publicEvidenceStatus, sourceMaterialized,
      },
    }],
    warnings: [
      "UNDERLANDは地下・水の物理／歴史contextを表示しますが、イヤシロチ・ケガレチ、安全・危険へ直接変換しません。",
      "地域地下水モデルは敷地直下の実測地下水位ではありません。境界・競合セルは追加確認が必要です。",
      ...(sourceMaterialized ? [] : ["このセルの公開Evidenceはremote source pendingを含むため、詳細断定を避けてcontextとして表示します。"]),
    ],
    metadata: { formalCellCount: UNDERLAND_FORMAL_CELLS, practicalRuntime: true, scoringEffect: "none", sourcePointer: SOURCE_POINTER },
  };
}
