export type LocationProfileAudience = "public" | "owner";

export type LayerId =
  | "placeGraph"
  | "veil"
  | "underland"
  | "limen"
  | "v10Legacy"
  | "v11Terrain"
  | "landHistory"
  | "burial"
  | "facilities"
  | "ecoscape"
  | "kaso";

export type LayerAvailability =
  | "available"
  | "partial"
  | "not_available"
  | "not_applicable"
  | "error";

export type CoverageStatus =
  | "complete_for_defined_sources"
  | "partial_known_sources"
  | "source_limited"
  | "not_scanned"
  | "unknown";

export type FindingStatus =
  | "confirmed"
  | "source_backed_review"
  | "candidate"
  | "context"
  | "conflict"
  | "excluded"
  | "unknown"
  | "not_scanned";

export type SpatialRelation =
  | "intersects"
  | "buffer_intersects"
  | "within_100m"
  | "within_300m"
  | "within_500m"
  | "cell_context"
  | "area_context"
  | "reference_context"
  | "unknown";

export type EvidenceMaturity =
  | "S0"
  | "S1"
  | "S2"
  | "S3"
  | "S4"
  | "S5"
  | "S6"
  | "S7"
  | "current_only"
  | "context_only"
  | "unknown";

export interface QueryAnchor {
  anchorId: string;
  anchorType:
    | "verified_building"
    | "verified_parcel"
    | "representative_point"
    | "address_point"
    | "map_click"
    | "current_location";
  lat: number;
  lng: number;
  precisionClass: string;
  uncertaintyMeters: number | null;
  source: string;
  sourceDate: string;
  acquiredAt: string;
  matchedAddress?: string | null;
  cellId?: string | null;
}

export interface SpatialContext {
  supported: boolean;
  cellId: string | null;
  gridRow: number | null;
  gridCol: number | null;
  municipalityId: string | null;
  municipalityCode: string | null;
  municipalityName: string | null;
  cellCenter?: { lat: number; lng: number } | null;
  candidateCellIdsByRadius?: Readonly<Record<"100" | "300" | "500", readonly string[]>>;
  spatialCoreVersion?: string | null;
  spatialCoreSha?: string | null;
}

export interface SourcePointer {
  project: string;
  pointer: string;
  title?: string | null;
  version?: string | null;
  sourceDate?: string | null;
}

export interface LocationFinding {
  findingId: string;
  project: string;
  globalFeatureId: string | null;
  localPointer: string | null;
  title: string;
  category: string;
  status: FindingStatus;
  evidenceMaturity: EvidenceMaturity;
  geometryRole: string | null;
  spatialRelation: SpatialRelation;
  distanceMeters: number | null;
  uncertaintyMeters: number | null;
  validFrom: string | null;
  validTo: string | null;
  publicPrecision: string | null;
  independenceGroup: string | null;
  canonicalSourceIdentity: string | null;
  explanation: string;
  sourcePointers: readonly SourcePointer[];
  metadata?: Readonly<Record<string, unknown>>;
}

export interface LocationLayer {
  layerId: LayerId;
  project: string;
  availability: LayerAvailability;
  coverageStatus: CoverageStatus;
  scoringEffect: "none";
  datasetVersion: string | null;
  sourceRegistryVersion?: string | null;
  findings: readonly LocationFinding[];
  warnings: readonly string[];
  hiddenFindingCount?: number;
  metadata?: Readonly<Record<string, unknown>>;
}

export interface LocationProfileCoverage {
  cellClosureStatus: string;
  sourceCoverageCeiling: string;
  absenceClaimAllowed: boolean;
  lastUpdatedAt: string;
  refreshPolicy: string;
  notes: readonly string[];
}

export interface LocationProfileFactSummary {
  confirmed: number;
  review: number;
  context: number;
  conflict: number;
  unknown: number;
  notScanned: number;
}

export interface LocationProfileV2 {
  schemaVersion: "location-profile/2.0";
  generatedAt: string;
  audience: LocationProfileAudience;
  location: {
    query: string | null;
    matchedAddress: string | null;
    lat: number;
    lng: number;
  };
  queryAnchor: QueryAnchor;
  spatialContext: SpatialContext;
  legacyRuntime: Readonly<Record<string, unknown>>;
  layers: Partial<Record<LayerId, LocationLayer>>;
  coverage: LocationProfileCoverage;
  factSummary: LocationProfileFactSummary;
  sources: readonly SourcePointer[];
  decisionFactors: readonly unknown[];
  personalRanking: null;
  disclaimer: string;
}

export interface ComposeLocationProfileInput {
  audience: LocationProfileAudience;
  query: string | null;
  matchedAddress: string | null;
  queryAnchor: QueryAnchor;
  spatialContext: SpatialContext;
  legacyRuntime: Readonly<Record<string, unknown>>;
  layers: readonly LocationLayer[];
  coverage: LocationProfileCoverage;
  sources?: readonly SourcePointer[];
  generatedAt?: string;
}
