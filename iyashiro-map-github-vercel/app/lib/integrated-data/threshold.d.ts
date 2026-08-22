import type {
  IntegratedDecisionStatus,
  IntegratedThresholdStatus,
} from "./types";

export function classifyIntegratedThreshold(
  distanceM: number | null,
  thresholdM: number | null,
): IntegratedThresholdStatus;

export function classifyIntegratedHardGate(
  distanceM: number | null,
  thresholdM: number | null,
  completeCoverage: boolean,
): Extract<IntegratedDecisionStatus, "fail" | "pass_current_evidence" | "unknown">;
