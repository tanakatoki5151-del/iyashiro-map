import { addressEvidenceCanBeRefinedBy, addressEvidenceIsConsistent } from "./address-evidence";
import { createCandidateId } from "./candidate-identity";
import { buildComparisonOrdering } from "./comparison-ordering";
import {
  COMPARISON_TOKEN_TTL_MS,
  comparisonTokenWindowIsValid,
  decodeComparisonToken,
  encodeComparisonToken,
  MAX_COMPARISON_TOKEN_WIRE_BYTES,
} from "./comparison-token";
import { applyResolutionCoverageGate } from "./coverage-gate";
import { comparisonSigningSecret } from "./comparison-secret";
import { integratedDataRuntimeAvailable, integratedReleaseMetadata } from "./data-adapter";
import { assessmentSnapshotMaterial, createSnapshotSignature, snapshotSignatureMatches } from "./snapshot-integrity";
import { ApiError } from "./errors";
import { runHouseCompass, type HouseCompassResponse } from "./hcl-adapter";
import { evaluatePersonalPolicy, parsePersonalPolicy } from "./policy";
import { intakeProperty, type PropertyIntakeResult } from "./property-intake";
import { buildCellProfile, type IntegratedCellProfile } from "./profile";
import {
  evidenceReleaseFromMetadata,
  evidenceReleaseMatchesCurrent,
  INTEGRATED_DATA_CONTRACT,
  type EvidenceRelease,
} from "./release-identity";
import { parseResolveInput, resolveLocation } from "./resolution";
import type { AssessmentDecision, LocationResolution, PersonalPolicy } from "./types";
import { objectValue, optionalString } from "./validation";

export interface AssessmentResponse {
  schemaVersion: "iyashiro-assessment/3.0";
  candidateId: string;
  sourceCandidateId: string | null;
  clientCandidateId: string | null;
  candidateOrdinal: number | null;
  generatedAt: string;
  evidenceRelease: EvidenceRelease;
  property: PropertyIntakeResult;
  resolution: LocationResolution;
  profile: IntegratedCellProfile | null;
  candidateCellProfiles: Array<{
    cellId: string;
    weight: number;
    profile: IntegratedCellProfile | null;
    profileAvailable?: boolean;
  }>;
  policy: PersonalPolicy;
  decision: AssessmentDecision;
  houseCompass: HouseCompassResponse | null;
  comparisonToken: string | null;
  snapshotSignature: string | null;
  disclaimer: string;
}


interface CompactPropertySummary {
  name: string | null;
  address: string | null;
}

interface CompactResolutionSummary {
  primaryCellId: string | null;
  coverage: {
    status: LocationResolution["coverage"]["status"];
    coveredWeight: number;
    note: string;
  };
}

interface ComparisonCandidate extends Omit<AssessmentResponse, "property" | "resolution"> {
  property: PropertyIntakeResult | CompactPropertySummary;
  resolution: LocationResolution | CompactResolutionSummary;
  comparisonSourceRank?: number | null;
}
function candidateId(
  property: PropertyIntakeResult,
  resolution: LocationResolution,
  clientCandidateId: string | null,
  candidateOrdinal: number | null,
): string {
  const identity = JSON.stringify({
    url: property.url,
    address: property.address ?? resolution.matchedAddress ?? resolution.query.address,
    lat: resolution.query.lat,
    lon: resolution.query.lon,
    name: property.name,
    station: property.station,
    areaM2: property.areaM2,
    layout: property.layout,
    memo: property.memo,
    clientCandidateId,
    candidateOrdinal,
  });
  return createCandidateId(identity);
}

function snapshotSecret(): string | null {
  return comparisonSigningSecret();
}

function currentEvidenceRelease(): EvidenceRelease {
  return evidenceReleaseFromMetadata(integratedReleaseMetadata());
}

