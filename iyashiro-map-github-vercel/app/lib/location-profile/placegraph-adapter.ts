import type {
  EvidenceMaturity,
  FindingStatus,
  LocationFinding,
  LocationLayer,
  LocationProfileAudience,
  SourcePointer,
  SpatialRelation,
} from "./types";

export const PLACEGRAPH_DEFAULT_CELL_STATUS =
  "NO_INDEXED_CANDIDATE_SOURCE_LIMITED";

export interface PlaceGraphCellIndexRecord {
  canonicalCellId: string;
  totalLinks: number;
  globalFeatureLinks: number;
  parentSiteComponentLinks: number;
  sourceObservationLinks: number;
  currentAnchorLinks: number;
  referenceContextLinks: number;
  duplicateSuppressionLinks: number;
  openIdentityLinks: number;
  featureQueryableLinks: number;
  nonPositiveLinks: number;
  indexStatus: string;
}

export interface PlaceGraphLinkRecord {
  candidateCellLinkId: string;
  intakeId: string;
  canonicalCellId: string;
  relationType: string | null;
  distanceMeters: number | null;
  intersects: boolean | string | null;
  uncertaintyMeters: number | null;
  boundarySensitive: boolean | string | null;
  externalProject: string;
  finalDisposition: string;
  globalFeatureId: string | null;
  indexLane: string;
  queryStatus: string;
  positiveClaimEligible: string;
  externalLocalId?: string | null;
  sourceRecordClass?: string | null;
  featureClass?: string | null;
  canonicalSourceIdentity?: string | null;
  independenceGroup?: string | null;
  identityDecision?: string | null;
  municipalityId?: string | null;
  municipalityName?: string | null;
  geometryType?: string | null;
  geometryRole?: string | null;
  geometryStage?: string | null;
  locationPrecision?: string | null;
  evidenceStatus?: string | null;
  sourceReadiness?: string | null;
  publicEligible?: boolean | string | null;
  convergenceEligible?: boolean | string | null;
  scoringEffect?: string | null;
  crossProjectImpact?: string | null;
  sourceUrlOrPointer?: string | null;
  sourceTitle?: string | null;
}

export interface PlaceGraphFeatureRecord {
  featureId: string;
  canonicalName: string;
  featureType: string;
  lifecycleStatus: string;
  identityStatus: string;
  sourceProjects: string | null;
  relatedCellIds: string | null;
  parentFeatureId: string | null;
  identityRule: string | null;
}

export interface PlaceGraphGeometryRecord {
  geometryId: string;
  featureId: string;
  geometryRole: string;
  validFrom: string | null;
  validTo: string | null;
  geometryType: string;
  locationLabel: string | null;
  lat: number | null;
  lon: number | null;
  locationPrecision: string | null;
  geometryStatus: string;
  sourceProject: string | null;
  sourcePointer: string | null;
  externalGeometryId: string | null;
  uncertainty: string | number | null;
  targetCellRelation: string | null;
  notes: string | null;
}

export interface PlaceGraphAdapterData {
  buildId: string;
  runId: string;
  defaultCellStatus?: string;
  sourceCoverageCeiling: string;
  sparseCells: Readonly<Record<string, PlaceGraphCellIndexRecord>>;
  linksByCell: Readonly<Record<string, readonly PlaceGraphLinkRecord[]>>;
  featuresById: Readonly<Record<string, PlaceGraphFeatureRecord>>;
  geometriesByFeatureId: Readonly<
    Record<string, readonly PlaceGraphGeometryRecord[]>
  >;
}

export interface BuildPlaceGraphLayerInput {
  audience: LocationProfileAudience;
  cellId: string;
  data: PlaceGraphAdapterData;
}

function normalizeBooleanLike(value: boolean | string | null | undefined): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value !== "string") return false;
  return ["true", "yes", "1"].includes(value.trim().toLowerCase());
}

function mapEvidenceStatus(link: PlaceGraphLinkRecord): FindingStatus {
  const evidence = (link.evidenceStatus ?? "").toLowerCase();
  const identity = (link.identityDecision ?? "").toLowerCase();

  if (identity.includes("conflict")) return "conflict";
  if (evidence === "confirmed" || evidence === "confirmed_positive") {
    return "confirmed";
  }
  if (evidence.includes("review")) return "source_backed_review";
  if (evidence.includes("context") || evidence.includes("crosscheck")) {
    return "context";
  }
  if (link.indexLane === "REFERENCE_CONTEXT") return "context";
  if (link.indexLane === "DUPLICATE_SUPPRESSION") return "excluded";
  if (link.indexLane === "OPEN_IDENTITY") return "candidate";
  return "candidate";
}

