export interface PolicyObservation {
  distanceM: number | null;
  triggered: boolean | null;
  decisionStatus: string | null;
  thresholdStatus: string | null;
  thresholdM: number | null;
  coverageState: string;
}

export type PolicyObservationResult = "hard_veto" | "review" | "clear";

export function classifyPolicyObservation(
  observation: PolicyObservation,
  selectedThresholdM: number,
): PolicyObservationResult {
  if (observation.distanceM !== null && Number.isFinite(observation.distanceM)) {
    if (observation.distanceM <= selectedThresholdM) return "hard_veto";
    if (observation.coverageState !== "complete" || observation.decisionStatus === "unknown") return "review";
    return "clear";
  }

  const evidenceThreshold = observation.thresholdM;
  const positive =
    observation.triggered === true ||
    observation.decisionStatus === "fail" ||
    observation.thresholdStatus === "inside_threshold";
  const negative =
    observation.triggered === false ||
    observation.decisionStatus === "pass_current_evidence" ||
    observation.thresholdStatus === "outside_threshold";

  if (positive && evidenceThreshold !== null && Number.isFinite(evidenceThreshold)) {
    return selectedThresholdM >= evidenceThreshold ? "hard_veto" : "review";
  }
  if (
    negative &&
    observation.coverageState === "complete" &&
    evidenceThreshold !== null &&
    Number.isFinite(evidenceThreshold)
  ) {
    return selectedThresholdM <= evidenceThreshold ? "clear" : "review";
  }
  return "review";
}

export const BASE_HARD_FACTORS = [
  "temple",
  "cemetery",
  "large_hospital",
  "strong_history",
  "p8",
] as const;

export interface CandidatePolicyObservation {
  cellId: string;
  weight: number;
  observation: PolicyObservation;
}

export interface AggregatedPolicyObservation {
  classification: PolicyObservationResult;
  cellId: string | null;
  distanceM: number | null;
  affectedCellCount: number;
  evaluatedCellCount: number;
  affectedWeight: number;
}

function nearestCandidate(candidates: CandidatePolicyObservation[]): CandidatePolicyObservation | null {
  return [...candidates].sort((left, right) => {
    const leftDistance = left.observation.distanceM;
    const rightDistance = right.observation.distanceM;
    if (leftDistance === null && rightDistance !== null) return 1;
    if (leftDistance !== null && rightDistance === null) return -1;
    if (leftDistance !== null && rightDistance !== null && leftDistance !== rightDistance) {
      return leftDistance - rightDistance;
    }
    return left.cellId.localeCompare(right.cellId);
  })[0] ?? null;
}

export function aggregatePolicyObservations(
  candidates: CandidatePolicyObservation[],
  selectedThresholdM: number,
): AggregatedPolicyObservation {
  const classified = candidates.map((candidate) => ({
    candidate,
    classification: classifyPolicyObservation(candidate.observation, selectedThresholdM),
  }));
  const hard = classified
    .filter((item) => item.classification === "hard_veto")
    .map((item) => item.candidate);
  const review = classified
    .filter((item) => item.classification === "review")
    .map((item) => item.candidate);
  const selected = nearestCandidate(hard.length ? hard : review);
  const affected = hard.length ? hard : review;
  return {
    classification: hard.length ? "hard_veto" : review.length ? "review" : "clear",
    cellId: selected?.cellId ?? null,
    distanceM: selected?.observation.distanceM ?? null,
    affectedCellCount: affected.length,
    evaluatedCellCount: candidates.length,
    affectedWeight: affected.reduce(
      (sum, candidate) => sum + (Number.isFinite(candidate.weight) && candidate.weight > 0 ? candidate.weight : 0),
      0,
    ),
  };
}
export function activeHardFactors(includeShrines: boolean): string[] {
  return includeShrines ? [...BASE_HARD_FACTORS, "shrine"] : [...BASE_HARD_FACTORS];
}