function assertCurrentEvidenceRelease(value: unknown, source: string): EvidenceRelease {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ApiError(400, "invalid_evidence_release", `${source}のrelease identityが不正です。`);
  }
  const record = value as Record<string, unknown>;
  if (
    typeof record.releaseId !== "string" ||
    typeof record.sha256 !== "string" ||
    record.dataContract !== INTEGRATED_DATA_CONTRACT
  ) {
    throw new ApiError(400, "invalid_evidence_release", `${source}のrelease identityが不正です。`);
  }
  const current = currentEvidenceRelease();
  if (!evidenceReleaseMatchesCurrent(record, current)) {
    throw new ApiError(
      409,
      "stale_evidence_release",
      `${source}は現在の統合データreleaseと一致しないため比較できません。`,
      { currentReleaseId: current.releaseId },
    );
  }
  return current;
}

function comparisonTokenPayload(value: AssessmentResponse): Record<string, unknown> {
  const rankingProfile = value.candidateCellProfiles[0]?.profile ?? null;
  return {
    schemaVersion: "iyashiro-comparison-candidate/1.1",
    candidateId: value.candidateId,
    clientCandidateId: value.clientCandidateId,
    generatedAt: value.generatedAt,
    expiresAt: new Date(Date.parse(value.generatedAt) + COMPARISON_TOKEN_TTL_MS).toISOString(),
    evidenceRelease: value.evidenceRelease,
    property: {
      name: value.property.name,
      address: value.property.address,
    },
    resolution: {
      primaryCellId: value.resolution.primaryCellId,
      coverage: {
        status: value.resolution.coverage.status,
        coveredWeight: value.resolution.coverage.coveredWeight,
        note: value.resolution.coverage.note,
      },
    },
    candidateCells: value.candidateCellProfiles.map((candidate) => ({
      cellId: candidate.cellId,
      weight: candidate.weight,
      profileAvailable: candidate.profileAvailable ?? candidate.profile !== null,
    })),
    policy: value.policy,
    decision: value.decision,
    rankingBasis: {
      id: "source_first_area_rank",
      scope: "area_family",
      rank: rankingProfile?.cell.sourceRank ?? null,
      evidence: rankingProfile?.rankings.sourceFirst.coverage ?? "unknown",
    },
  };
}

function signComparisonToken(value: AssessmentResponse): string | null {
  const secret = snapshotSecret();
  if (!secret) return null;
  try {
    return encodeComparisonToken(comparisonTokenPayload(value), secret);
  } catch (error) {
    if (error instanceof RangeError) {
      throw new ApiError(
        500,
        "comparison_token_too_large",
        "比較用compact tokenを安全な上限内で生成できませんでした。",
      );
    }
    throw error;
  }
}

function signAssessmentSnapshot(value: AssessmentResponse): string | null {
  const secret = snapshotSecret();
  return secret ? createSnapshotSignature(assessmentSnapshotMaterial(value), secret) : null;
}

function assertAssessmentSnapshotIntegrity(value: AssessmentResponse): void {
  const secret = snapshotSecret();
  if (!secret) {
    throw new ApiError(
      503,
      "snapshot_signing_unavailable",
      "比較にはIYASHIRO_COMPARE_SNAPSHOT_SECRETの設定が必要です。",
    );
  }
  if (
    typeof value.snapshotSignature !== "string" ||
    !snapshotSignatureMatches(assessmentSnapshotMaterial(value), secret, value.snapshotSignature)
  ) {
    throw new ApiError(400, "snapshot_signature_invalid", "assessment snapshotの署名が不正です。");
  }
}

