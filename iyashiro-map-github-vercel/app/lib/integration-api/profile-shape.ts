function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
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
  const distances = asRecord(record.distances);
  return {
    V15_3: r3?.v15 ?? null,
    RYUMYAK: r3?.ryumyak ?? null,
    ORBIT: layers?.orbit ?? null,
    R3_PERSONAL_GATE: r3 ?? null,
    HISTORY_P8: distances?.p8 ?? null,
    LEGACY_CONTEXT: r3?.context ?? null,
  };
}
