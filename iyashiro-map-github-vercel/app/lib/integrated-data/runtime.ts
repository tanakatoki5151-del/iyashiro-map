import path from "node:path";
import { RowPromiseLruCache } from "./row-cache.mjs";

import type {
  IntegratedCellRecord,
  IntegratedDecisionStatus,
  IntegratedDistanceFact,
  IntegratedDistanceKind,
  IntegratedGateRole,
  IntegratedReleaseMetadata,
  IntegratedThresholdStatus,
} from "./types";

export type { IntegratedCellRecord, IntegratedReleaseMetadata } from "./types";

type RawDistanceTuple = [
  distanceM: number,
  nearestFacilityId: string,
  nearestName: string | null,
  nearestAddress: string | null,
  geometryBasis: string | null,
  beds: number | null,
  largeInpatientHospital: boolean | null,
  primaryCategory: string | null,
];

type RawR3Tuple = Array<unknown>;

type RawCellTuple = [
  cellId: string,
  gridColumn: number,
  latitude: number,
  longitude: number,
  municipalityIndex: number | null,
  temple: RawDistanceTuple,
  shrine: RawDistanceTuple,
  cemetery: RawDistanceTuple,
  hospital: RawDistanceTuple,
  r3: RawR3Tuple | null,
];

type RawRowShard = {
  schemaVersion: "iyashiro-integrated-data/1.0";
  releaseId: string;
  gridRow: number;
  cells: RawCellTuple[];
};

type RawArtifactDeclaration = {
  path?: unknown;
  bytes?: unknown;
  sha256?: unknown;
};

type RawReleaseManifest = {
  schemaVersion?: unknown;
  releaseId?: unknown;
  sources?: Array<{
    project?: unknown;
    version?: unknown;
    sha256?: unknown;
    pointer?: unknown;
  }>;
  coverage?: {
    validCells?: unknown;
    integratedCells?: unknown;
    r3LensCells?: unknown;
    r3PassLensCells?: unknown;
    orbitDistanceRows?: unknown;
    canonicalFacilities?: unknown;
  };
  qa?: {
    status?: unknown;
    allGridRowsMaterialized?: unknown;
    publicR3SourcePointersRedacted?: unknown;
    publicR3SourcePointerValuesRedacted?: unknown;
  };
  outputs?: {
    rowShardCount?: unknown;
    facilityShardCount?: unknown;
    rowShards?: RawArtifactDeclaration[];
    facilityShards?: RawArtifactDeclaration[];
  };
};

type ArtifactIntegrity = {
  bytes: number;
  sha256: string;
};

type ReadyRelease = {
  rowShardArtifacts: ReadonlyMap<string, ArtifactIntegrity>;
};

export class IntegratedArtifactMissingError extends Error {
  readonly code = "INTEGRATED_ARTIFACT_MISSING";
  readonly artifactPath: string;

  constructor(artifactPath: string) {
    super("Integrated data artifact is missing: " + artifactPath);
    this.name = "IntegratedArtifactMissingError";
    this.artifactPath = artifactPath;
  }
}

export class IntegratedReleaseNotReadyError extends Error {
  readonly code = "INTEGRATED_RELEASE_NOT_READY";

  constructor(message: string) {
    super(message);
    this.name = "IntegratedReleaseNotReadyError";
  }
}

const R3 = {
  municipality: 2,
  town: 3,
  v15Rank: 6,
  v15Zone: 7,
  v15Regime: 8,
  ryRank: 9,
  ryZone: 10,
  ryArea: 11,
  ryConfidence: 12,
  ryCurrentWater: 13,
  ryHardSplit: 14,
  spiritualPass: 15,
  core650m: 16,
  failReasons: 17,
  integratedCellScore: 18,
  lensScore: 19,
  minimumMarginM: 20,
  largeHospitalM: 23,
  largeHospitalName: 24,
  beds: 25,
  strongHistoryEffectiveM: 26,
  strongHistoryName: 29,
  strongHistoryCategory: 30,
  p8MinM: 31,
  p8Within500: 32,
  moisture: 33,
  groundwaterBand: 34,
  jshisRisk: 35,
  jshisDetail: 36,
  wetHistory: 37,
  p7KnownEras: 38,
  p7State: 39,
  eventregFatalities: 40,
  eventregWithin500m: 41,
  veilWithin500mCount: 42,
  veilState: 43,
  ecoscapeState: 44,
  ecoscapeTier: 45,
  placegraphStatus: 46,
  identityConflicts: 47,
  sourceV15: 48,
  sourceRy: 49,
  sourceOrbit: 50,
  sourceHistory: 51,
} as const;