export async function assessCandidate(
  value: unknown,
  options: { candidateOrdinal?: number } = {},
): Promise<AssessmentResponse> {
  const body = objectValue(value);
  const clientCandidateId = optionalString(body.clientCandidateId, 120);
  const property = await intakeProperty(body);
  const explicitAddress = optionalString(body.address, 120);
  const manual = body.manual && typeof body.manual === "object" && !Array.isArray(body.manual)
    ? body.manual as Record<string, unknown>
    : null;
  const manualAddress = optionalString(manual?.address, 120);
  const extractedAddress = property.provenance.extracted?.address ?? null;
  if (
    explicitAddress &&
    manualAddress &&
    !addressEvidenceIsConsistent(explicitAddress, manualAddress)
  ) {
    throw new ApiError(
      422,
      "address_evidence_conflict",
      "入力住所と手動住所が一致しないため、候補混同を避けて判定を停止しました。",
      { sources: ["explicit", "manual"] },
    );
  }
  const authoritativeInputAddress = explicitAddress ?? manualAddress;
  if (
    extractedAddress &&
    authoritativeInputAddress &&
    !addressEvidenceCanBeRefinedBy(extractedAddress, authoritativeInputAddress)
  ) {
    throw new ApiError(
      422,
      "address_evidence_conflict",
      "物件ページ住所と指定住所が一致しないため、候補混同を避けて判定を停止しました。",
      { sources: ["property_page", explicitAddress ? "explicit" : "manual"] },
    );
  }
  const address = explicitAddress ?? manualAddress ?? property.address;
  const propertyDerivedAddress = !explicitAddress && !manualAddress &&
    property.source === "url" && property.address !== null;
  const locationInput = parseResolveInput(
    {
      address,
      lat: body.lat,
      lon: body.lon ?? body.lng,
      sigmaM: body.sigmaM,
    },
    propertyDerivedAddress ? "PROPERTY_PAGE_ADDRESS" : "GSI_JUKYO_BASE_NUMBER",
  );
  const resolution = await resolveLocation(locationInput);
  const authoritativeAddress = resolution.matchedAddress ?? address ?? property.address;
  const resolvedProperty = authoritativeAddress === property.address
    ? property
    : {
        ...property,
        address: authoritativeAddress,
        extraction: {
          ...property.extraction,
          warnings: [
            ...property.extraction.warnings,
            "判定・物件・HCLの住所表示をGSI確認済み住所へ統一しました。",
          ],
        },
      };
  const candidateCellProfiles = await Promise.all(
    resolution.cells.map(async (cell) => {
      try {
        return { cellId: cell.cellId, weight: cell.weight, profile: await buildCellProfile(cell.cellId) };
      } catch (error) {
        if (error instanceof ApiError && error.status === 503) throw error;
        return { cellId: cell.cellId, weight: cell.weight, profile: null };
      }
    }),
  );
  const policy = parsePersonalPolicy(body.policy);
  const decision = applyResolutionCoverageGate(
    evaluatePersonalPolicy(candidateCellProfiles, policy),
    resolution,
  );
  const hcl = body.hcl === undefined || body.hcl === null
    ? null
    : runHouseCompass(body.hcl, authoritativeAddress);
  const response: AssessmentResponse = {
    schemaVersion: "iyashiro-assessment/3.0",
    candidateId: candidateId(resolvedProperty, resolution, clientCandidateId, options.candidateOrdinal ?? null),
    sourceCandidateId: null,
    clientCandidateId,
    candidateOrdinal: options.candidateOrdinal ?? null,
    generatedAt: new Date().toISOString(),
    evidenceRelease: currentEvidenceRelease(),
    property: resolvedProperty,
    resolution,
    profile: candidateCellProfiles[0]?.profile ?? null,
    candidateCellProfiles,
    policy,
    decision,
    houseCompass: hcl,
    comparisonToken: null,
    snapshotSignature: null,
    disclaimer:
      "本応答は候補比較用です。UNKNOWNを安全へ変換せず、hard gateは非補償です。科学的効能・資産価値・健康を保証しません。",
  };
  response.comparisonToken = signComparisonToken(response);
  response.snapshotSignature = signAssessmentSnapshot(response);
  return response;
}

function samePolicy(left: PersonalPolicy, right: PersonalPolicy): boolean {
  return left.distanceThresholdM === right.distanceThresholdM &&
    left.includeShrines === right.includeShrines &&
    left.hardGateNonCompensatory === right.hardGateNonCompensatory &&
    left.unknownDisposition === right.unknownDisposition;
}

