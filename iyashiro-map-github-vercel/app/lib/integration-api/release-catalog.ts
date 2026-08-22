import { integratedDataRuntimeAvailable, integratedReleaseMetadata } from "./data-adapter";
import { ApiError } from "./errors";
import { evidenceReleaseFromMetadata } from "./release-identity";

export async function buildIntegratedReleaseCatalog() {
  if (!(await integratedDataRuntimeAvailable())) {
    throw new ApiError(
      503,
      "integrated_data_unavailable",
      "統合データreleaseを検証できないためrelease catalogを返しません。",
    );
  }
  const metadata = integratedReleaseMetadata();
  return {
    schemaVersion: "iyashiro-release-catalog/1.0" as const,
    checkedAt: new Date().toISOString(),
    readiness: {
      status: "ready" as const,
      manifestValidated: true,
    },
    current: {
      evidence: evidenceReleaseFromMetadata(metadata),
      generatedAt: typeof metadata.generatedAt === "string" ? metadata.generatedAt : null,
      sourceSchemaVersion: typeof metadata.schemaVersion === "string" ? metadata.schemaVersion : null,
    },
  };
}
