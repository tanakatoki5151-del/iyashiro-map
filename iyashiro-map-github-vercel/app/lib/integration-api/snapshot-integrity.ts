import { createHmac, timingSafeEqual } from "node:crypto";

export function createSnapshotSignature(payload: unknown, secret: string): string {
  return createHmac("sha256", secret).update(JSON.stringify(payload)).digest("hex");
}

export function snapshotSignatureMatches(
  payload: unknown,
  secret: string,
  signature: string,
): boolean {
  if (!/^[a-f0-9]{64}$/i.test(signature)) return false;
  const expected = Buffer.from(createSnapshotSignature(payload, secret), "hex");
  const received = Buffer.from(signature, "hex");
  return received.length === expected.length && timingSafeEqual(received, expected);
}
export function assessmentSnapshotMaterial(value: unknown): Record<string, unknown> {
  const record = value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
  return {
    schemaVersion: record.schemaVersion,
    candidateId: record.candidateId,
    sourceCandidateId: record.sourceCandidateId,
    clientCandidateId: record.clientCandidateId,
    candidateOrdinal: record.candidateOrdinal,
    generatedAt: record.generatedAt,
    evidenceRelease: record.evidenceRelease,
    property: record.property,
    resolution: record.resolution,
    profile: record.profile,
    candidateCellProfiles: record.candidateCellProfiles,
    policy: record.policy,
    decision: record.decision,
    houseCompass: record.houseCompass,
    comparisonToken: record.comparisonToken,
    disclaimer: record.disclaimer,
  };
}