const CEMETERY_COVERAGE =
  "UNKNOWN_REQUEST_REQUIRED_FOR_FULL_PERMIT_LEDGER";
const HOSPITAL_COVERAGE =
  "PUBLIC_PRIMARY_SOURCE_COMPLETE_TECHNICAL_QA";
const RELIGION_COVERAGE =
  "OSM_SNAPSHOT_COMPLETE_OFFICIAL_SITE_LINKAGE_PARTIAL";

export const INTEGRATED_RELEASE_METADATA = {
  releaseId: "iyashiro-r3-orbit-v2-20260823",
  generatedAt: "2026-08-23",
  schemaVersion: "iyashiro-integrated-data/1.0",
  sources: [
    {
      project: "ALL_PROJECT_INTEGRATED_TOP20",
      version: "R3_20260822",
      sha256:
        "1fe4e9506336932755f5a27306bfeb93082d365ad29a1356dd7bfe0cbc48547b",
    },
    {
      project: "PROJECT_ORBIT",
      version: "v2_20260822",
      sha256:
        "439865368ae08aedc1f934075e5432c8c2b3651c9cf7dbe0cd556b67c6157a98",
    },
    {
      project: "PROJECT_ORBIT_FACILITIES",
      version: "v2_20260822",
      sha256:
        "9f9f14f344dbdd97f3743f20ea20960a020525addf8752c5cab9ca9867e02099",
    },
  ],
  coverage: {
    totalCells: 120662,
    validCells: 120662,
    integratedCells: 120662,
    r3LensCells: 84060,
    r3PassLensCells: 20118,
    r3NoLensCells: 36602,
    orbitDistanceRows: 482648,
    canonicalFacilities: 31544,
    missingDistances: 0,
    missingFacilityReferences: 0,
    cemetery: CEMETERY_COVERAGE,
    hospital: HOSPITAL_COVERAGE,
    shrine: RELIGION_COVERAGE,
    temple: RELIGION_COVERAGE,
  },
  policy: {
    unknownIsSafe: false,
    shrine: "context_only",
    generalHospital: "excluded_from_ranking",
  },
} as const satisfies IntegratedReleaseMetadata;

export const releaseMetadata = INTEGRATED_RELEASE_METADATA;

const GRID_ROW_COUNT = 624;
const GRID_COLUMN_COUNT = 462;
const FACILITY_SHARD_COUNT = 16;
export const INTEGRATED_PUBLIC_MANIFEST_SHA256 =
  "619a916dbbdb0a39239fa48207a5951925bca8ff1203ca34e6d324d5ae492138";
export const INTEGRATED_ROW_CACHE_LIMIT = 64;
const rowCache = new RowPromiseLruCache<
  number,
  RawRowShard
>(INTEGRATED_ROW_CACHE_LIMIT);
let releaseReadiness: Promise<ReadyRelease> | null = null;

function dataRoot(): string {
  const override = process.env.IYASHIRO_INTEGRATED_DATA_ROOT?.trim();
  return override || path.join(process.cwd(), "public", "data", "integrated");
}

function publicAssetBaseUrl(): string | null {
  const host =
    process.env.IYASHIRO_INTEGRATED_DATA_BASE_URL?.trim() ||
    process.env.VERCEL_URL?.trim() ||
    process.env.VERCEL_PROJECT_PRODUCTION_URL?.trim();
  if (!host) return null;
  return host.startsWith("http://") || host.startsWith("https://")
    ? host.replace(/\/+$/, "")
    : "https://" + host.replace(/\/+$/, "");
}

function errorCode(error: unknown): string | null {
  return typeof error === "object" && error !== null && "code" in error
    ? String(error.code)
    : null;
}

