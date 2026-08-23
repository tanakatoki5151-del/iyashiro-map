function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function isMeaningfulAxisValue(value: unknown): boolean {
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value === "string") return value.trim().length > 0;
  return typeof value === "boolean";
}

function hasMeaningfulAxisData(
  value: unknown,
  fields: readonly string[],
): boolean {
  const record = asRecord(value);
  return record !== null && fields.some((field) =>
    isMeaningfulAxisValue(record[field]),
  );
}

export function hasMeaningfulV153Data(value: unknown): boolean {
  return hasMeaningfulAxisData(value, ["rank", "zone", "regime"]);
}

export function hasMeaningfulRyumyakData(value: unknown): boolean {
  return hasMeaningfulAxisData(value, [
    "rank",
    "zone",
    "area",
    "confidence",
    "currentWater",
    "hardSplit",
  ]);
}

export interface MaterializedProfileLayers {
  V15_3: unknown;
  RYUMYAK: unknown;
  ORBIT: unknown;
  R3_PERSONAL_GATE: unknown;
  HISTORY_P8: unknown;
  LEGACY_CONTEXT: unknown;
}

export function materializeProfileLayers(record: { layers?: unknown; distances?: unknown }): MaterializedProfileLayers {
  const layers = asRecord(record.layers);
  const r3 = asRecord(layers?.r3);
  const hasR3LensRecord = r3?.availability === "available";
  const v153 = r3?.v15 ?? null;
  const ryumyak = r3?.ryumyak ?? null;
  const distances = asRecord(record.distances);
  return {
    V15_3:
      hasR3LensRecord && hasMeaningfulV153Data(v153) ? v153 : null,
    RYUMYAK:
      hasR3LensRecord && hasMeaningfulRyumyakData(ryumyak) ? ryumyak : null,
    ORBIT: layers?.orbit ?? null,
    R3_PERSONAL_GATE: r3 ?? null,
    HISTORY_P8: distances?.p8 ?? null,
    LEGACY_CONTEXT: hasR3LensRecord ? r3?.context ?? null : null,
  };
}
