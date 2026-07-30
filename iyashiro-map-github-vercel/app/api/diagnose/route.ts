import { NextRequest, NextResponse } from "next/server";
import { diagnoseLocation } from "@/app/lib/diagnose";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

const coordinate = (value: string | null) => {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

export async function GET(request: NextRequest) {
  const lat = coordinate(request.nextUrl.searchParams.get("lat"));
  const lng = coordinate(
    request.nextUrl.searchParams.get("lng") ??
      request.nextUrl.searchParams.get("lon"),
  );
  if (
    lat === null ||
    lng === null ||
    lat < -90 ||
    lat > 90 ||
    lng < -180 ||
    lng > 180
  ) {
    return NextResponse.json(
      {
        error: "invalid_coordinate",
        message: "lat と lng を数値で指定してください。",
      },
      { status: 400 },
    );
  }
  try {
    return NextResponse.json(await diagnoseLocation(lat, lng), {
      headers: {
        "Cache-Control": "public, s-maxage=86400, stale-while-revalidate=604800",
        "Access-Control-Allow-Origin": "*",
      },
    });
  } catch (error) {
    return NextResponse.json(
      error instanceof RangeError
        ? { error: "out_of_scope", message: error.message }
        : {
            error: "analysis_failed",
            message:
              "公式データの取得または解析に失敗しました。少し待って再試行してください。",
          },
      { status: error instanceof RangeError ? 422 : 502 },
    );
  }
}