async function readIntegratedAsset(relativePath: string): Promise<string> {
  const baseUrl = publicAssetBaseUrl();
  if (baseUrl) {
    const bypassSecret = process.env.VERCEL_AUTOMATION_BYPASS_SECRET?.trim();
    let response: Response;
    try {
      response = await fetch(
        baseUrl + "/data/integrated/" + relativePath,
        {
          cache: "force-cache",
          headers: bypassSecret ? { "x-vercel-protection-bypass": bypassSecret } : undefined,
        },
      );
    } catch {
      throw new IntegratedReleaseNotReadyError(
        "Integrated data artifact fetch failed: " + relativePath,
      );
    }
    if (response.status === 404) {
      throw new IntegratedArtifactMissingError(relativePath);
    }
    if (!response.ok) {
      throw new IntegratedReleaseNotReadyError(
        "Integrated data artifact fetch failed (" +
          response.status +
          "): " +
          relativePath,
      );
    }
    return response.text();
  }

  // Local execution may read public data. Vercel always self-fetches above so
  // output tracing does not duplicate the integrated corpus into Functions.
  const fs = process.getBuiltinModule(
    /* turbopackIgnore: true */ "fs",
  );
  if (!fs) {
    throw new IntegratedReleaseNotReadyError(
      "Node fs is unavailable for local integrated data loading.",
    );
  }
  const localPath = path.join(
    /* turbopackIgnore: true */ dataRoot(),
    relativePath,
  );
  try {
    return await fs.promises.readFile(localPath, "utf8");
  } catch (error) {
    if (errorCode(error) !== "ENOENT") {
      throw new IntegratedReleaseNotReadyError(
        "Integrated data artifact could not be read: " + relativePath,
      );
    }
  }
  throw new IntegratedArtifactMissingError(relativePath);
}

function parseJsonAsset<T>(text: string, relativePath: string): T {
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new IntegratedReleaseNotReadyError(
      "Integrated data artifact is not valid JSON: " + relativePath,
    );
  }
}

async function utf8Integrity(text: string): Promise<ArtifactIntegrity> {
  const bytes = new TextEncoder().encode(text);
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) {
    throw new IntegratedReleaseNotReadyError(
      "SHA-256 verification is unavailable for integrated data.",
    );
  }
  let digest: ArrayBuffer;
  try {
    digest = await subtle.digest("SHA-256", bytes);
  } catch {
    throw new IntegratedReleaseNotReadyError(
      "SHA-256 verification failed for integrated data.",
    );
  }
  return {
    bytes: bytes.byteLength,
    sha256: Array.from(new Uint8Array(digest), (value) =>
      value.toString(16).padStart(2, "0"),
    ).join(""),
  };
}

async function verifyArtifactIntegrity(
  text: string,
  relativePath: string,
  expected: { bytes?: number; sha256: string },
): Promise<void> {
  const actual = await utf8Integrity(text);
  if (
    (expected.bytes !== undefined && actual.bytes !== expected.bytes) ||
    actual.sha256 !== expected.sha256
  ) {
    throw new IntegratedReleaseNotReadyError(
      "Integrated data artifact failed integrity validation: " +
        relativePath,
    );
  }
}

function expectedRowPath(gridRow: number): string {
  return "rows/g" + gridRow.toString().padStart(3, "0") + ".json";
}

function expectedFacilityPath(shardIndex: number): string {
  return "facilities/part-" + shardIndex.toString(16) + ".json";
}

function validatedArtifactMap(
  declarations: RawArtifactDeclaration[] | undefined,
  expectedPaths: readonly string[],
): Map<string, ArtifactIntegrity> | null {
  if (
    !Array.isArray(declarations) ||
    declarations.length !== expectedPaths.length
  ) {
    return null;
  }
  const expected = new Set(expectedPaths);
  const artifacts = new Map<string, ArtifactIntegrity>();
  for (const declaration of declarations) {
    const artifactPath = declaration?.path;
    const bytes = declaration?.bytes;
    const sha256 = declaration?.sha256;
    if (
      typeof artifactPath !== "string" ||
      !expected.has(artifactPath) ||
      artifacts.has(artifactPath) ||
      typeof bytes !== "number" ||
      !Number.isSafeInteger(bytes) ||
      bytes <= 0 ||
      typeof sha256 !== "string" ||
      !/^[0-9a-f]{64}$/i.test(sha256)
    ) {
      return null;
    }
    artifacts.set(artifactPath, {
      bytes,
      sha256: sha256.toLowerCase(),
    });
  }
  return artifacts.size === expectedPaths.length ? artifacts : null;
}

