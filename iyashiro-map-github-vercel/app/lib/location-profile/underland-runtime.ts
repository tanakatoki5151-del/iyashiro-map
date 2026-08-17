import "server-only";
import { gunzipSync } from "node:zlib";
import c0 from "./underland-runtime-chunk-0";
import c1 from "./underland-runtime-chunk-1";
import c2 from "./underland-runtime-chunk-2";
import c3 from "./underland-runtime-chunk-3";
import c4 from "./underland-runtime-chunk-4";
import c5 from "./underland-runtime-chunk-5";
import c6 from "./underland-runtime-chunk-6";

const ENCODED_GZIP = c0 + c1 + c2 + c3 + c4 + c5 + c6;

export const UNDERLAND_RUNTIME_VERSION = "UNDERLAND_MEGA05_WATER_MOISTURE_CARD_120662_v1";
export const UNDERLAND_FORMAL_CELLS = 120662;
export const UNDERLAND_GRID_WIDTH = 462;

export const underlandAttention = ["insufficient","historical_water_attention_model_unavailable","low","moderate","elevated","high_attention","reference_only","low_to_moderate"] as const;
export const underlandConfidence = ["reference", "practical"] as const;
export const underlandCoverage = ["outside_jurisdiction_adapter_coverage","full_single_class","boundary_sensitive_or_partial_coverage","overlap_center_resolved_by_official_fixed_rule__cell_mixed_or_boundary_sensitive","source_overlap_conflict_interpolated_classes"] as const;
export const underlandGroundwaterBand = ["unavailable","upland_5m_model","other_materialized_model","shallow_model","very_shallow_model","moderately_shallow_model","moderate_model"] as const;
export const underlandA2State = ["defined_sources_no_direct_water_signal","wet_context_only","within_family_historical_water_convergence","old_water_geomorph_candidate","historical_water_landuse_candidate"] as const;
export const underlandPublicEvidence = ["materialized", "remote_public_source_pending"] as const;

export type UnderlandRuntimeRecord = {
  gridIndex: number;
  moistureAttentionClass: (typeof underlandAttention)[number];
  confidence: (typeof underlandConfidence)[number];
  coverageStatus: (typeof underlandCoverage)[number];
  groundwaterRegionalBand: (typeof underlandGroundwaterBand)[number];
  historicalWaterContext: (typeof underlandA2State)[number];
  publicEvidenceStatus: (typeof underlandPublicEvidence)[number];
};

let decoded: Buffer | null = null;
function runtimeBuffer(): Buffer {
  if (!decoded) decoded = gunzipSync(Buffer.from(ENCODED_GZIP, "base64"));
  return decoded;
}

export function readUnderlandRuntime(gridRow: number, gridCol: number): UnderlandRuntimeRecord | null {
  if (!Number.isInteger(gridRow) || !Number.isInteger(gridCol) || gridRow < 0 || gridCol < 0) return null;
  const gridIndex = gridRow * UNDERLAND_GRID_WIDTH + gridCol;
  const offset = gridIndex * 2;
  const buffer = runtimeBuffer();
  if (offset + 1 >= buffer.length) return null;
  const stored = buffer.readUInt16LE(offset);
  if (stored === 0) return null;
  let code = stored - 1;
  const publicEvidenceIndex = code % underlandPublicEvidence.length; code = Math.floor(code / underlandPublicEvidence.length);
  const a2Index = code % underlandA2State.length; code = Math.floor(code / underlandA2State.length);
  const groundwaterIndex = code % underlandGroundwaterBand.length; code = Math.floor(code / underlandGroundwaterBand.length);
  const coverageIndex = code % underlandCoverage.length; code = Math.floor(code / underlandCoverage.length);
  const confidenceIndex = code % underlandConfidence.length; code = Math.floor(code / underlandConfidence.length);
  const attentionIndex = code;
  const moistureAttentionClass = underlandAttention[attentionIndex];
  const confidence = underlandConfidence[confidenceIndex];
  const coverageStatus = underlandCoverage[coverageIndex];
  const groundwaterRegionalBand = underlandGroundwaterBand[groundwaterIndex];
  const historicalWaterContext = underlandA2State[a2Index];
  const publicEvidenceStatus = underlandPublicEvidence[publicEvidenceIndex];
  if (!moistureAttentionClass || !confidence || !coverageStatus || !groundwaterRegionalBand || !historicalWaterContext || !publicEvidenceStatus) return null;
  return { gridIndex, moistureAttentionClass, confidence, coverageStatus, groundwaterRegionalBand, historicalWaterContext, publicEvidenceStatus };
}
