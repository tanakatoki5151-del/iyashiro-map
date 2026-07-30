import { NextRequest, NextResponse } from "next/server";
import { isAddressLabelInScope } from "@/app/lib/geo";

export const dynamic = "force-dynamic";
type GsiFeature = {
  geometry?: { coordinates?: [number, number] };
  properties?: { title?: string };
};

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams.get("q")?.trim() ?? "";
  if (query.length < 2 || query.length > 120) {
    return NextResponse.json(
      { error: "invalid_query", message: "住所を2文字以上で入力してください。" },
      { status: 400 },
    );
  }
  try {
    const endpoint = new URL(
      "https://msearch.gsi.go.jp/address-search/AddressSearch",
    );
    endpoint.searchParams.set("q", query);
    const response = await fetch(endpoint, {
      headers: { accept: "application/geo+json,application/json" },
    });
    if (!response.ok) throw new Error(String(response.status));
    const features = (await response.json()) as GsiFeature[];
    const candidates = features
      .map((feature) => ({
        label: feature.properties?.title ?? "",
        lng: Number(feature.geometry?.coordinates?.[0]),
        lat: Number(feature.geometry?.coordinates?.[1]),
      }))
      .filter(
        (candidate) =>
          candidate.label &&
          Number.isFinite(candidate.lat) &&
          Number.isFinite(candidate.lng) &&
          isAddressLabelInScope(candidate.label),
      )
      .slice(0, 5);
    return NextResponse.json(
      { query, candidates },
      {
        headers: {
          "Cache-Control": "public, s-maxage=86400, stale-while-revalidate=604800",
          "Access-Control-Allow-Origin": "*",
        },
      },
    );
  } catch {
    return NextResponse.json(
      {
        error: "geocoder_failed",
        message: "住所検索サービスに接続できませんでした。",
      },
      { status: 502 },
    );
  }
}
