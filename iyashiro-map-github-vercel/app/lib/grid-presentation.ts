export const GRID_REVIEW_LABEL = "資料不足・要確認" as const;

export type GridAssessment = {
  score: number | null;
  provisional: boolean;
  status: "available" | "unknown";
  label: string;
};

type GridAssessmentInput = {
  score: number;
  provisional: boolean;
  label: string;
};

export function toGridAssessment(
  input: GridAssessmentInput,
): GridAssessment {
  if (input.provisional || !Number.isFinite(input.score)) {
    return {
      score: null,
      provisional: true,
      status: "unknown",
      label: GRID_REVIEW_LABEL,
    };
  }
  return {
    score: input.score,
    provisional: false,
    status: "available",
    label: input.label,
  };
}

export function gridAssessmentNeedsReview(
  value: Pick<GridAssessment, "score" | "provisional" | "status">,
) {
  return (
    value.status === "unknown" ||
    value.provisional ||
    value.score === null ||
    !Number.isFinite(value.score)
  );
}
