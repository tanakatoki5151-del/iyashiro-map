import { NextRequest, NextResponse } from "next/server";
import { diagnoseLocation } from "@/app/lib/diagnose";
import { isAddressLabelInScope } from "@/app/lib/geo";
import { composeLocationProfile } from "@/app/lib/location-profile/compose";
import { resolveCanonicalCell } from "@/app/lib/location-profile/canonical-cell";
import { buildPlaceGraphLayer, type PlaceGraphAdapterData } from "@/app/lib/location-profile/placegraph-adapter";
import { placeGraphSparseCells } from "@/app/lib/location-profile/placegraph-sparse-runtime";
import type { LayerId, LocationLayer, LocationProfileAudience } from "@/app/lib/location-profile/types";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 60;

type GsiFeature = {
  geometry?: { coordinates?: [number, number] };
  properties?: { title?: string };
};

async function resolveQuery(request: NextRequest) {
  const q = request.nextUrl.searchParams.get("q")?.trim() ?? "";
  const latParam = request.nextUrl.searchParams.get("lat");
  const lngParam = request.nextUrl.searchParams.get("lng");
  const lat = latParam === null ? Number.NaN : Number(latParam);
  const lng = lngParam === null ? Number.NaN : Number(lngParam);
  if (Number.isFinite(lat) && Number.isFinite(lng)) {
    return { query: q || null, matchedAddress: null as string | null, lat, lng };
  }
  if (q.length < 2 || q.length > 120) {
    throw new TypeError("q または lat/lng を指定してください。");
  }
  const endpoint = new URL("https://msearch.gsi.go.jp/address-search/AddressSearch");
  endpoint.searchParams.set("q", q);
  const response = await fetch(endpoint);
  if (!response.ok) throw new Error("geocoder failed");
  const features = (await response.json()) as GsiFeature[];
  const match = features
    .map((feature) => ({
      label: feature.properties?.title ?? "",
      lng: Number(feature.geometry?.coordinates?.[0]),
      lat: Number(feature.geometry?.coordinates?.[1]),
    }))
    .find(
      (candidate) =>
        candidate.label &&
        Number.isFinite(candidate.lat) &&
        Number.isFinite(candidate.lng) &&
        isAddressLabelInScope(candidate.label),
    );
  if (!match) throw new RangeError("対象範囲に一致する住所が見つかりませんでした。");
  return { query: q, matchedAddress: match.label, lat: match.lat, lng: match.lng };
}

function readinessLayer(
  layerId: LayerId,
  project: string,
  state: "partial" | "not_available",
  note: string,
): LocationLayer {
  return {
    layerId,
    project,
    availability: state,
    coverageStatus: state === "partial" ? "source_limited" : "unknown",
    scoringEffect: "none",
    datasetVersion: null,
    findings: [],
    warnings: [note],
    metadata: { integrationState: state === "partial" ? "ADAPTER_STAGED" : "FORMAL_RELEASE_PENDING" },
  };
}

