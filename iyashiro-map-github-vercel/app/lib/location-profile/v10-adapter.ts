import "server-only";
import type { LocationLayer } from "./types";

const SOURCE_URL = "https://drive.google.com/uc?export=download&id=17p0FtJjuRX5LLpSwp7jp1pImKM7-x-S8";
const SOURCE_SHA = "8756f7bff8e917355e87c0aa7d5fe156d2340356ac030eecfd51ab1ed91c511f";
const INVALID = 255;

type V10Catalog = {
  schemaVersion: string;
  buildId: string;
  cellCount: number;
  grid: { rows: number; columns: number };
  labels: string[];
  data: Record<string, string>;
};

type DecodedCatalog = {
  catalog: V10Catalog;
  fields: Record<string, Uint8Array>;
};

let catalogPromise: Promise<DecodedCatalog> | null = null;

function decode(text: string): Uint8Array {
  return new Uint8Array(Buffer.from(text, "base64"));
}

async function loadCatalog(): Promise<DecodedCatalog> {
  if (!catalogPromise) {
    catalogPromise = fetch(SOURCE_URL, { next: { revalidate: 86400 } })
      .then(async (response) => {
        if (!response.ok) throw new Error(`V10 source fetch failed: ${response.status}`);
        const catalog = (await response.json()) as V10Catalog;
        const fields = Object.fromEntries(
          [
            "labelCode",
            "originalScore",
            "originalFit",
            "auxiliaryTerrainScore",
            "detailScore",
            "neighborhoodScore",
            "confidence",
          ].map((name) => [name, decode(catalog.data[name])]),
        );
        return { catalog, fields };
      })
      .catch((error) => {
        catalogPromise = null;
        throw error;
      });
  }
  return catalogPromise;
}

function value(raw: number | undefined): number | null {
  return raw === undefined || raw === INVALID ? null : raw;
}

export async function buildV10Layer(row: number, col: number): Promise<LocationLayer> {
  try {
    const { catalog, fields } = await loadCatalog();
    if (row < 0 || row >= catalog.grid.rows || col < 0 || col >= catalog.grid.columns) {
      return {
        layerId: "v10Legacy",
        project: "V10",
        availability: "not_applicable",
        coverageStatus: "unknown",
        scoringEffect: "none",
        datasetVersion: catalog.buildId,
        sourceRegistryVersion: SOURCE_SHA,
        findings: [],
        warnings: ["The query falls outside the frozen V10 grid."],
      };
    }
    const index = row * catalog.grid.columns + col;
    const labelCode = value(fields.labelCode[index]);
    if (labelCode === null) {
      return {
        layerId: "v10Legacy",
        project: "V10",
        availability: "partial",
        coverageStatus: "source_limited",
        scoringEffect: "none",
        datasetVersion: catalog.buildId,
        sourceRegistryVersion: SOURCE_SHA,
        findings: [],
        warnings: ["This grid position is not a valid V10 target cell; no safety or absence inference is allowed."],
      };
    }
    const label = catalog.labels[labelCode] ?? `label-${labelCode}`;
    const originalScore = value(fields.originalScore[index]);
    const originalFit = value(fields.originalFit[index]);
    const auxiliaryTerrainScore = value(fields.auxiliaryTerrainScore[index]);
    const detailScore = value(fields.detailScore[index]);
    const neighborhoodScore = value(fields.neighborhoodScore[index]);
    const confidence = value(fields.confidence[index]);

    return {
      layerId: "v10Legacy",
      project: "V10",
      availability: "available",
      coverageStatus: "complete_for_defined_sources",
      scoringEffect: "none",
      datasetVersion: catalog.buildId,
      sourceRegistryVersion: SOURCE_SHA,
      findings: [
        {
          findingId: `V10-CELL-${row}-${col}`,
          project: "V10",
          globalFeatureId: null,
          localPointer: `regional-catalog-v4:${index}`,
          title: `V10凍結セル判定: ${label}`,
          category: "terrain_hypothesis_context",
          status: "context",
          evidenceMaturity: "context_only",
          geometryRole: "canonical_100m_cell",
          spatialRelation: "cell_context",
          distanceMeters: 0,
          uncertaintyMeters: 100,
          validFrom: null,
          validTo: null,
          publicPrecision: "100m_cell",
          independenceGroup: "V10_FROZEN_REGIONAL_CATALOG_V4",
          canonicalSourceIdentity: `V10:${catalog.buildId}:${index}`,
          explanation: `原典判定 ${originalScore ?? "—"}、原典適合 ${originalFit ?? "—"}、補助地形 ${auxiliaryTerrainScore ?? "—"}、詳細 ${detailScore ?? "—"}、周辺 ${neighborhoodScore ?? "—"}、信頼度 ${confidence ?? "—"}。V10は独立レンズとして表示し、他ProjectのFactと平均・加算しません。`,
          sourcePointers: [
            {
              project: "V10",
              pointer: "regional-catalog-v4.json",
              title: "V10 frozen regional catalog v4",
              version: catalog.buildId,
            },
          ],
          metadata: { labelCode, originalScore, originalFit, auxiliaryTerrainScore, detailScore, neighborhoodScore, confidence },
        },
      ],
      warnings: [
        "V10の凍結セル判定は地形仮説・研究レンズであり、歴史featureの不存在や安全を証明しません。",
        "LocationProfileではV10を再採点せず、legacyRuntimeの現行診断とも別カードとして保持します。",
      ],
      metadata: { sourceFile: "regional-catalog-v4.json", sourceSha256: SOURCE_SHA, cellCount: catalog.cellCount },
    };
  } catch (error) {
    return {
      layerId: "v10Legacy",
      project: "V10",
      availability: "error",
      coverageStatus: "unknown",
      scoringEffect: "none",
      datasetVersion: null,
      findings: [],
      warnings: [error instanceof Error ? error.message : "V10 source could not be loaded."],
      metadata: { sourceFile: "regional-catalog-v4.json", sourceSha256: SOURCE_SHA },
    };
  }
}
