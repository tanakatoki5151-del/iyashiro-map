export type IntegratedGateRole =
  | "hard_veto"
  | "context_only"
  | "excluded_from_ranking";

export type IntegratedDecisionStatus =
  | "fail"
  | "pass_current_evidence"
  | "context_only"
  | "excluded_from_ranking"
  | "unknown";

export type IntegratedThresholdStatus =
  | "inside_threshold"
  | "outside_threshold"
  | "not_evaluated"
  | "unknown";

export type IntegratedDistanceKind =
  | "temple"
  | "cemetery"
  | "largeHospital"
  | "generalHospital"
  | "shrine"
  | "strongHistory"
  | "p8";

export type IntegratedDistanceFact = {
  kind: IntegratedDistanceKind;
  distanceM: number | null;
  nearestFacilityId: string | null;
  name: string | null;
  address: string | null;
  geometryBasis: string | null;
  beds: number | null;
  largeInpatientHospital: boolean | null;
  sourceProject: "PROJECT_ORBIT" | "ALL_PROJECT_INTEGRATED_TOP20_R3";
  sourceVersion: "v2_20260822" | "R3_20260822";
  coverage: string;
  gateRole: IntegratedGateRole;
  thresholdM: number | null;
  thresholdStatus: IntegratedThresholdStatus;
  decisionStatus: IntegratedDecisionStatus;
};

export type IntegratedReleaseSource = {
  project: string;
  version: string;
  sha256?: string;
  pointer?: string;
};

export type IntegratedReleaseMetadata = {
  releaseId: string;
  generatedAt: string;
  schemaVersion: "iyashiro-integrated-data/1.0";
  sources: readonly IntegratedReleaseSource[];
  coverage: {
    totalCells: 120662;
    validCells: 120662;
    integratedCells: 120662;
    r3LensCells: 84060;
    r3PassLensCells: 20118;
    r3NoLensCells: 36602;
    orbitDistanceRows: 482648;
    canonicalFacilities: 31544;
    missingDistances: 0;
    missingFacilityReferences: 0;
    cemetery: string;
    hospital: string;
    shrine: string;
    temple: string;
  };
  policy: {
    unknownIsSafe: false;
    shrine: "context_only";
    generalHospital: "excluded_from_ranking";
  };
};

export type IntegratedR3Rankings = {
  v15PureRank: number | null;
  ryumyakPureRank: number | null;
  sourceFirstAreaRank: null;
  robustnessAreaRank: null;
  areaRankCoverage: "not_cell_addressable_in_r3_release";
};

export type IntegratedR3Layer = {
  project: "ALL_PROJECT_INTEGRATED_TOP20";
  version: "R3_20260822";
  availability: "available" | "unknown_no_lens_record";
  spiritualPass: boolean | null;
  currentEvidenceDecision:
    | "pass_current_evidence"
    | "fail_current_evidence"
    | "unknown";
  core650m: boolean | null;
  failReasons: string[];
  integratedCellScore: number | null;
  lensScore: number | null;
  minimumMarginM: number | null;
  rankings: IntegratedR3Rankings;
  v15: {
    rank: number | null;
    zone: string | null;
    regime: string | null;
  };
  ryumyak: {
    rank: number | null;
    zone: string | null;
    area: string | null;
    confidence: string | null;
    currentWater: string | null;
    hardSplit: string | null;
  };
  context: {
    moisture: string | null;
    groundwaterBand: string | null;
    jshisRisk: number | null;
    jshisDetail: string | null;
    wetHistory: boolean | null;
    p7KnownEras: number | null;
    p7State: string | null;
    eventregFatalities: number | null;
    eventregWithin500m: number | null;
    veilWithin500mCount: number | null;
    veilState: string | null;
    ecoscapeState: string | null;
    ecoscapeTier: string | null;
    placegraphStatus: string | null;
    identityConflicts: number | null;
  };
  sources: {
    v15: string | null;
    ryumyak: string | null;
    orbit: string | null;
    history: string | null;
  };
};

export type IntegratedOrbitLayer = {
  project: "PROJECT_ORBIT";
  version: "v2_20260822";
  availability: "available";
  scoreEffect: "none";
  categoryCount: 4;
  missingDistances: false;
  coverage: {
    cemetery: string;
    hospital: string;
    shrine: string;
    temple: string;
  };
};

export type IntegratedCellRecord = {
  cellId: string;
  gridRow: number;
  gridCol: number;
  lat: number;
  lon: number;
  valid: true;
  municipalityIndex: number | null;
  municipality: string | null;
  town: string | null;
  address: string | null;
  sourceRank: {
    v15: number | null;
    ryumyak: number | null;
  };
  release: IntegratedReleaseMetadata;
  layers: {
    orbit: IntegratedOrbitLayer;
    r3: IntegratedR3Layer;
  };
  distances: {
    temple: IntegratedDistanceFact;
    cemetery: IntegratedDistanceFact;
    largeHospital: IntegratedDistanceFact;
    generalHospital: IntegratedDistanceFact;
    shrine: IntegratedDistanceFact;
    strongHistory: IntegratedDistanceFact;
    p8: IntegratedDistanceFact;
  };
  unknowns: string[];
};
