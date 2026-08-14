import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";

export const VEIL_CANONICAL_SOURCE = Object.freeze({
  fileName: "regional-catalog-v4.json",
  driveFileId: "17p0FtJjuRX5LLpSwp7jp1pImKM7-x-S8",
  sha256: "8756f7bff8e917355e87c0aa7d5fe156d2340356ac030eecfd51ab1ed91c511f",
  cellCount: 120_662,
  municipalityCount: 48,
  regionCounts: Object.freeze({
    tokyo23: 62_553,
    yokohama: 43_785,
    kawasaki: 14_324,
  }),
});

const EXPECTED_GRID = Object.freeze({
  rows: 624,
  columns: 462,
  originNorth: 35.839647862019405,
  originWest: 139.43,
  latitudeStep: 0.0008983111749910168,
  longitudeStep: 0.0011042452218025757,
  stepMeters: 100,
});

const SAFE_MUNICIPALITY_KEYS = new Set(["index", "code", "name", "cellCount"]);
const BLOCKED_TOP_LEVEL_KEYS = new Set(["labels"]);
const BLOCKED_DATA_KEYS = new Set([
  "originalScore",
  "originalFit",
  "labelCode",
  "confidence",
  "score",
  "ranking",
  "labels",
  "highEvidence",
  "lowEvidence",
  "ordinaryEvidence",
  "auxiliaryTerrainScore",
  "detailScore",
  "neighborhoodScore",
  "nearbyBestColumnOffset",
  "nearbyBestRowOffset",
]);

export function sha256Hex(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

function assertExactGrid(grid) {
  if (!grid || typeof grid !== "object") throw new Error("canonical grid missing");
  for (const [key, expected] of Object.entries(EXPECTED_GRID)) {
    if (grid[key] !== expected) throw new Error(`canonical grid mismatch at ${key}`);
  }
}

function sanitizeMunicipalities(municipalities) {
  if (!Array.isArray(municipalities)) throw new Error("municipalities must be an array");
  if (municipalities.length !== VEIL_CANONICAL_SOURCE.municipalityCount) {
    throw new Error("canonical municipalityCount mismatch");
  }

  const seen = new Set();
  return municipalities.map((item) => {
    if (!item || typeof item !== "object") throw new Error("invalid municipality record");
    const extraKeys = Object.keys(item).filter((key) => !SAFE_MUNICIPALITY_KEYS.has(key));
    if (extraKeys.length) throw new Error(`unsafe municipality fields: ${extraKeys.join(",")}`);
    if (!Number.isInteger(item.index) || item.index < 1 || item.index > 48) {
      throw new Error(`invalid municipality index: ${item.index}`);
    }
    if (seen.has(item.index)) throw new Error(`duplicate municipality index: ${item.index}`);
    seen.add(item.index);
    if (!/^\d{5}$/.test(String(item.code ?? ""))) throw new Error("invalid municipality code");
    if (typeof item.name !== "string" || !item.name) throw new Error("invalid municipality name");
    if (!Number.isInteger(item.cellCount) || item.cellCount < 0) throw new Error("invalid municipality cellCount");
    return Object.freeze({
      index: item.index,
      code: item.code,
      name: item.name,
      cellCount: item.cellCount,
    });
  });
}

function assertRegionCounts(municipalities) {
  const sum = (lo, hi) => municipalities
    .filter((m) => m.index >= lo && m.index <= hi)
    .reduce((n, m) => n + m.cellCount, 0);
  const actual = {
    tokyo23: sum(1, 23),
    yokohama: sum(24, 41),
    kawasaki: sum(42, 48),
  };
  for (const [region, expected] of Object.entries(VEIL_CANONICAL_SOURCE.regionCounts)) {
    if (actual[region] !== expected) {
      throw new Error(`canonical ${region} cellCount mismatch: ${actual[region]} != ${expected}`);
    }
  }
}

export function projectSafeVeilSpatialCatalog(rawCatalog) {
  if (!rawCatalog || typeof rawCatalog !== "object") throw new Error("canonical catalog object required");
  assertExactGrid(rawCatalog.grid);
  if (rawCatalog.cellCount !== VEIL_CANONICAL_SOURCE.cellCount) {
    throw new Error("canonical cellCount mismatch");
  }
  if (rawCatalog.municipalityCount !== VEIL_CANONICAL_SOURCE.municipalityCount) {
    throw new Error("canonical municipalityCount mismatch");
  }
  if (!rawCatalog.data || typeof rawCatalog.data.municipality !== "string") {
    throw new Error("canonical municipality membership missing");
  }

  const municipalities = sanitizeMunicipalities(rawCatalog.municipalities);
  assertRegionCounts(municipalities);

  // Explicit projection is the security boundary: none of the legacy Iyashiro
  // score/evidence arrays are retained in the object passed into VEIL.
  const safe = {
    grid: Object.freeze({ ...EXPECTED_GRID }),
    cellCount: rawCatalog.cellCount,
    municipalityCount: rawCatalog.municipalityCount,
    municipalities: Object.freeze(municipalities),
    data: Object.freeze({ municipality: rawCatalog.data.municipality }),
  };

  const serialized = JSON.stringify(safe);
  for (const key of BLOCKED_TOP_LEVEL_KEYS) {
    if (serialized.includes(`"${key}"`)) throw new Error(`blocked top-level field retained: ${key}`);
  }
  for (const key of BLOCKED_DATA_KEYS) {
    if (serialized.includes(`"${key}"`)) throw new Error(`blocked legacy field retained: ${key}`);
  }
  return Object.freeze(safe);
}

export async function loadVeilCanonicalCatalogFromFile(
  filePath,
  { expectedSha256 = VEIL_CANONICAL_SOURCE.sha256 } = {},
) {
  if (typeof filePath !== "string" || !filePath) throw new Error("catalog file path required");
  const bytes = await readFile(filePath);
  const actualSha256 = sha256Hex(bytes);
  if (actualSha256 !== expectedSha256) {
    throw new Error(`canonical SHA-256 mismatch: ${actualSha256} != ${expectedSha256}`);
  }

  let rawCatalog;
  try {
    rawCatalog = JSON.parse(bytes.toString("utf8"));
  } catch (error) {
    throw new Error(`canonical JSON parse failed: ${error.message}`);
  }

  return Object.freeze({
    catalog: projectSafeVeilSpatialCatalog(rawCatalog),
    integrity: Object.freeze({
      fileName: VEIL_CANONICAL_SOURCE.fileName,
      driveFileId: VEIL_CANONICAL_SOURCE.driveFileId,
      sha256: actualSha256,
      byteLength: bytes.length,
    }),
  });
}
