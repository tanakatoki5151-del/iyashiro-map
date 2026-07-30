import { NextRequest, NextResponse } from "next/server";
import { diagnoseLocation } from "@/app/lib/diagnose";
import { clamp, withinRoughScope } from "@/app/lib/geo";

export const dynamic = "force-dynamic";
export const maxDuration = 60;
type GridCell = {
  lat: number;
  lng: number;
  bounds: [[number, number], [number, number]];
  theory: { score: number; confidence: number; label: string };
  modern: { score: number; completeness: number; label: string };
  combined: { score: number; provisional: boolean; label: string };
};
const finiteParam = (params: URLSearchParams, name: string) => {
  const value = Number(params.get(name));
  return Number.isFinite(value) ? value : null;
};

async function mapWithConcurrency<T, R>(
  values: T[],
  concurrency: number,
  mapper: (value: T) => Promise<R>,
) {
  const results = new Array<R>(values.length);
  let cursor = 0;
  await Promise.all(
    Array.from({ length: Math.min(concurrency, values.length) }, async () => {
      while (cursor < values.length) {
        const index = cursor++;
        results[index] = await mapper(values[index]);
      }
    }),
  );
  return results;
}

export async function GET(request: NextRequest) {
  const p = request.nextUrl.searchParams;
  const west = finiteParam(p, "west");
  const south = finiteParam(p, "south");
  const east = finiteParam(p, "east");
  const north = finiteParam(p, "north");
  if (
    west === null ||
    south === null ||
    east === null ||
    north === null ||
    east <= west ||
    north <= south ||
    east - west > 0.25 ||
    north - south > 0.2
  ) {
    return NextResponse.json(
      {
        error: "invalid_bounds",
        message:
          "表示範囲が広すぎます。地図をズームしてから色分けしてください。",
      },
      { status: 400 },
    );
  }
  const columns = Math.round(clamp(Number(p.get("cols")) || 4, 2, 5));
  const rows = Math.round(clamp(Number(p.get("rows")) || 3, 2, 4));
  const width = (east - west) / columns;
  const height = (north - south) / rows;
  const points = Array.from({ length: columns * rows }, (_, index) => {
    const column = index % columns;
    const row = Math.floor(index / columns);
    const cellWest = west + column * width;
    const cellSouth = south + row * height;
    return {
      lat: cellSouth + height / 2,
      lng: cellWest + width / 2,
      bounds: [
        [cellSouth, cellWest],
        [cellSouth + height, cellWest + width],
      ] as [[number, number], [number, number]],
    };
  }).filter((point) => withinRoughScope(point.lat, point.lng));
  const settled = await mapWithConcurrency(points, 3, async (point) => {
    try {
      const result = await diagnoseLocation(point.lat, point.lng);
      return {
        ...point,
        theory: {
          score: result.theory.score,
          confidence: result.theory.internalConfidence,
          label: result.theory.label,
        },
        modern: {
          score: result.modern.score,
          completeness: result.modern.completeness,
          label: result.modern.label,
        },
        combined: {
          score: result.combined.score,
          provisional: result.combined.provisional,
          label: result.combined.label,
        },
      };
    } catch {
      return null;
    }
  });
  const cells: GridCell[] = settled.filter((cell) => cell !== null);
  return NextResponse.json(
    {
      generatedAt: new Date().toISOString(),
      resolution: { columns, rows },
      cells,
      note: "表示範囲を均等分割したオンデマンド概算です。住所診断は指定地点をより詳細に解析します。",
    },
    {
      headers: {
        "Cache-Control": "public, s-maxage=86400, stale-while-revalidate=604800",
        "Access-Control-Allow-Origin": "*",
      },
    },
  );
}