function mapMaturity(link: PlaceGraphLinkRecord): EvidenceMaturity {
  const source = [link.geometryStage, link.queryStatus, link.finalDisposition]
    .filter(Boolean)
    .join(" ")
    .toUpperCase();

  for (const maturity of ["S7", "S6", "S5", "S4", "S3", "S2", "S1", "S0"] as const) {
    if (source.includes(maturity)) return maturity;
  }
  if (link.indexLane === "CURRENT_ANCHOR") return "current_only";
  if (
    link.indexLane === "REFERENCE_CONTEXT" ||
    link.indexLane === "SOURCE_OBSERVATION" ||
    link.indexLane === "PARENT_SITE_COMPONENT"
  ) {
    return "context_only";
  }
  return "unknown";
}

function mapSpatialRelation(link: PlaceGraphLinkRecord): SpatialRelation {
  if (normalizeBooleanLike(link.intersects)) return "intersects";

  const relation = (link.relationType ?? "").toLowerCase();
  if (relation.includes("buffer")) return "buffer_intersects";
  if (link.indexLane === "REFERENCE_CONTEXT") return "reference_context";
  if (
    link.indexLane === "PARENT_SITE_COMPONENT" ||
    link.indexLane === "SOURCE_OBSERVATION"
  ) {
    return "area_context";
  }

  if (Number.isFinite(link.distanceMeters)) {
    const distance = link.distanceMeters as number;
    if (distance <= 100) return "within_100m";
    if (distance <= 300) return "within_300m";
    if (distance <= 500) return "within_500m";
  }

  if (link.canonicalCellId) return "cell_context";
  return "unknown";
}

function sourcePointersFor(link: PlaceGraphLinkRecord): SourcePointer[] {
  if (!link.sourceUrlOrPointer) return [];
  return [
    {
      project: link.externalProject,
      pointer: link.sourceUrlOrPointer,
      title: link.sourceTitle ?? null,
    },
  ];
}

function canExposeDetails(
  audience: LocationProfileAudience,
  link: PlaceGraphLinkRecord,
): boolean {
  return audience === "owner" || normalizeBooleanLike(link.publicEligible);
}

function findingKey(link: PlaceGraphLinkRecord): string {
  return (
    link.globalFeatureId ||
    link.independenceGroup ||
    link.canonicalSourceIdentity ||
    link.intakeId
  );
}

function mergeSources(
  first: readonly SourcePointer[],
  second: readonly SourcePointer[],
): SourcePointer[] {
  const merged = new Map<string, SourcePointer>();
  for (const source of [...first, ...second]) {
    const key = [source.project, source.pointer, source.version ?? ""].join("::");
    merged.set(key, source);
  }
  return [...merged.values()];
}