function comparisonSnapshot(
  value: unknown,
  index: number,
  comparisonPolicy: PersonalPolicy,
): AssessmentResponse {
  const record = objectValue(value, "snapshots[" + index + "]");
  if (record.schemaVersion !== "iyashiro-assessment/3.0") {
    throw new ApiError(400, "invalid_assessment_snapshot", "server-issued v3 assessment snapshotを指定してください。");
  }
  const snapshotPolicy = parsePersonalPolicy(record.policy);
  if (!samePolicy(snapshotPolicy, comparisonPolicy)) {
    throw new ApiError(409, "snapshot_policy_mismatch", "snapshotのpolicyが比較policyと一致しません。");
  }
  if (
    !record.property || typeof record.property !== "object" ||
    !record.resolution || typeof record.resolution !== "object" ||
    !Array.isArray(record.candidateCellProfiles)
  ) {
    throw new ApiError(400, "invalid_assessment_snapshot", "snapshotのproperty/resolution/profile evidenceが不足しています。");
  }
  const snapshot = record as unknown as AssessmentResponse;
  assertAssessmentSnapshotIntegrity(snapshot);
  assertCurrentEvidenceRelease(snapshot.evidenceRelease, "snapshot");
  if (
    !snapshot.resolution.coverage ||
    typeof snapshot.resolution.coverage.coveredWeight !== "number" ||
    !Array.isArray(snapshot.candidateCellProfiles)
  ) {
    throw new ApiError(400, "invalid_assessment_snapshot", "snapshotのcoverage evidenceが不正です。");
  }
  const clientCandidateId = optionalString(record.clientCandidateId, 120);
  const decision = applyResolutionCoverageGate(
    evaluatePersonalPolicy(snapshot.candidateCellProfiles, comparisonPolicy),
    snapshot.resolution,
  );
  return {
    ...snapshot,
    profile: snapshot.candidateCellProfiles[0]?.profile ?? null,
    candidateId: createCandidateId(JSON.stringify({ sourceCandidateId: snapshot.candidateId, index, clientCandidateId })),
    sourceCandidateId: snapshot.candidateId,
    comparisonToken: null,
    snapshotSignature: null,
    clientCandidateId,
    candidateOrdinal: index,
    policy: comparisonPolicy,
    decision,
  };
}

