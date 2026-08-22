import type { IntegratedCellProfile } from "./profile";
import {
  activeHardFactors,
  aggregatePolicyObservations,
  type CandidatePolicyObservation,
} from "./policy-evaluation";
import type { AssessmentDecision, GateFinding, PersonalPolicy } from "./types";
import { ApiError } from "./errors";
import { objectValue, optionalFiniteNumber } from "./validation";

export function parsePersonalPolicy(value: unknown): PersonalPolicy {
  const record = value === undefined || value === null ? {} : objectValue(value, "policy");
  const requestedThreshold = optionalFiniteNumber(
    record.distanceThresholdM,
    { minimum: 300, maximum: 650 },
  ) ?? 500;
  const distanceThresholdM = ([300, 500, 650] as const).find((item) => item === requestedThreshold);
  if (!distanceThresholdM) {
    throw new ApiError(400, "invalid_policy", "distanceThresholdM は 300 / 500 / 650 のいずれかです。");
  }
  if (record.includeShrines !== undefined && typeof record.includeShrines !== "boolean") {
    throw new ApiError(400, "invalid_policy", "includeShrines はbooleanで指定してください。");
  }
  return {
    id: "R3_DEFAULT",
    distanceThresholdM,
    includeShrines: record.includeShrines ?? false,
    hardGateNonCompensatory: true,
    unknownDisposition: "review",
  };
}

function observation(profile: IntegratedCellProfile, factor: string) {
  const fact = profile.facts.find((candidate) => candidate.factId === factor);
  const value = fact?.finding.value;
  return {
    distanceM: value?.distanceM ?? null,
    triggered: value?.triggered ?? null,
    decisionStatus: value?.decisionStatus ?? null,
    thresholdStatus: value?.thresholdStatus ?? null,
    thresholdM: value?.thresholdM ?? null,
    coverageState: fact?.coverage.state ?? "unknown",
  };
}

function label(factor: string): string {
  return ({
    temple: "寺院",
    cemetery: "墓地",
    large_hospital: "大規模入院病院",
    strong_history: "強い歴史履歴",
    p8: "P8履歴",
    shrine: "神社",
  } as Record<string, string>)[factor] ?? factor;
}

export function evaluatePersonalPolicy(
  cells: Array<{ cellId: string; weight?: number; profile: IntegratedCellProfile | null }>,
  policy: PersonalPolicy,
): AssessmentDecision {
  if (!cells.length) {
    return {
      status: "out_of_scope",
      eligible: false,
      hardVeto: false,
      hardGates: [],
      reviews: [{
        factor: "canonical_cell",
        cellId: null,
        distanceM: null,
        thresholdM: policy.distanceThresholdM,
        reason: "canonical valid-cellを確定できませんでした。",
        affectedCellCount: 0,
        evaluatedCellCount: 0,
        affectedWeight: 0,
      }],
      summary: "対象範囲内の有効セルを確定できないため判定しません。",
    };
  }

  const factors = activeHardFactors(policy.includeShrines);
  const hardGates: GateFinding[] = [];
  const reviews: GateFinding[] = [];
  const missingProfiles = cells.filter((cell) => !cell.profile);
  if (missingProfiles.length) {
    reviews.push({
      factor: "cell_profile",
      cellId: missingProfiles[0].cellId,
      distanceM: null,
      thresholdM: policy.distanceThresholdM,
      reason: `候補セル${missingProfiles.length}件の正本profileを取得できません。UNKNOWNとして要確認です。`,
      affectedCellCount: missingProfiles.length,
      evaluatedCellCount: cells.length,
      affectedWeight: missingProfiles.reduce(
        (sum, cell) => sum + (Number.isFinite(cell.weight) && (cell.weight ?? 0) > 0 ? cell.weight! : 0),
        0,
      ),
    });
  }

  for (const factor of factors) {
    const candidates: CandidatePolicyObservation[] = cells.flatMap((cell) => cell.profile
      ? [{
          cellId: cell.cellId,
          weight: cell.weight ?? 0,
          observation: observation(cell.profile, factor),
        }]
      : []);
    const aggregate = aggregatePolicyObservations(candidates, policy.distanceThresholdM);
    if (aggregate.classification === "hard_veto") {
      hardGates.push({
        factor,
        cellId: aggregate.cellId,
        distanceM: aggregate.distanceM,
        thresholdM: policy.distanceThresholdM,
        reason:
          `${label(factor)}が候補セル${aggregate.evaluatedCellCount}件中${aggregate.affectedCellCount}件で停止条件${policy.distanceThresholdM}m以内です。`,
        affectedCellCount: aggregate.affectedCellCount,
        evaluatedCellCount: aggregate.evaluatedCellCount,
        affectedWeight: aggregate.affectedWeight,
      });
    } else if (aggregate.classification === "review") {
      reviews.push({
        factor,
        cellId: aggregate.cellId,
        distanceM: aggregate.distanceM,
        thresholdM: policy.distanceThresholdM,
        reason:
          `${label(factor)}は候補セル${aggregate.evaluatedCellCount}件中${aggregate.affectedCellCount}件でcoverageまたはゲート状態がUNKNOWNです。`,
        affectedCellCount: aggregate.affectedCellCount,
        evaluatedCellCount: aggregate.evaluatedCellCount,
        affectedWeight: aggregate.affectedWeight,
      });
    }
  }

  if (hardGates.length) {
    return {
      status: "hard_veto",
      eligible: false,
      hardVeto: true,
      hardGates,
      reviews,
      summary: "不確実性候補セルのいずれかが非補償型停止条件に該当しました。他の好材料で相殺しません。",
    };
  }
  if (reviews.length) {
    return {
      status: "review",
      eligible: true,
      hardVeto: false,
      hardGates: [],
      reviews,
      summary: "停止条件の確定該当はありませんが、候補セル群にUNKNOWNが残るため要確認です。",
    };
  }
  return {
    status: "pass",
    eligible: true,
    hardVeto: false,
    hardGates: [],
    reviews: [],
    summary: "全不確実性候補セルで選択policyの停止条件は明示的に閾値外です。安全保証ではありません。",
  };
}
