import { NextRequest, NextResponse } from "next/server";
import { diagnoseLocation } from "@/app/lib/diagnose";
import { isAddressLabelInScope } from "@/app/lib/geo";

export const dynamic = "force-dynamic";
export const maxDuration = 60;
type GsiFeature = {
  geometry?: { coordinates?: [number, number] };
  properties?: { title?: string };
};

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams.get("q")?.trim() ?? "";
  if (query.length < 2 || query.length > 120) {
    return NextResponse.json(
      { error: "invalid_query", message: "q に住所を指定してください。" },
      { status: 400 },
    );
  }
  try {
    const endpoint = new URL(
      "https://msearch.gsi.go.jp/address-search/AddressSearch",
    );
    endpoint.searchParams.set("q", query);
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
    if (!match) {
      return NextResponse.json(
        {
          error: "not_found",
          message:
            "東京23区・横浜市・川崎市に一致する住所が見つかりませんでした。",
        },
        { status: 404 },
      );
    }
    const diagnosis = await diagnoseLocation(match.lat, match.lng);
    return NextResponse.json(
      { query, matchedAddress: match.label, ...diagnosis },
      {
        headers: {
          "Cache-Control": "public, s-maxage=86400, stale-while-revalidate=604800",
          "Access-Control-Allow-Origin": "*",
        },
      },
    );
  } catch (error) {
    return NextResponse.json(
      error instanceof RangeError
        ? { error: "out_of_scope", message: error.message }
        : {
            error: "lookup_failed",
            message: "住所の検索または解析に失敗しました。",
          },
      { status: error instanceof RangeError ? 422 : 502 },
    );
  }
}