function comparisonTokenAssessment(
  value: unknown,
  index: number,
  comparisonPolicy: PersonalPolicy,
): ComparisonCandidate {
  const secret = snapshotSecret();
  if (!secret) {
    throw new ApiError(503, "snapshot_signing_unavailable", "比較tokenの検証secretが設定されていません。");
  }
  const token = optionalString(value, MAX_COMPARISON_TOKEN_WIRE_BYTES);
  if (!token) throw new ApiError(400, "invalid_comparison_token", "比較tokenが空です。");
  const decoded = decodeComparisonToken(token, secret);
  if (!decoded.ok) {
    throw new ApiError(400, "invalid_comparison_token", `比較tokenを検証できません（${decoded.reason}）。`);
  }
  const record = objectValue(decoded.payload, "comparisonToken");
  if (record.schemaVersion !== "iyashiro-comparison-candidate/1.1") {
    throw new ApiError(400, "invalid_comparison_token", "PII最小化済み比較token 1.1を指定してください。");
  }
  const generatedAt = optionalString(record.generatedAt, 80);
  const expiresAt = optionalString(record.expiresAt, 80);
  const issuedMs = generatedAt ? Date.parse(generatedAt) : Number.NaN;
  const expiresMs = expiresAt ? Date.parse(expiresAt) : Number.NaN;
  if (!comparisonTokenWindowIsValid(issuedMs, expiresMs)) {
    throw new ApiError(400, "comparison_token_expired", "比較tokenの24時間有効期間が不正または期限切れです。");
  }
  const evidenceRelease = assertCurrentEvidenceRelease(
    record.evidenceRelease,
    "comparisonToken",
  );
  const tokenPolicy = parsePersonalPolicy(record.policy);
  if (!samePolicy(tokenPolicy, comparisonPolicy)) {
    throw new ApiError(409, "comparison_token_policy_mismatch", "比較tokenのpolicyが共有policyと一致しません。");
  }

  const property = objectValue(record.property, "comparisonToken.property");
  const propertyName = property.name === null || property.name === undefined
    ? null
    : optionalString(property.name, 200);
  const propertyAddress = property.address === null || property.address === undefined
    ? null
    : optionalString(property.address, 160);
  const resolution = objectValue(record.resolution, "comparisonToken.resolution");
  const coverage = objectValue(resolution.coverage, "comparisonToken.resolution.coverage");
  const primaryCellId = resolution.primaryCellId === null || resolution.primaryCellId === undefined
    ? null
    : optionalString(resolution.primaryCellId, 20);
  const coverageStatus = String(coverage.status);
  const coveredWeight = coverage.coveredWeight;
  const coverageNote = optionalString(coverage.note, 1_000);
  if (
    !["VALIDATED", "PARTIAL", "NO_VALID_CELL", "RUNTIME_UNAVAILABLE"].includes(coverageStatus) ||
    typeof coveredWeight !== "number" ||
    !Number.isFinite(coveredWeight) ||
    coveredWeight < 0 ||
    coveredWeight > 1 ||
    !coverageNote
  ) {
    throw new ApiError(400, "invalid_comparison_token", "比較tokenのcoverage summaryが不正です。");
  }

  const rankingBasis = objectValue(record.rankingBasis, "comparisonToken.rankingBasis");
  const sourceRank = rankingBasis.rank;
  if (
    rankingBasis.id !== "source_first_area_rank" ||
    !(sourceRank === null || (typeof sourceRank === "number" && Number.isFinite(sourceRank) && sourceRank > 0))
  ) {
    throw new ApiError(400, "invalid_comparison_token", "比較tokenのranking basisが不正です。");
  }
  const decision = objectValue(record.decision, "comparisonToken.decision");
  if (
    !["pass", "review", "hard_veto", "out_of_scope"].includes(String(decision.status)) ||
    typeof decision.summary !== "string" ||
    !Array.isArray(decision.hardGates) ||
    !Array.isArray(decision.reviews)
  ) {
    throw new ApiError(400, "invalid_comparison_token", "比較tokenのdecision summaryが不正です。");
  }
  const sourceCandidateId = optionalString(record.candidateId, 120);
  if (!sourceCandidateId || !generatedAt) {
    throw new ApiError(400, "invalid_comparison_token", "比較tokenのmetadataが不足しています。");
  }
  const clientCandidateId = optionalString(record.clientCandidateId, 120);
  if (!Array.isArray(record.candidateCells) || record.candidateCells.length > 25) {
    throw new ApiError(400, "invalid_comparison_token", "比較tokenのcandidate cell summaryが不正です。");
  }
  const seenCellIds = new Set<string>();
  const candidateCellProfiles = record.candidateCells.map((candidate, cellIndex) => {
    const cell = objectValue(candidate, `comparisonToken.candidateCells[${cellIndex}]`);
    const cellId = optionalString(cell.cellId, 20);
    const weight = cell.weight;
    if (
      !cellId ||
      seenCellIds.has(cellId) ||
      typeof weight !== "number" ||
      !Number.isFinite(weight) ||
      weight < 0 ||
      weight > 1 ||
      typeof cell.profileAvailable !== "boolean"
    ) {
      throw new ApiError(400, "invalid_comparison_token", "比較tokenのcell summaryが不正です。");
    }
    seenCellIds.add(cellId);
    return {
      cellId,
      weight,
      profile: null,
      profileAvailable: cell.profileAvailable,
    };
  });

  return {
    schemaVersion: "iyashiro-assessment/3.0",
    candidateId: createCandidateId(JSON.stringify({ sourceCandidateId, index, clientCandidateId })),
    sourceCandidateId,
    clientCandidateId,
    candidateOrdinal: index,
    generatedAt,
    evidenceRelease,
    property: { name: propertyName, address: propertyAddress },
    resolution: {
      primaryCellId,
      coverage: {
        status: coverageStatus as LocationResolution["coverage"]["status"],
        coveredWeight,
        note: coverageNote,
      },
    },
    profile: null,
    candidateCellProfiles,
    policy: comparisonPolicy,
    decision: decision as unknown as AssessmentDecision,
    houseCompass: null,
    comparisonToken: null,
    snapshotSignature: null,
    disclaimer: "署名済み比較要約です。元の物件URL・メモ・HCL入力は含みません。",
    comparisonSourceRank: sourceRank as number | null,
  };
}

