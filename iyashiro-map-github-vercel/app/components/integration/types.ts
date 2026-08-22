export type DecisionStatus = "hard_veto" | "review" | "pass" | "out_of_scope" | "unknown";
export type DistanceThreshold = 300 | 500 | 650;

export type ManualPropertyInput = {
  name: string;
  address: string;
  station: string;
  areaM2: string;
  layout: string;
  monthlyCostYen: string;
  memo: string;
};

export type HclInput = {
  enabled: boolean;
  entranceDirection: string;
  bedroomDirection: string;
  workDeskDirection: string;
  kitchenDirection: string;
  headDirection: string;
  buildingAgeBand: string;
  concerns: string;
};

export type AssessmentFormState = {
  candidateLabel: string;
  address: string;
  latitude: string;
  longitude: string;
  propertyUrl: string;
  manual: ManualPropertyInput;
  policy: {
    distanceThresholdM: DistanceThreshold;
    includeShrines: boolean;
  };
  hcl: HclInput;
};

export type AssessRequest = {
  clientCandidateId?: string;
  candidateLabel?: string;
  address?: string;
  lat?: number;
  lon?: number;
  propertyUrl?: string;
  manual?: {
    name?: string;
    address?: string;
    station?: string;
    areaM2?: string;
    layout?: string;
    monthlyCostYen?: string;
    memo?: string;
  };
  policy: {
    distanceThresholdM: DistanceThreshold;
    includeShrines: boolean;
  };
  hcl?: Omit<HclInput, "enabled">;
};

export type GateView = {
  id: string;
  label: string;
  status: DecisionStatus;
  detail: string;
  distanceM?: number;
  thresholdM?: number;
  nearestName?: string;
};

export type RankingView = {
  id: "sourceFirst" | "robustness" | "pureV15" | "pureRyumyak";
  label: string;
  status: "available" | "unknown" | "unavailable";
  value?: string;
  detail?: string;
};

export type LayerView = {
  id: "r3" | "v153" | "ryumyak" | "orbit" | "history" | "hcl";
  label: string;
  status: DecisionStatus;
  availability: "available" | "partial" | "unavailable" | "unknown";
  headline: string;
  details: Array<{ label: string; value: string }>;
  warnings: string[];
  evidence: string[];
  raw?: Record<string, unknown>;
};

export type AssessmentView = {
  assessmentId?: string;
  generatedAt?: string;
  status: DecisionStatus;
  label: string;
  reasons: string[];
  nextActions: string[];
  warnings: string[];
  location: {
    label: string;
    address?: string;
    lat?: number;
    lon?: number;
    cellId?: string;
    uncertaintyM?: number;
    coverageStatus?: string;
    coveredWeight?: number;
    coverageNote?: string;
  };
  gates: GateView[];
  rankings: RankingView[];
  layers: LayerView[];
  sources: string[];
  raw: Record<string, unknown>;
};

export type SavedCandidate = {
  localId: string;
  savedAt: string;
  label: string;
  request: AssessRequest;
  assessment: AssessmentView;
};

export type CompareView = {
  title: string;
  summary: string[];
  rows: Array<{
    id: string;
    label: string;
    status: DecisionStatus;
    displayOrder?: number;
    rank?: number;
    sourceRank?: number;
    tie: boolean;
    rankingBasis?: string;
    notes: string[];
  }>;
  failures: Array<{
    id: string;
    label: string;
    candidateOrdinal?: number;
    error?: string;
    status?: number;
    message: string;
  }>;
  raw: Record<string, unknown>;
};

export const emptyAssessmentForm: AssessmentFormState = {
  candidateLabel: "",
  address: "",
  latitude: "",
  longitude: "",
  propertyUrl: "",
  manual: {
    name: "",
    address: "",
    station: "",
    areaM2: "",
    layout: "",
    monthlyCostYen: "",
    memo: "",
  },
  policy: {
    distanceThresholdM: 500,
    includeShrines: false,
  },
  hcl: {
    enabled: false,
    entranceDirection: "",
    bedroomDirection: "",
    workDeskDirection: "",
    kitchenDirection: "",
    headDirection: "",
    buildingAgeBand: "",
    concerns: "",
  },
};