function createFinding(
  link: PlaceGraphLinkRecord,
  data: PlaceGraphAdapterData,
): LocationFinding {
  const feature = link.globalFeatureId
    ? data.featuresById[link.globalFeatureId]
    : undefined;
  const geometries = link.globalFeatureId
    ? data.geometriesByFeatureId[link.globalFeatureId] ?? []
    : [];
  const primaryGeometry = geometries[0];

  return {
    findingId: `placegraph:${findingKey(link)}`,
    project: "PLACEGRAPH",
    globalFeatureId: link.globalFeatureId,
    localPointer: link.externalLocalId ?? link.intakeId,
    title:
      feature?.canonicalName ??
      link.sourceTitle ??
      link.externalLocalId ??
      link.intakeId,
    category: feature?.featureType ?? link.featureClass ?? link.indexLane,
    status: mapEvidenceStatus(link),
    evidenceMaturity: mapMaturity(link),
    geometryRole: primaryGeometry?.geometryRole ?? link.geometryRole ?? null,
    spatialRelation: mapSpatialRelation(link),
    distanceMeters: Number.isFinite(link.distanceMeters)
      ? (link.distanceMeters as number)
      : null,
    uncertaintyMeters: Number.isFinite(link.uncertaintyMeters)
      ? (link.uncertaintyMeters as number)
      : null,
    validFrom: primaryGeometry?.validFrom ?? null,
    validTo: primaryGeometry?.validTo ?? null,
    publicPrecision:
      primaryGeometry?.locationPrecision ?? link.locationPrecision ?? null,
    independenceGroup: link.independenceGroup ?? null,
    canonicalSourceIdentity: link.canonicalSourceIdentity ?? null,
    explanation:
      link.queryStatus === "FEATURE_LINK_QUERYABLE"
        ? "PLACEGRAPH has an indexed relation for this canonical cell. Feature evidence and geometry maturity remain source-owned and time-scoped."
        : "PLACEGRAPH retains this as candidate or context. It is not a confirmed local historical positive.",
    sourcePointers: sourcePointersFor(link),
    metadata: {
      featureIdentityStatus: feature?.identityStatus ?? null,
      featureLifecycleStatus: feature?.lifecycleStatus ?? null,
      parentFeatureId: feature?.parentFeatureId ?? null,
      identityRule: feature?.identityRule ?? null,
      linkDisposition: link.finalDisposition,
      indexLane: link.indexLane,
      positiveClaimEligible: link.positiveClaimEligible,
      sourceReadiness: link.sourceReadiness ?? null,
      geometries,
    },
  };
}

function mergeFinding(
  existing: LocationFinding,
  incoming: LocationFinding,
): LocationFinding {
  const existingDistance = existing.distanceMeters ?? Number.POSITIVE_INFINITY;
  const incomingDistance = incoming.distanceMeters ?? Number.POSITIVE_INFINITY;
  const nearest = incomingDistance < existingDistance ? incoming : existing;

  return {
    ...nearest,
    sourcePointers: mergeSources(
      existing.sourcePointers,
      incoming.sourcePointers,
    ),
    metadata: {
      ...existing.metadata,
      ...incoming.metadata,
      mergedFindingIds: [existing.findingId, incoming.findingId],
    },
  };
}

export function buildPlaceGraphLayer(
  input: BuildPlaceGraphLayerInput,
): LocationLayer {
  const cell = input.data.sparseCells[input.cellId];
  const links = input.data.linksByCell[input.cellId] ?? [];
  const hiddenFindingCount = links.filter(
    (link) => !canExposeDetails(input.audience, link),
  ).length;
  const visibleLinks = links.filter((link) =>
    canExposeDetails(input.audience, link),
  );

  const deduplicated = new Map<string, LocationFinding>();
  for (const link of visibleLinks) {
    const finding = createFinding(link, input.data);
    const key = findingKey(link);
    const existing = deduplicated.get(key);
    deduplicated.set(key, existing ? mergeFinding(existing, finding) : finding);
  }

  const findings = [...deduplicated.values()].sort((a, b) => {
    const distanceA = a.distanceMeters ?? Number.POSITIVE_INFINITY;
    const distanceB = b.distanceMeters ?? Number.POSITIVE_INFINITY;
    return distanceA - distanceB || a.title.localeCompare(b.title, "ja");
  });

  const cellClosureStatus =
    cell?.indexStatus ??
    input.data.defaultCellStatus ??
    PLACEGRAPH_DEFAULT_CELL_STATUS;
  const warnings: string[] = [];

  if (!cell) {
    warnings.push(
      "No indexed PLACEGRAPH relation is currently attached to this cell. Source coverage is partial, so this is not an absence or safety claim.",
    );
  }
  if (hiddenFindingCount > 0) {
    warnings.push(
      `${hiddenFindingCount} finding(s) are withheld by the public-eligibility policy.`,
    );
  }

  return {
    layerId: "placeGraph",
    project: "PLACEGRAPH",
    availability: "partial",
    coverageStatus: "partial_known_sources",
    scoringEffect: "none",
    datasetVersion: input.data.buildId,
    sourceRegistryVersion: input.data.runId,
    findings,
    warnings,
    hiddenFindingCount,
    metadata: {
      canonicalCellId: input.cellId,
      cellClosureStatus,
      sourceCoverageCeiling: input.data.sourceCoverageCeiling,
      absenceClaimAllowed: false,
      cellIndex: cell ?? null,
      rawLinkCount: links.length,
      deduplicatedFindingCount: findings.length,
    },
  };
}
