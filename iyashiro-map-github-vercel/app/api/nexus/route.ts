import { NextRequest, NextResponse } from "next/server";
import { assessNexusProperty, type NexusCurrentness, type NexusIdentity, type NexusPolicyInput } from "@/app/lib/nexus/policy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function optionalNumber(value: unknown, field: string): number | null {
  if (value === undefined || value === null || value === "") return null;
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) throw new TypeError(`${field} は数値で指定してください。`);
  return parsed;
}

function currentness(value: unknown): NexusCurrentness {
  return value === "confirmed" || value === "stale" ? value : "unknown";
}

function identity(value: unknown): NexusIdentity {
  return value === "exact" || value === "partial" ? value : "unknown";
}

function cleanText(value: unknown, maxLength = 300) {
  if (typeof value !== "string") return null;
  const cleaned = value.trim();
  if (!cleaned) return null;
  if (cleaned.length > maxLength) throw new TypeError(`文字数は${maxLength}文字以内にしてください。`);
  return cleaned;
}

function fromSearchParams(request: NextRequest): NexusPolicyInput {
  const params = request.nextUrl.searchParams;
  return {
    propertyName: cleanText(params.get("name"), 120),
    address: cleanText(params.get("address"), 160),
    sourceUrl: cleanText(params.get("url"), 500),
    totalMonthlyFixedJPY: optionalNumber(params.get("total"), "total"),
    areaSquareMeters: optionalNumber(params.get("area"), "area"),
    floor: optionalNumber(params.get("floor"), "floor"),
    currentness: currentness(params.get("currentness")),
    identity: identity(params.get("identity")),
  };
}

function fromBody(body: Record<string, unknown>): NexusPolicyInput {
  return {
    propertyName: cleanText(body.propertyName, 120),
    address: cleanText(body.address, 160),
    sourceUrl: cleanText(body.sourceUrl, 500),
    totalMonthlyFixedJPY: optionalNumber(body.totalMonthlyFixedJPY, "totalMonthlyFixedJPY"),
    areaSquareMeters: optionalNumber(body.areaSquareMeters, "areaSquareMeters"),
    floor: optionalNumber(body.floor, "floor"),
    currentness: currentness(body.currentness),
    identity: identity(body.identity),
  };
}

function response(input: NexusPolicyInput) {
  return NextResponse.json(assessNexusProperty(input), {
    headers: {
      "Cache-Control": "no-store",
      "Access-Control-Allow-Origin": "*",
    },
  });
}

export async function GET(request: NextRequest) {
  try {
    return response(fromSearchParams(request));
  } catch (error) {
    return NextResponse.json(
      { error: "invalid_input", message: error instanceof Error ? error.message : "入力を確認してください。" },
      { status: 400 },
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as Record<string, unknown>;
    return response(fromBody(body));
  } catch (error) {
    return NextResponse.json(
      { error: "invalid_input", message: error instanceof Error ? error.message : "JSON入力を確認してください。" },
      { status: 400 },
    );
  }
}
