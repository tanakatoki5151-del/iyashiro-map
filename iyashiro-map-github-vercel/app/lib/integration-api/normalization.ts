export function finiteNumeric(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  if (!normalized) return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

export type OptionalNumericInput =
  | { kind: "missing" }
  | { kind: "invalid"; reason: "type" | "blank" | "format" }
  | { kind: "value"; value: number };

export function classifyOptionalNumericInput(value: unknown): OptionalNumericInput {
  if (value === undefined || value === null || value === "") return { kind: "missing" };
  if (typeof value !== "number" && typeof value !== "string") return { kind: "invalid", reason: "type" };
  if (typeof value === "string" && !value.trim()) return { kind: "invalid", reason: "blank" };
  const parsed = finiteNumeric(value);
  return parsed === null ? { kind: "invalid", reason: "format" } : { kind: "value", value: parsed };
}
