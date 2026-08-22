/**
 * The R3 policy treats a feature at exactly 500 m as within the hard gate.
 * @param {number | null} distanceM
 * @param {number | null} thresholdM
 * @returns {"inside_threshold" | "outside_threshold" | "not_evaluated" | "unknown"}
 */
export function classifyIntegratedThreshold(distanceM, thresholdM) {
  if (distanceM === null || !Number.isFinite(distanceM)) return "unknown";
  if (thresholdM === null || !Number.isFinite(thresholdM)) {
    return "not_evaluated";
  }
  return distanceM <= thresholdM
    ? "inside_threshold"
    : "outside_threshold";
}

/**
 * @param {number | null} distanceM
 * @param {number | null} thresholdM
 * @param {boolean} completeCoverage
 * @returns {"fail" | "pass_current_evidence" | "unknown"}
 */
export function classifyIntegratedHardGate(
  distanceM,
  thresholdM,
  completeCoverage,
) {
  if (
    distanceM === null ||
    thresholdM === null ||
    !Number.isFinite(distanceM) ||
    !Number.isFinite(thresholdM)
  ) return "unknown";
  if (distanceM <= thresholdM) return "fail";
  return completeCoverage ? "pass_current_evidence" : "unknown";
}
