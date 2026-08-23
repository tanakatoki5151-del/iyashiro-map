import { ApiError, errorResponse } from "@/app/lib/integration-api/errors";
import { buildLandDossier } from "@/app/lib/integration-api/dossier";
import type { LandDossier } from "@/app/lib/land-dossier-types";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 60;

function trimmed(value: string | null): string | null {
  const normalized = value?.trim() ?? "";
  return normalized || null;
}

function coordinate(value: string, name: "lat" | "lng"): number {
  const parsed = Number(value);
  const minimum = name === "lat" ? -90 : -180;
  const maximum = name === "lat" ? 90 : 180;
  if (!Number.isFinite(parsed) || parsed < minimum || parsed > maximum) {
    throw new ApiError(
      400,
      "invalid_coordinates",
      `${name} は ${minimum}〜${maximum} の有限な数値で指定してください。`,
    );
  }
  return parsed;
}

function publicPointer(pointer: string | null): string | null {
  if (!pointer) return null;
  try {
    const url = new URL(pointer);
    return url.protocol === "https:" || url.protocol === "http:" ? pointer : null;
  } catch {
    return null;
  }
}

function toPublicDossier(dossier: LandDossier): LandDossier {
  const result: LandDossier = {
    ...dossier,
    sources: dossier.sources.map((source) => ({
      ...source,
      pointer: publicPointer(source.pointer),
    })),
  };
  delete result.rawEvidence;
  return result;
}

export async function GET(request: Request) {
  try {
    const searchParams = new URL(request.url).searchParams;
    const rawLat = trimmed(searchParams.get("lat"));
    const rawLng = trimmed(searchParams.get("lng")) ?? trimmed(searchParams.get("lon"));
    const address = trimmed(searchParams.get("q")) ?? trimmed(searchParams.get("address"));
    const labelHint = trimmed(searchParams.get("label"));
    const hasCoordinateParameter = rawLat !== null || rawLng !== null;

    if (hasCoordinateParameter) {
      if (rawLat === null || rawLng === null) {
        throw new ApiError(
          400,
          "invalid_coordinates",
          "座標で調べる場合は lat と lng（または lon）を両方指定してください。",
        );
      }
      return Response.json(
        toPublicDossier(await buildLandDossier({
          lat: coordinate(rawLat, "lat"),
          lng: coordinate(rawLng, "lng"),
          labelHint: labelHint ?? address ?? undefined,
        })),
        { headers: { "Cache-Control": "no-store" } },
      );
    }

    if (!address) {
      throw new ApiError(
        400,
        "location_required",
        "lat/lng（またはlat/lon）、q、address のいずれかで地点を指定してください。",
      );
    }

    return Response.json(
      toPublicDossier(await buildLandDossier({
        address,
        labelHint: labelHint ?? undefined,
      })),
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    return errorResponse(error);
  }
}