export async function GET(request: NextRequest) {
  try {
    const resolved = await resolveQuery(request);
    const diagnosis = await diagnoseLocation(resolved.lat, resolved.lng);
    const cell = resolveCanonicalCell(resolved.lat, resolved.lng);
    const audience: LocationProfileAudience =
      request.nextUrl.searchParams.get("audience") === "owner" ? "owner" : "public";

    const placeGraphData: PlaceGraphAdapterData = {
      buildId: "placegraph-operational-l4-20260817-v1",
      runId: "PG-FD-RUN-000028",
      defaultCellStatus: "NO_INDEXED_CANDIDATE_SOURCE_LIMITED",
      sourceCoverageCeiling: "PARTIAL_KNOWN_SOURCES",
      sparseCells: placeGraphSparseCells(),
      linksByCell: {},
      featuresById: {},
      geometriesByFeatureId: {},
    };
    const placeGraph = buildPlaceGraphLayer({ audience, cellId: cell.cellId, data: placeGraphData });
    const indexed = placeGraphData.sparseCells[cell.cellId];
    placeGraph.warnings = [
      ...placeGraph.warnings,
      ...(indexed && indexed.totalLinks > 0
        ? [
            `${indexed.totalLinks} PLACEGRAPH relation(s) are indexed for this cell. Detailed owner records remain server-side gated until the internal payload adapter is connected.`,
          ]
        : []),
    ];

    const layers: LocationLayer[] = [
      placeGraph,
      readinessLayer(
        "v10Legacy",
        "V10",
        "partial",
        "V10 has a canonical-cell adapter upstream; its fact payload is not yet duplicated into LocationProfile v2. Legacy diagnosis remains available separately.",
      ),
      readinessLayer(
        "v11Terrain",
        "V11",
        "partial",
        "V11 history/terrain contracts are staged. Missing evidence must remain UNKNOWN and is never converted to safety.",
      ),
      readinessLayer(
        "veil",
        "VEIL",
        "partial",
        "VEIL is currently partial/cohort-backed. Folklore, incident, taboo and physical facts will stay separated when the payload adapter is connected.",
      ),
      readinessLayer(
        "underland",
        "UNDERLAND",
        "partial",
        "UNDERLAND is currently cohort/pointer-backed. Outside researched cohorts means NOT_RESEARCHED, not a positive or negative conclusion.",
      ),
      readinessLayer(
        "limen",
        "LIMEN",
        "partial",
        "LIMEN is currently partial. Boundary, ritual and relocation facts require identity/geometry before positive spatial claims.",
      ),
      readinessLayer(
        "ecoscape",
        "ECOSCAPE",
        "not_available",
        "ECOSCAPE formal release is pending; unreleased source families remain UNKNOWN.",
      ),
    ];

    const profile = composeLocationProfile({
      audience,
      query: resolved.query,
      matchedAddress: resolved.matchedAddress,
      queryAnchor: {
        anchorId: `query:${resolved.lat.toFixed(6)},${resolved.lng.toFixed(6)}`,
        anchorType: resolved.matchedAddress ? "address_point" : "representative_point",
        lat: resolved.lat,
        lng: resolved.lng,
        precisionClass: resolved.matchedAddress ? "GSI_ADDRESS_POINT" : "COORDINATE_INPUT",
        uncertaintyMeters: resolved.matchedAddress ? 100 : null,
        source: resolved.matchedAddress ? "GSI_ADDRESS_SEARCH" : "USER_COORDINATE",
        sourceDate: "current",
        acquiredAt: new Date().toISOString(),
        matchedAddress: resolved.matchedAddress,
        cellId: cell.cellId,
      },
      spatialContext: {
        supported: diagnosis.scope.supported,
        cellId: cell.cellId,
        gridRow: cell.gridRow,
        gridCol: cell.gridCol,
        municipalityId: diagnosis.scope.municipalityCode,
        municipalityCode: diagnosis.scope.municipalityCode,
        municipalityName: diagnosis.scope.address,
        cellCenter: { lat: cell.centerLat, lng: cell.centerLng },
        spatialCoreVersion: "canonical-100m-v1",
        spatialCoreSha: null,
      },
      legacyRuntime: diagnosis as unknown as Readonly<Record<string, unknown>>,
      layers,
      coverage: {
        cellClosureStatus:
          indexed?.indexStatus ?? "NO_INDEXED_CANDIDATE_SOURCE_LIMITED",
        sourceCoverageCeiling: "PARTIAL_KNOWN_SOURCES",
        absenceClaimAllowed: false,
        lastUpdatedAt: "2026-08-17",
        refreshPolicy: "REFRESH_ON_FEEDER_DELTA_OR_SOURCE_COVERAGE_CHANGE",
        notes: [
          "Operational L4 uses a user-approved 100m tolerance.",
          "No known relation is not evidence that a cell is historically empty or safe.",
          "Research projects keep their own evidence status; LocationProfile does not rescore them.",
        ],
      },
    });

    return NextResponse.json(profile, {
      headers: {
        "Cache-Control": "public, s-maxage=86400, stale-while-revalidate=604800",
        "Access-Control-Allow-Origin": "*",
      },
    });
  } catch (error) {
    const status = error instanceof TypeError ? 400 : error instanceof RangeError ? 404 : 502;
    return NextResponse.json(
      {
        error: status === 400 ? "invalid_query" : status === 404 ? "not_found" : "profile_failed",
        message: error instanceof Error ? error.message : "土地カルテの生成に失敗しました。",
      },
      { status },
    );
  }
}