async function readReleaseReadiness(): Promise<ReadyRelease> {
  const manifestPath = "release-manifest.json";
  const manifestText = await readIntegratedAsset(manifestPath);
  await verifyArtifactIntegrity(manifestText, manifestPath, {
    sha256: INTEGRATED_PUBLIC_MANIFEST_SHA256,
  });
  const manifest = parseJsonAsset<RawReleaseManifest>(
    manifestText,
    manifestPath,
  );
  const rows = manifest.outputs?.rowShards;
  const rowArtifacts = validatedArtifactMap(
    rows,
    Array.from({ length: GRID_ROW_COUNT }, (_, gridRow) =>
      expectedRowPath(gridRow),
    ),
  );
  const facilityArtifacts = validatedArtifactMap(
    manifest.outputs?.facilityShards,
    Array.from({ length: FACILITY_SHARD_COUNT }, (_, shardIndex) =>
      expectedFacilityPath(shardIndex),
    ),
  );
  const sourcesReady =
    Array.isArray(manifest.sources) &&
    manifest.sources.length === releaseMetadata.sources.length &&
    releaseMetadata.sources.every((expected, index) => {
      const actual = manifest.sources?.[index];
      return (
        actual?.project === expected.project &&
        actual.version === expected.version &&
        actual.sha256 === expected.sha256 &&
        (actual.pointer === undefined || actual.pointer === null)
      );
    });
  const ready =
    manifest.schemaVersion === releaseMetadata.schemaVersion &&
    manifest.releaseId === releaseMetadata.releaseId &&
    sourcesReady &&
    manifest.qa?.status === "PASS" &&
    manifest.qa?.allGridRowsMaterialized === true &&
    manifest.qa?.publicR3SourcePointersRedacted === true &&
    manifest.qa?.publicR3SourcePointerValuesRedacted === 336240 &&
    manifest.outputs?.rowShardCount === GRID_ROW_COUNT &&
    manifest.outputs?.facilityShardCount === FACILITY_SHARD_COUNT &&
    rowArtifacts !== null &&
    facilityArtifacts !== null &&
    manifest.coverage?.validCells ===
      releaseMetadata.coverage.validCells &&
    manifest.coverage?.integratedCells ===
      releaseMetadata.coverage.integratedCells &&
    manifest.coverage?.r3LensCells ===
      releaseMetadata.coverage.r3LensCells &&
    manifest.coverage?.r3PassLensCells ===
      releaseMetadata.coverage.r3PassLensCells &&
    manifest.coverage?.orbitDistanceRows ===
      releaseMetadata.coverage.orbitDistanceRows &&
    manifest.coverage?.canonicalFacilities ===
      releaseMetadata.coverage.canonicalFacilities;
  if (!ready) {
    throw new IntegratedReleaseNotReadyError(
      "Integrated release manifest failed readiness validation.",
    );
  }
  return { rowShardArtifacts: rowArtifacts };
}

function loadReleaseReadiness(): Promise<ReadyRelease> {
  if (releaseReadiness) return releaseReadiness;
  const pending = readReleaseReadiness().catch((error: unknown) => {
    if (releaseReadiness === pending) releaseReadiness = null;
    throw error;
  });
  releaseReadiness = pending;
  return pending;
}

export async function ensureIntegratedReleaseReady(): Promise<
  IntegratedReleaseMetadata
