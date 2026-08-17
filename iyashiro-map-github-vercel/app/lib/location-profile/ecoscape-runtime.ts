import "server-only";
import { gunzipSync } from "node:zlib";
import c0 from "./ecoscape-runtime-chunk-0";
import c1 from "./ecoscape-runtime-chunk-1";
import c2 from "./ecoscape-runtime-chunk-2";
import c3 from "./ecoscape-runtime-chunk-3";
import c4 from "./ecoscape-runtime-chunk-4";

const ENCODED_GZIP = c0 + c1 + c2 + c3 + c4;

export const ECOSCAPE_RUNTIME_VERSION = "ECOSCAPE_PROPERTY_PROFILE_INDEX_120662_B120";
export const ECOSCAPE_BUILD_ID = "ecos-mw4-property-profile-adapter-20260817-b120";
export const ECOSCAPE_FORMAL_CELLS = 120662;
export const ECOSCAPE_GRID_WIDTH = 462;
export const ECOSCAPE_GRID_HEIGHT = 587;
const RECORD_SIZE = 7;

export const ecoscapeAggregateStates = ["INVALID", "NEUTRAL", "CAUTION", "CANDIDATE", "STRONG", "MIXED"] as const;
export const ecoscapeResidentialTiers = [
  "INVALID",
  "A_BUILT_UP_CONTINUITY",
  "B_CURRENT_BUILDINGS_HISTORIC_REVIEW",
  "NO_CURRENT_BUILDINGS",
  "HISTORIC_NONRESIDENTIAL_REVIEW",
  "UNKNOWN_PLATEAU_SOURCE_HOLE",
] as const;
export const ecoscapePlateauStatuses = ["INVALID", "PASS", "EXPLICIT_NO_BUILDINGS", "UNKNOWN_SOURCE_TILE_404"] as const;

export type EcoscapeRuntimeRecord = {
  gridIndex: number;
  robustEnvironmentalCandidate: boolean;
  thresholdStable: boolean;
  robustResidentialCandidate: boolean;
  aggregateStateP25: (typeof ecoscapeAggregateStates)[number];
  coreZone3Plus: boolean;
  residentialPlausibilityTier: (typeof ecoscapeResidentialTiers)[number];
  knownPillarsP25: number;
  favorablePillarsP25: number;
  cautionPillarsP25: number;
  plateauStatus: (typeof ecoscapePlateauStatuses)[number];
  robustCandidateShare300m: number;
  robustCandidateShare500m: number;
  residentialComponentId: string | null;
};

let decoded: Buffer | null = null;
function runtimeBuffer(): Buffer {
  if (!decoded) decoded = gunzipSync(Buffer.from(ENCODED_GZIP, "base64"));
  return decoded;
}

export function readEcoscapeRuntime(gridRow: number, gridCol: number): EcoscapeRuntimeRecord | null {
  if (!Number.isInteger(gridRow) || !Number.isInteger(gridCol) || gridRow < 0 || gridCol < 0 || gridRow >= ECOSCAPE_GRID_HEIGHT || gridCol >= ECOSCAPE_GRID_WIDTH) return null;
  const gridIndex = gridRow * ECOSCAPE_GRID_WIDTH + gridCol;
  const offset = gridIndex * RECORD_SIZE;
  const buffer = runtimeBuffer();
  if (offset + RECORD_SIZE > buffer.length) return null;
  const b0 = buffer[offset];
  if ((b0 & 1) === 0) return null;
  const b1 = buffer[offset + 1];
  const b2 = buffer[offset + 2];
  const aggregateStateP25 = ecoscapeAggregateStates[(b0 >> 4) & 0x7];
  const residentialPlausibilityTier = ecoscapeResidentialTiers[b1 & 0x7];
  const plateauStatus = ecoscapePlateauStatuses[(b2 >> 6) & 0x3];
  if (!aggregateStateP25 || aggregateStateP25 === "INVALID" || !residentialPlausibilityTier || residentialPlausibilityTier === "INVALID" || !plateauStatus || plateauStatus === "INVALID") return null;
  const zoneNumber = buffer[offset + 5] | (buffer[offset + 6] << 8);
  return {
    gridIndex,
    robustEnvironmentalCandidate: Boolean(b0 & 0x2),
    thresholdStable: Boolean(b0 & 0x4),
    robustResidentialCandidate: Boolean(b0 & 0x8),
    aggregateStateP25,
    coreZone3Plus: Boolean(b0 & 0x80),
    residentialPlausibilityTier,
    knownPillarsP25: (b1 >> 3) & 0x7,
    favorablePillarsP25: b2 & 0x7,
    cautionPillarsP25: (b2 >> 3) & 0x7,
    plateauStatus,
    robustCandidateShare300m: buffer[offset + 3] / 100,
    robustCandidateShare500m: buffer[offset + 4] / 100,
    residentialComponentId: zoneNumber ? `HRZ${String(zoneNumber).padStart(5, "0")}` : null,
  };
}
