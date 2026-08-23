export type DossierStatus =
  | "avoid"
  | "review"
  | "current_clear"
  | "available"
  | "context"
  | "unknown";

export type DossierDetail = {
  label: string;
  value: string;
};

export type DossierItem = {
  id: string;
  title: string;
  status: DossierStatus;
  summary: string;
  explanation: string;
  details: DossierDetail[];
  coverage: string;
  source: string;
};

export type DossierSection = {
  id: "terrain" | "water" | "ground" | "history" | "facilities";
  title: string;
  intro: string;
  items: DossierItem[];
};

export type MissingInformation = {
  id: string;
  priority: "high" | "medium" | "low";
  title: string;
  currentState: string;
  nextAction: string;
};

export type LandDossier = {
  schemaVersion: "land-dossier/1.0";
  generatedAt: string;
  location: {
    label: string;
    lat: number;
    lng: number;
    coordinate: string;
    cellId: string;
    cellStability: string;
    coverageStatus: string;
    coverageNote: string;
  };
  stageOne: {
    thresholdM: 500;
    status: "avoid" | "review" | "current_clear";
    title: string;
    summary: string;
    items: DossierItem[];
  };
  axes: {
    iyashiroji: {
      title: "イヤシロジ（＝テライン仮説）";
      summary: string;
      current: DossierItem;
      legacy: DossierItem;
      comparisonNote: string;
    };
    ryumyak: {
      title: "龍脈";
      summary: string;
      current: DossierItem;
    };
  };
  sections: DossierSection[];
  missingInformation: MissingInformation[];
  versionGuide: {
    visible: ["V15.3", "V10"];
    archivedFromNormalView: ["V11", "V12", "V13", "V14"];
    note: string;
  };
  sources: Array<{
    title: string;
    project: string;
    version: string | null;
    pointer: string | null;
  }>;
  cautions: string[];
  rawEvidence?: {
    resolution: unknown;
    integratedProfile: unknown;
    v10: unknown;
    legacyDiagnosis: unknown;
  };
};