> {
  await loadReleaseReadiness();
  return releaseMetadata;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function asBoolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function thresholdStatus(
  distanceM: number | null,
  thresholdM: number | null,
): IntegratedThresholdStatus {
  if (distanceM === null) return "unknown";
  if (thresholdM === null) return "not_evaluated";
  return distanceM <= thresholdM
    ? "inside_threshold"
    : "outside_threshold";
}

function decisionStatus(
  distanceM: number | null,
  thresholdM: number | null,
  gateRole: IntegratedGateRole,
  completeCoverage: boolean,
): IntegratedDecisionStatus {
  if (gateRole === "context_only") return "context_only";
  if (gateRole === "excluded_from_ranking") {
    return "excluded_from_ranking";
  }
  if (distanceM === null || thresholdM === null) return "unknown";
  if (distanceM <= thresholdM) return "fail";
  return completeCoverage ? "pass_current_evidence" : "unknown";
}

function orbitFact(
  tuple: RawDistanceTuple,
  kind: IntegratedDistanceKind,
  coverage: string,
  gateRole: IntegratedGateRole,
  thresholdM: number | null,
  completeCoverage: boolean,
): IntegratedDistanceFact {
  const distanceM = asNumber(tuple[0]);
  return {
    kind,
    distanceM,
    nearestFacilityId: asString(tuple[1]),
    name: asString(tuple[2]),
    address: asString(tuple[3]),
    geometryBasis: asString(tuple[4]),
    beds: asNumber(tuple[5]),
    largeInpatientHospital: asBoolean(tuple[6]),
    sourceProject: "PROJECT_ORBIT",
    sourceVersion: "v2_20260822",
    coverage,
    gateRole,
    thresholdM,
    thresholdStatus: thresholdStatus(distanceM, thresholdM),
    decisionStatus: decisionStatus(
      distanceM,
      thresholdM,
      gateRole,
      completeCoverage,
    ),
  };
}

function r3Fact(
  r3: RawR3Tuple | null,
  kind: "largeHospital" | "strongHistory" | "p8",
  distanceIndex: number,
  nameIndex: number | null,
  coverage: string,
): IntegratedDistanceFact {
  const distanceM = r3 ? asNumber(r3[distanceIndex]) : null;
  const name = r3 && nameIndex !== null ? asString(r3[nameIndex]) : null;
  return {
    kind,
    distanceM,
    nearestFacilityId: null,
    name,
    address: null,
    geometryBasis: null,
    beds:
      kind === "largeHospital" && r3 ? asNumber(r3[R3.beds]) : null,
    largeInpatientHospital:
      kind === "largeHospital" && r3 ? true : null,
    sourceProject: "ALL_PROJECT_INTEGRATED_TOP20_R3",
    sourceVersion: "R3_20260822",
    coverage,
    gateRole: "hard_veto",
    thresholdM: 500,
    thresholdStatus: thresholdStatus(distanceM, 500),
    decisionStatus:
      distanceM === null
        ? "unknown"
        : distanceM <= 500
          ? "fail"
          : "pass_current_evidence",
  };
}

async function readRowShard(gridRow: number): Promise<RawRowShard> {
  const relativePath = expectedRowPath(gridRow);
  const readiness = await loadReleaseReadiness();
  const integrity = readiness.rowShardArtifacts.get(relativePath);
  if (!integrity) {
    throw new IntegratedReleaseNotReadyError(
      "Integrated release manifest does not declare: " + relativePath,
    );
  }
  const text = await readIntegratedAsset(relativePath);
  await verifyArtifactIntegrity(text, relativePath, integrity);
  return parseJsonAsset<RawRowShard>(text, relativePath);
}

function loadRowShard(gridRow: number): Promise<RawRowShard> {
  const cached = rowCache.get(gridRow);
  if (cached) return cached;
  const pending = readRowShard(gridRow).catch((error: unknown) => {
    rowCache.deleteIfSame(gridRow, pending);
    throw error;
  });
  rowCache.set(gridRow, pending);
  return pending;
}

function findCell(
  cells: RawCellTuple[],
  gridColumn: number,
): RawCellTuple | null {
  let lower = 0;
  let upper = cells.length - 1;
  while (lower <= upper) {
    const middle = (lower + upper) >> 1;
    const column = cells[middle][1];
    if (column === gridColumn) return cells[middle];
    if (column < gridColumn) lower = middle + 1;
    else upper = middle - 1;
  }
  return null;
}

function addressLabel(
  municipality: string | null,
  town: string | null,
): string | null {
  const combined = ((municipality ?? "") + (town ?? "")).trim();
  return combined || null;
}

function buildR3Layer(r3: RawR3Tuple | null): IntegratedCellRecord["layers"]["r3"] {
  const spiritualPass = r3 ? asBoolean(r3[R3.spiritualPass]) : null;
  const v15Rank = r3 ? asNumber(r3[R3.v15Rank]) : null;
  const ryRank = r3 ? asNumber(r3[R3.ryRank]) : null;
  const lensScore = r3 ? asNumber(r3[R3.lensScore]) : null;
  const hasLensRecord = r3 !== null && (
    spiritualPass !== null ||
    v15Rank !== null ||
    ryRank !== null ||
    lensScore !== null ||
    asString(r3[R3.v15Zone]) !== null ||
    asString(r3[R3.ryZone]) !== null
  );
  return {
    project: "ALL_PROJECT_INTEGRATED_TOP20",
    version: "R3_20260822",
    availability: hasLensRecord ? "available" : "unknown_no_lens_record",
    spiritualPass,
    currentEvidenceDecision:
      spiritualPass === true
        ? "pass_current_evidence"
        : spiritualPass === false
          ? "fail_current_evidence"
          : "unknown",
    core650m: r3 ? asBoolean(r3[R3.core650m]) : null,
    failReasons: r3 ? asStringList(r3[R3.failReasons]) : [],
    integratedCellScore: r3
      ? asNumber(r3[R3.integratedCellScore])
      : null,
    lensScore,
    minimumMarginM: r3 ? asNumber(r3[R3.minimumMarginM]) : null,
    rankings: {
      v15PureRank: v15Rank,
      ryumyakPureRank: ryRank,
      sourceFirstAreaRank: null,
      robustnessAreaRank: null,
      areaRankCoverage: "not_cell_addressable_in_r3_release",
    },
    v15: {
      rank: v15Rank,
      zone: r3 ? asString(r3[R3.v15Zone]) : null,
      regime: r3 ? asString(r3[R3.v15Regime]) : null,
    },
    ryumyak: {
      rank: ryRank,
      zone: r3 ? asString(r3[R3.ryZone]) : null,
      area: r3 ? asString(r3[R3.ryArea]) : null,
      confidence: r3 ? asString(r3[R3.ryConfidence]) : null,
      currentWater: r3 ? asString(r3[R3.ryCurrentWater]) : null,
      hardSplit: r3 ? asString(r3[R3.ryHardSplit]) : null,
    },
    context: {
      moisture: r3 ? asString(r3[R3.moisture]) : null,
      groundwaterBand: r3 ? asString(r3[R3.groundwaterBand]) : null,
      jshisRisk: r3 ? asNumber(r3[R3.jshisRisk]) : null,
      jshisDetail: r3 ? asString(r3[R3.jshisDetail]) : null,
      wetHistory: r3 ? asBoolean(r3[R3.wetHistory]) : null,
      p7KnownEras: r3 ? asNumber(r3[R3.p7KnownEras]) : null,
      p7State: r3 ? asString(r3[R3.p7State]) : null,
      eventregFatalities: r3
        ? asNumber(r3[R3.eventregFatalities])
        : null,
      eventregWithin500m: r3
        ? asNumber(r3[R3.eventregWithin500m])
        : null,
      veilWithin500mCount: r3
        ? asNumber(r3[R3.veilWithin500mCount])
        : null,
      veilState: r3 ? asString(r3[R3.veilState]) : null,
      ecoscapeState: r3 ? asString(r3[R3.ecoscapeState]) : null,
      ecoscapeTier: r3 ? asString(r3[R3.ecoscapeTier]) : null,
      placegraphStatus: r3
        ? asString(r3[R3.placegraphStatus])
        : null,
      identityConflicts: r3
        ? asNumber(r3[R3.identityConflicts])
        : null,
    },
    sources: {
      v15: null,
      ryumyak: null,
      orbit: null,
      history: null,
    },
  };
}

export async function lookupIntegratedCell(
  cellId: string,
): Promise<IntegratedCellRecord | null> {
  const match = /^g([0-9]+)-([0-9]+)$/.exec(cellId);
  if (!match) return null;
  const gridRow = Number(match[1]);
  const gridCol = Number(match[2]);
  if (
    !Number.isInteger(gridRow) ||
    !Number.isInteger(gridCol) ||
    gridRow < 0 ||
    gridRow >= GRID_ROW_COUNT ||
    gridCol < 0 ||
    gridCol >= GRID_COLUMN_COUNT
  ) {
    return null;
  }

  const shard = await loadRowShard(gridRow);
  if (
    shard.schemaVersion !== "iyashiro-integrated-data/1.0" ||
    shard.releaseId !== releaseMetadata.releaseId ||
    shard.gridRow !== gridRow ||
    !Array.isArray(shard.cells)
  ) {
    throw new IntegratedReleaseNotReadyError(
      "Integrated row shard contract mismatch: g" + gridRow,
    );
  }
  const raw = findCell(shard.cells, gridCol);
  if (!raw || raw[0] !== cellId) return null;

  const r3 = raw[9];
  const municipality = r3 ? asString(r3[R3.municipality]) : null;
  const town = r3 ? asString(r3[R3.town]) : null;
  const temple = orbitFact(
    raw[5],
    "temple",
    RELIGION_COVERAGE,
    "hard_veto",
    500,
    false,
  );
  const shrine = orbitFact(
    raw[6],
    "shrine",
    RELIGION_COVERAGE,
    "context_only",
    null,
    false,
  );
  const cemetery = orbitFact(
    raw[7],
    "cemetery",
    CEMETERY_COVERAGE,
    "hard_veto",
    500,
    false,
  );
  const generalHospital = orbitFact(
    raw[8],
    "generalHospital",
    HOSPITAL_COVERAGE,
    "excluded_from_ranking",
    null,
    true,
  );
  const largeHospital = r3Fact(
    r3,
    "largeHospital",
    R3.largeHospitalM,
    R3.largeHospitalName,
    HOSPITAL_COVERAGE,
  );
  const strongHistory = r3Fact(
    r3,
    "strongHistory",
    R3.strongHistoryEffectiveM,
    R3.strongHistoryName,
    "R3_LOCATED_HISTORY_CURRENT_EVIDENCE",
  );
  const p8 = r3Fact(
    r3,
    "p8",
    R3.p8MinM,
    null,
    "V11_P8_LOCATED_CONTEXT_CURRENT_EVIDENCE",
  );

  const unknowns = [
    CEMETERY_COVERAGE,
    RELIGION_COVERAGE,
    ...(r3
      ? [
          "RYUMYAK current-water geometry is OPEN_NOT_MATERIALIZED.",
          "R3 pass is a current-evidence gate result, not a general safety claim.",
          "Source-first and robustness ranks are area-family ranks and are not cell-addressable in this release.",
        ]
      : [
          "This valid canonical cell has no R3 lens-ledger row; R3 pass/fail is UNKNOWN.",
          "Large-hospital, strong-history and P8 R3 distances are UNKNOWN for this no-lens cell.",
        ]),
  ];

  return {
    cellId,
    gridRow,
    gridCol,
    lat: raw[2],
    lon: raw[3],
    valid: true,
    municipalityIndex: raw[4],
    municipality,
    town,
    address: addressLabel(municipality, town),
    sourceRank: {
      v15: r3 ? asNumber(r3[R3.v15Rank]) : null,
      ryumyak: r3 ? asNumber(r3[R3.ryRank]) : null,
    },
    release: releaseMetadata,
    layers: {
      orbit: {
        project: "PROJECT_ORBIT",
        version: "v2_20260822",
        availability: "available",
        scoreEffect: "none",
        categoryCount: 4,
        missingDistances: false,
        coverage: {
          cemetery: CEMETERY_COVERAGE,
          hospital: HOSPITAL_COVERAGE,
          shrine: RELIGION_COVERAGE,
          temple: RELIGION_COVERAGE,
        },
      },
      r3: buildR3Layer(r3),
    },
    distances: {
      temple,
      cemetery,
      largeHospital,
      generalHospital,
      shrine,
      strongHistory,
      p8,
    },
    unknowns,
  };
}

export function clearIntegratedDataCacheForTests(): void {
  rowCache.clear();
  releaseReadiness = null;
}

export function integratedDataCacheSizeForTests(): number {
  return rowCache.size;
}
