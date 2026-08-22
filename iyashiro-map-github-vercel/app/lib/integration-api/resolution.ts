import { integratedDataRuntimeAvailable, lookupIntegratedCellRecord } from "./data-adapter";
import { ApiError } from "./errors";
import {
  boundedGeocodeSigmaM,
  inferGeocodeRoute,
  coordinateDistanceM,
  edgeMarginM,
  resolveTheoreticalCells,
  resolutionStability,
  type GeocodeRouteId,
} from "./grid";
import { geocodeAddress } from "./geocode";
import type { LocationResolution } from "./types";
import { finiteCoordinate, objectValue, optionalFiniteNumber, optionalString, roundNumber } from "./validation";

export const ADDRESS_COORDINATE_TOLERANCE_M = 250;

export interface ResolveInput {
  address: string | null;
  lat: number | null;
  lon: number | null;
  sigmaM: number;
  routeId: GeocodeRouteId;
  addressRouteId: Exclude<GeocodeRouteId, "USER_COORDINATE">;
}

export function parseResolveInput(
  value: unknown,
  addressEvidenceRoute: Exclude<GeocodeRouteId, "USER_COORDINATE"> = "GSI_JUKYO_BASE_NUMBER",
): ResolveInput {
  const body = objectValue(value);
  const coordinate = finiteCoordinate(body.lat, body.lon ?? body.lng);
  const address = optionalString(body.address, 120);
  if (!coordinate && !address) {
    throw new ApiError(400, "location_required", "address または lat/lon を指定してください。");
  }
  const routeId = inferGeocodeRoute(coordinate !== null, addressEvidenceRoute);
  const requestedSigmaM = optionalFiniteNumber(body.sigmaM, { minimum: 1, maximum: 500 });
  const sigmaM = boundedGeocodeSigmaM(routeId, requestedSigmaM);
  return {
    address,
    lat: coordinate?.lat ?? null,
    lon: coordinate?.lon ?? null,
    sigmaM,
    routeId,
    addressRouteId: addressEvidenceRoute,
  };
}

export async function resolveLocation(input: ResolveInput): Promise<LocationResolution> {
  const addressEvidence = input.address
    ? await geocodeAddress(input.address, input.addressRouteId)
    : null;
  const hasCoordinate = input.lat !== null && input.lon !== null;
  let consistency: LocationResolution["consistency"];
  if (hasCoordinate && addressEvidence) {
    const distanceM = coordinateDistanceM(
      { lat: input.lat!, lon: input.lon! },
      { lat: addressEvidence.lat, lon: addressEvidence.lon },
    );
    if (distanceM > ADDRESS_COORDINATE_TOLERANCE_M) {
      throw new ApiError(
        422,
        "address_coordinate_mismatch",
        "住所検索結果と指定座標が一致しません。候補を混同しないよう判定を停止しました。",
        {
          distanceM: roundNumber(distanceM, 2),
          toleranceM: ADDRESS_COORDINATE_TOLERANCE_M,
          coordinate: { lat: input.lat, lon: input.lon },
          addressPoint: { lat: addressEvidence.lat, lon: addressEvidence.lon },
          matchedAddress: addressEvidence.matchedAddress,
        },
      );
    }
    consistency = {
      status: "matched",
      toleranceM: ADDRESS_COORDINATE_TOLERANCE_M,
      distanceM: roundNumber(distanceM, 2),
      addressPoint: {
        lat: roundNumber(addressEvidence.lat, 9),
        lon: roundNumber(addressEvidence.lon, 9),
      },
    };
  } else {
    consistency = {
      status: hasCoordinate ? "coordinate_only" : "address_only",
      toleranceM: ADDRESS_COORDINATE_TOLERANCE_M,
      distanceM: null,
      addressPoint: addressEvidence
        ? { lat: roundNumber(addressEvidence.lat, 9), lon: roundNumber(addressEvidence.lon, 9) }
        : null,
    };
  }
  const geocoded = hasCoordinate
    ? {
        query: input.address,
        matchedAddress: addressEvidence?.matchedAddress ?? null,
        lat: input.lat!,
        lon: input.lon!,
        routeId: "USER_COORDINATE" as const,
      }
    : addressEvidence!;
  const sigmaM = input.sigmaM;
  const theoretical = resolveTheoreticalCells(geocoded.lat, geocoded.lon, sigmaM);
  if (!theoretical.length) {
    throw new ApiError(422, "out_of_grid", "座標はcanonical gridの理論範囲外です。");
  }

  const runtimeAvailable = await integratedDataRuntimeAvailable();
  if (!runtimeAvailable) {
    throw new ApiError(
      503,
      "integrated_data_unavailable",
      "統合データreleaseを検証できないため、cell判定を停止しました。",
    );
  }
  const records = await Promise.all(theoretical.map((candidate) => lookupIntegratedCellRecord(candidate.cellId)));
  const cells = theoretical
    .filter((_, index) => records[index]?.valid === true)
    .map((candidate) => ({ ...candidate, valid: true }));
  const rejectedTheoreticalCells = theoretical
    .filter((_, index) => records[index]?.valid !== true)
    .map((candidate) => candidate.cellId);
  const coveredWeight = cells.reduce((sum, cell) => sum + cell.weight, 0);
  const returnedTheoreticalWeight = theoretical.reduce((sum, cell) => sum + cell.weight, 0);
  const rejectedWeight = Math.max(0, returnedTheoreticalWeight - coveredWeight);
  const primaryWeight = cells[0]?.weight ?? 0;
  const coverageStatus = cells.length === 0
    ? "NO_VALID_CELL"
    : rejectedTheoreticalCells.length === 0 && coveredWeight >= 0.95
      ? "VALIDATED"
      : "PARTIAL";

  return {
    schemaVersion: "canonical-resolution/2.0",
    query: {
      address: geocoded.query,
      lat: roundNumber(geocoded.lat, 9),
      lon: roundNumber(geocoded.lon, 9),
    },
    matchedAddress: geocoded.matchedAddress,
    geocodeRoute: geocoded.routeId,
    sigmaM,
    consistency,
    edgeMarginM: roundNumber(edgeMarginM(geocoded.lat, geocoded.lon), 2),
    stability: resolutionStability(primaryWeight),
    isUniqueCell: primaryWeight >= 0.95,
    primaryCellId: cells[0]?.cellId ?? null,
    cells: cells.map((cell) => ({
      ...cell,
      weight: roundNumber(cell.weight, 6),
      centerDistanceM: roundNumber(cell.centerDistanceM, 2),
    })),
    rejectedTheoreticalCells,
    coverage: {
      status: coverageStatus,
      coveredWeight: roundNumber(coveredWeight, 6),
      returnedTheoreticalWeight: roundNumber(returnedTheoreticalWeight, 6),
      rejectedWeight: roundNumber(rejectedWeight, 6),
      omittedWeight: roundNumber(Math.max(0, 1 - returnedTheoreticalWeight), 6),
      note: coverageStatus === "VALIDATED"
        ? "候補セルをcanonical valid-cell台帳で確認しました。"
        : coverageStatus === "PARTIAL"
          ? "測位不確実性の一部が対象行政界外または未収録です。欠測を安全扱いしません。"
          : "canonical valid-cell台帳に一致しません。対象範囲外としてfail-closedにしました。",
    },
  };
}
