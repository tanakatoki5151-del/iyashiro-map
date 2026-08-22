import {
  ensureIntegratedReleaseReady,
  IntegratedArtifactMissingError,
  IntegratedReleaseNotReadyError,
  lookupIntegratedCell,
  releaseMetadata,
} from "../integrated-data/runtime";
import { ApiError } from "./errors";
import type { IntegratedCellRecord, IntegratedReleaseMetadata } from "./types";

function unavailable(error: unknown): ApiError | null {
  if (
    error instanceof IntegratedArtifactMissingError ||
    error instanceof IntegratedReleaseNotReadyError
  ) {
    return new ApiError(
      503,
      "integrated_data_unavailable",
      "統合データreleaseが未完了または欠損しています。判定を停止しました。",
      { reason: error.code },
    );
  }
  return null;
}

export async function integratedDataRuntimeAvailable(): Promise<boolean> {
  try {
    await ensureIntegratedReleaseReady();
    return true;
  } catch (error) {
    if (unavailable(error)) return false;
    throw error;
  }
}

export async function lookupIntegratedCellRecord(cellId: string): Promise<IntegratedCellRecord | null> {
  try {
    await ensureIntegratedReleaseReady();
    const record = await lookupIntegratedCell(cellId);
    return (record ?? null) as unknown as IntegratedCellRecord | null;
  } catch (error) {
    throw unavailable(error) ?? error;
  }
}

export function integratedReleaseMetadata(): IntegratedReleaseMetadata {
  return releaseMetadata as unknown as IntegratedReleaseMetadata;
}
