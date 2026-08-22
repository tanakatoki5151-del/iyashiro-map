export type CoverageState =
  | "complete"
  | "partial"
  | "source_limited"
  | "not_scanned"
  | "unknown";

export type FactStatus =
  | "confirmed"
  | "review"
  | "context"
  | "excluded"
  | "unknown";

export type PolicyEffect = "hard_gate" | "review" | "context_only" | "off";

export interface ReleasePointer {
  releaseId: string;
  project: string;
  version: string | null;
  publishedAt: string | null;
  sha256: string | null;
  pointer: string | null;
}

export interface SourcePointer {
  project: string;
  title: string;
  version: string | null;
  pointer: string | null;
  sha256: string | null;
  sourceDate: string | null;
}

export interface FactEnvelope<T = unknown> {
  schemaVersion: "fact-envelope/1.0";
  factId: string;
  layer: string;
  subject: { kind: "canonical_cell"; id: string };
  release: ReleasePointer;
  sources: SourcePointer[];
  coverage: {
    state: CoverageState;
    checked: boolean;
    absenceClaimAllowed: boolean;
    note: string;
  };
  finding: {
    status: FactStatus;
    value: T | null;
    uncertaintyMeters: number | null;
  };
  policy: {
    defaultEffect: PolicyEffect;
    aiScoringAllowed: false;
  };
}

export interface IntegratedDistanceFact {
  distanceM: number | null;
  nearestName?: string | null;
  nearestAddress?: string | null;
  status?: string | null;
  coverage?: string | null;
  decisionStatus?: string | null;
  thresholdStatus?: string | null;
  gateRole?: string | null;
  thresholdM?: number | null;
  source?: unknown;
  [key: string]: unknown;
}

export interface IntegratedCellRecord {
  cellId: string;
  gridRow?: number;
  gridCol?: number;
  row?: number;
  col?: number;
  lat?: number;
  lon?: number;
  lng?: number;
  valid?: boolean;
  municipality?: unknown;
  address?: string | null;
  sourceRank?: number | { v15?: number | null; ryumyak?: number | null } | null;
  distances?: Record<string, IntegratedDistanceFact | number | null | undefined>;
  factors?: unknown[];
  facts?: unknown[];
  release?: unknown;
  coverage?: unknown;
  [key: string]: unknown;
}

export interface IntegratedReleaseMetadata {
  releaseId: string;
  generatedAt?: string | null;
  sources?: unknown[];
  coverage?: unknown;
  [key: string]: unknown;
}

export interface WeightedCell {
  cellId: string;
  row: number;
  col: number;
  weight: number;
  centerDistanceM: number;
  valid: boolean;
}

export interface LocationResolution {
  schemaVersion: "canonical-resolution/2.0";
  query: { address: string | null; lat: number; lon: number };
  matchedAddress: string | null;
  geocodeRoute: string;
  sigmaM: number;
  consistency: {
    status: "coordinate_only" | "address_only" | "matched";
    toleranceM: number;
    distanceM: number | null;
    addressPoint: { lat: number; lon: number } | null;
  };
  edgeMarginM: number;
  stability: "STABLE" | "LEANING" | "AMBIGUOUS" | "UNRESOLVED";
  isUniqueCell: boolean;
  primaryCellId: string | null;
  cells: WeightedCell[];
  rejectedTheoreticalCells: string[];
  coverage: {
    status: "VALIDATED" | "PARTIAL" | "NO_VALID_CELL" | "RUNTIME_UNAVAILABLE";
    coveredWeight: number;
    returnedTheoreticalWeight: number;
    rejectedWeight: number;
    omittedWeight: number;
    note: string;
  };
}

export type AssessmentStatus = "pass" | "hard_veto" | "review" | "out_of_scope";

export interface PersonalPolicy {
  id: "R3_DEFAULT";
  distanceThresholdM: 300 | 500 | 650;
  includeShrines: boolean;
  hardGateNonCompensatory: true;
  unknownDisposition: "review";
}

export interface GateFinding {
  factor: string;
  cellId: string | null;
  distanceM: number | null;
  thresholdM: number;
  affectedCellCount?: number;
  evaluatedCellCount?: number;
  affectedWeight?: number;
  reason: string;
}

export interface AssessmentDecision {
  status: AssessmentStatus;
  eligible: boolean;
  hardVeto: boolean;
  hardGates: GateFinding[];
  reviews: GateFinding[];
  summary: string;
}
