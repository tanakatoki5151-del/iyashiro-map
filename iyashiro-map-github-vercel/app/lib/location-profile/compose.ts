import type {
  ComposeLocationProfileInput,
  FindingStatus,
  LocationLayer,
  LocationProfileFactSummary,
  LocationProfileV2,
  SourcePointer,
} from "./types";

const REVIEW_STATUSES = new Set<FindingStatus>([
  "source_backed_review",
  "candidate",
]);

function assertFiniteCoordinate(value: number, field: string): void {
  if (!Number.isFinite(value)) {
    throw new TypeError(`${field} must be a finite number`);
  }
}

function validateLayer(layer: LocationLayer): void {
  if (layer.scoringEffect !== "none") {
    throw new Error(
      `LocationProfile Fact layers cannot mutate scores: ${layer.layerId}`,
    );
  }

  const findingIds = new Set<string>();
  for (const finding of layer.findings) {
    if (!finding.findingId) {
      throw new Error(`findingId is required in ${layer.layerId}`);
    }
    if (findingIds.has(finding.findingId)) {
      throw new Error(
        `duplicate findingId in ${layer.layerId}: ${finding.findingId}`,
      );
    }
    findingIds.add(finding.findingId);
  }
}

function summarizeFacts(layers: readonly LocationLayer[]): LocationProfileFactSummary {
  const summary: LocationProfileFactSummary = {
    confirmed: 0,
    review: 0,
    context: 0,
    conflict: 0,
    unknown: 0,
    notScanned: 0,
  };

  for (const layer of layers) {
    if (layer.coverageStatus === "not_scanned") {
      summary.notScanned += 1;
    }

    for (const finding of layer.findings) {
      if (finding.status === "confirmed") summary.confirmed += 1;
      else if (REVIEW_STATUSES.has(finding.status)) summary.review += 1;
      else if (finding.status === "context" || finding.status === "excluded") {
        summary.context += 1;
      } else if (finding.status === "conflict") summary.conflict += 1;
      else if (finding.status === "not_scanned") summary.notScanned += 1;
      else summary.unknown += 1;
    }
  }

  return summary;
}

function sourceKey(source: SourcePointer): string {
  return [source.project, source.pointer, source.version ?? ""].join("::");
}

function deduplicateSources(
  explicitSources: readonly SourcePointer[],
  layers: readonly LocationLayer[],
): SourcePointer[] {
  const output = new Map<string, SourcePointer>();

  for (const source of explicitSources) {
    output.set(sourceKey(source), source);
  }

  for (const layer of layers) {
    for (const finding of layer.findings) {
      for (const source of finding.sourcePointers) {
        output.set(sourceKey(source), source);
      }
    }
  }

  return [...output.values()].sort((a, b) =>
    sourceKey(a).localeCompare(sourceKey(b)),
  );
}

export function composeLocationProfile(
  input: ComposeLocationProfileInput,
): LocationProfileV2 {
  assertFiniteCoordinate(input.queryAnchor.lat, "queryAnchor.lat");
  assertFiniteCoordinate(input.queryAnchor.lng, "queryAnchor.lng");

  if (
    input.spatialContext.cellId &&
    input.queryAnchor.cellId &&
    input.spatialContext.cellId !== input.queryAnchor.cellId
  ) {
    throw new Error(
      `queryAnchor.cellId mismatch: ${input.queryAnchor.cellId} != ${input.spatialContext.cellId}`,
    );
  }

  const byLayer = new Map<LocationLayer["layerId"], LocationLayer>();
  for (const layer of input.layers) {
    validateLayer(layer);
    if (byLayer.has(layer.layerId)) {
      throw new Error(`duplicate LocationProfile layer: ${layer.layerId}`);
    }
    byLayer.set(layer.layerId, layer);
  }

  return {
    schemaVersion: "location-profile/2.0",
    generatedAt: input.generatedAt ?? new Date().toISOString(),
    audience: input.audience,
    location: {
      query: input.query,
      matchedAddress: input.matchedAddress,
      lat: input.queryAnchor.lat,
      lng: input.queryAnchor.lng,
    },
    queryAnchor: input.queryAnchor,
    spatialContext: input.spatialContext,
    legacyRuntime: input.legacyRuntime,
    layers: Object.fromEntries(byLayer),
    coverage: input.coverage,
    factSummary: summarizeFacts(input.layers),
    sources: deduplicateSources(input.sources ?? [], input.layers),
    decisionFactors: [],
    personalRanking: null,
    disclaimer:
      "Fact layers preserve source-owned status, uncertainty and coverage. Unknown or source-limited does not mean safe or absent. Research layers do not directly change the legacy score.",
  };
}
