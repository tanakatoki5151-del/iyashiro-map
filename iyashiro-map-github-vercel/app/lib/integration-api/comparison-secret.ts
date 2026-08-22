import { hkdfSync } from "node:crypto";

type Environment = Record<string, string | undefined>;

function configured(value: string | undefined): string | null {
  const normalized = value?.trim() ?? "";
  return normalized.length >= 32 ? normalized : null;
}

export function comparisonSigningSecret(environment: Environment = process.env): string | null {
  const dedicated = configured(environment.IYASHIRO_COMPARE_SNAPSHOT_SECRET);
  if (dedicated) return dedicated;
  if (environment.VERCEL_ENV !== "preview") return null;

  const automationSecret = configured(environment.VERCEL_AUTOMATION_BYPASS_SECRET);
  const deploymentUrl = environment.VERCEL_URL?.trim() ?? "";
  const projectIdentity = environment.VERCEL_PROJECT_ID?.trim() ||
    environment.VERCEL_PROJECT_PRODUCTION_URL?.trim() ||
    "";
  if (!automationSecret || !deploymentUrl || !projectIdentity) return null;

  const info = [
    "iyashiro/comparison-token/v1",
    projectIdentity,
    deploymentUrl,
  ].join("|");
  const derived = hkdfSync(
    "sha256",
    Buffer.from(automationSecret, "utf8"),
    Buffer.from("iyashiro-preview-signing/v1", "utf8"),
    Buffer.from(info, "utf8"),
    32,
  );
  return Buffer.from(derived).toString("hex");
}