function comparisonFailure(value: unknown, index: number, error: unknown) {
  const record = value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
  return {
    candidateOrdinal: index,
    clientCandidateId: typeof record?.clientCandidateId === "string"
      ? record.clientCandidateId.slice(0, 120)
      : null,
    error: error instanceof ApiError ? error.code : "candidate_failed",
    status: error instanceof ApiError ? error.status : 500,
    message: error instanceof ApiError ? error.message : "候補の処理に失敗しました。",
  };
}

export async function compareCandidates(value: unknown) {
  const body = objectValue(value);
  const tokens = Array.isArray(body.tokens) ? body.tokens : null;
  const snapshotCollections = [
    Array.isArray(body.snapshots) ? body.snapshots : null,
    Array.isArray(body.assessments) ? body.assessments : null,
  ].filter((collection): collection is unknown[] => collection !== null);
  const liveInputs = Array.isArray(body.candidates) ? body.candidates : null;
  const collectionCount = (tokens ? 1 : 0) + snapshotCollections.length + (liveInputs ? 1 : 0);
  if (collectionCount !== 1) {
    throw new ApiError(
      400,
      "ambiguous_compare_input",
      "tokens/snapshots/assessments/candidatesはいずれか1種類だけ指定してください。",
    );
  }
  const snapshots = snapshotCollections[0] ?? null;
  const items = tokens ?? snapshots ?? liveInputs!;
  if (items.length < 2 || items.length > 20) {
    throw new ApiError(400, "invalid_candidates", "比較入力は2〜20件で指定してください。");
  }
  if (tokens && new Set(tokens).size !== tokens.length) {
    throw new ApiError(400, "duplicate_comparison_candidate", "同じ比較tokenを重複指定できません。");
  }
  if (snapshots && items.length > 3) {
    throw new ApiError(
      400,
      "full_snapshot_collection_too_large",
      "full assessment snapshotは2〜3件の互換経路です。4〜20件はcompact tokensを使用してください。",
    );
  }
  const mode = tokens
    ? "comparison_tokens" as const
    : snapshots
      ? "assessment_snapshots" as const
      : "live_inputs" as const;
  if (mode === "comparison_tokens" && body.policy === undefined) {
    throw new ApiError(400, "comparison_policy_required", "compact token比較では共有policyを指定してください。");
  }
  const first = mode === "comparison_tokens" ? null : objectValue(items[0], "comparison[0]");
  const comparisonPolicy = parsePersonalPolicy(body.policy ?? first?.policy);
  if ((mode === "comparison_tokens" || mode === "assessment_snapshots") && !snapshotSecret()) {
    throw new ApiError(
      503,
      "snapshot_signing_unavailable",
      "比較にはIYASHIRO_COMPARE_SNAPSHOT_SECRETの設定が必要です。",
    );
  }
  if (mode === "live_inputs" && body.policy === undefined) {
    for (let index = 0; index < items.length; index += 1) {
      const candidate = objectValue(items[index], `candidates[${index}]`);
      if (candidate.policy !== undefined && !samePolicy(parsePersonalPolicy(candidate.policy), comparisonPolicy)) {
        throw new ApiError(400, "mixed_comparison_policy", "比較候補は同一policyで指定してください。");
      }
    }
  }
  if (mode === "live_inputs" && !(await integratedDataRuntimeAvailable())) {
    throw new ApiError(
      503,
      "integrated_data_unavailable",
      "統合データreleaseを検証できないため、live比較を開始しません。",
    );
  }

  const settled: Array<
    { result: ComparisonCandidate; failure: null } |
    { result: null; failure: ReturnType<typeof comparisonFailure> }
  > = new Array(items.length);
  let cursor = 0;
  const concurrency = mode === "live_inputs" ? Math.min(8, items.length) : items.length;
  await Promise.all(
    Array.from({ length: concurrency }, async () => {
      while (cursor < items.length) {
        const index = cursor++;
        try {
          const result = mode === "comparison_tokens"
            ? comparisonTokenAssessment(items[index], index, comparisonPolicy)
            : mode === "assessment_snapshots"
              ? comparisonSnapshot(items[index], index, comparisonPolicy)
              : await assessCandidate(
                  {
                    ...objectValue(items[index], `candidates[${index}]`),
                    policy: comparisonPolicy,
                  },
                  { candidateOrdinal: index },
                );
          settled[index] = { result, failure: null };
        } catch (error) {
          settled[index] = { result: null, failure: comparisonFailure(items[index], index, error) };
        }
      }
    }),
  );

  const assessedResults = settled.flatMap((entry) => entry.result ? [entry.result] : []);
  const failures = settled.flatMap((entry) => entry.failure ? [entry.failure] : []);
  const comparisonConflict = failures.find((failure) => failure.status === 409);
  if (comparisonConflict) {
    throw new ApiError(
      409,
      comparisonConflict.error,
      comparisonConflict.message,
    );
  }
  const seenClientCandidateIds = new Set<string>();
  for (const result of assessedResults) {
    if (!result.clientCandidateId) continue;
    if (seenClientCandidateIds.has(result.clientCandidateId)) {
      throw new ApiError(
        400,
        "duplicate_client_candidate_id",
        "clientCandidateIdは比較内で一意にしてください。",
      );
    }
    seenClientCandidateIds.add(result.clientCandidateId);
  }
  const releaseIds = new Set(assessedResults.map(
    (result) => `${result.evidenceRelease.releaseId}:${result.evidenceRelease.sha256}`,
  ));
  if (releaseIds.size > 1) {
    throw new ApiError(
      409,
      "cross_release_comparison",
      "異なる統合データreleaseの候補は同一順位へ混在できません。",
    );
  }
  const comparisonEvidenceRelease = assessedResults[0]?.evidenceRelease ?? null;
  const ordering = buildComparisonOrdering(assessedResults.map((result) => ({
    candidateId: result.candidateId,
    clientCandidateId: result.clientCandidateId,
    candidateOrdinal: result.candidateOrdinal,
    sourceRank: result.comparisonSourceRank ?? result.profile?.cell.sourceRank ?? null,
    tier: result.decision.status,
    summary: result.decision.summary,
    hardGateCount: result.decision.hardGates.length,
    reviewCount: result.decision.reviews.length,
  })));
  const results = assessedResults.map((assessment) => ({
    schemaVersion: assessment.schemaVersion,
    candidateId: assessment.candidateId,
    sourceCandidateId: assessment.sourceCandidateId,
    clientCandidateId: assessment.clientCandidateId,
    candidateOrdinal: assessment.candidateOrdinal,
    generatedAt: assessment.generatedAt,
    evidenceRelease: assessment.evidenceRelease,
    property: {
      name: assessment.property.name,
      address: assessment.property.address,
    },
    resolution: {
      primaryCellId: assessment.resolution.primaryCellId,
      coverage: assessment.resolution.coverage,
    },
    profile: null,
    policy: assessment.policy,
    decision: assessment.decision,
    houseCompass: null,
    disclaimer: assessment.disclaimer,
    candidateCells: assessment.candidateCellProfiles.map((candidate) => ({
      cellId: candidate.cellId,
      weight: candidate.weight,
      profileAvailable: candidate.profileAvailable ?? candidate.profile !== null,
      profileIncludedInResponse: false,
    })),
  }));

  return {
    schemaVersion: "iyashiro-comparison/3.0" as const,
    generatedAt: new Date().toISOString(),
    mode,
    policy: comparisonPolicy,
    evidenceRelease: comparisonEvidenceRelease,
    requestedCount: items.length,
    completedCount: results.length,
    failedCount: failures.length,
    results,
    failures,
    ordering,
    notes: [
      "入力順を表示順として保持します。cell-addressableなSource-first根拠がない候補へ1位/2位を捏造しません。",
      "comparison_tokensは署名済みcompact evidenceを検証し、外部URLやgeocoderを再取得しません。",
      "比較tokenは署名済みですが暗号化されていません。24時間で失効し、URL・メモ・HCL入力を含めません。ログや第三者共有を避けてください。",
      "比較結果は表示名・住所・判定・順位・cell要約だけを返し、物件URL・メモ・HCL入力を再掲しません。",
      "full snapshotsは2〜3件の互換経路、live_inputsは最大8並列です。候補失敗はfailuresへ隔離します。",
      "hard vetoは非補償、UNKNOWNはreviewです。",
    ],
  };
}
