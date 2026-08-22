import type { AssessmentDecision, LocationResolution } from "./types";

export function applyResolutionCoverageGate(
  decision: AssessmentDecision,
  resolution: LocationResolution,
): AssessmentDecision {
  if (resolution.coverage.status === "VALIDATED" && resolution.coverage.coveredWeight >= 0.95) {
    return decision;
  }
  const coverageReview = {
    factor: "location_coverage",
    cellId: resolution.primaryCellId,
    distanceM: null,
    thresholdM: 0,
    reason:
      `測位coverageが${resolution.coverage.status}（収容質量${resolution.coverage.coveredWeight}）です。` +
      "未収容・無効セルの可能性を安全扱いしません。",
  };
  const reviews = decision.reviews.some((finding) => finding.factor === "location_coverage")
    ? decision.reviews
    : [...decision.reviews, coverageReview];
  if (resolution.coverage.status === "RUNTIME_UNAVAILABLE") {
    return {
      ...decision,
      status: "review",
      eligible: false,
      hardVeto: false,
      hardGates: [],
      reviews,
      summary: "統合データreleaseを利用できないため判定を停止しました。地理的な対象範囲外とは扱いません。",
    };
  }

  if (decision.status !== "pass") return { ...decision, reviews };
  return {
    ...decision,
    status: "review",
    eligible: true,
    reviews,
    summary: "既知セルの停止条件は確定していませんが、測位coverageが不完全なため要確認です。",
  };
}
