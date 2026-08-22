import { createHash } from "node:crypto";
import type { IntegratedReleaseMetadata } from "./types";

export const INTEGRATED_DATA_CONTRACT = "integrated-cell-profile/3.0" as const;

export interface EvidenceRelease {
  releaseId: string;
  sha256: string;
  dataContract: typeof INTEGRATED_DATA_CONTRACT;
}

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .filter(([, nested]) => nested !== undefined && typeof nested !== "function")
      .sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0)
      .map(([key, nested]) => [key, canonicalize(nested)]),
  );
}

export function evidenceReleaseFromMetadata(metadata: IntegratedReleaseMetadata): EvidenceRelease {
  const declared = typeof metadata.sha256 === "string" && /^[a-f0-9]{64}$/i.test(metadata.sha256)
    ? metadata.sha256.toLowerCase()
    : null;
  const canonicalMetadata = JSON.stringify(canonicalize(metadata)) ?? "{}";
  const digest = declared ?? createHash("sha256")
    .update(canonicalMetadata)
    .digest("hex");
  return {
    releaseId: metadata.releaseId,
    sha256: digest,
    dataContract: INTEGRATED_DATA_CONTRACT,
  };
}

export function evidenceReleaseMatchesCurrent(
  candidate: unknown,
  current: EvidenceRelease,
): boolean {
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) return false;
  const record = candidate as Record<string, unknown>;
  return record.releaseId === current.releaseId &&
    record.dataContract === current.dataContract &&
    typeof record.sha256 === "string" &&
    record.sha256.toLowerCase() === current.sha256;
}
