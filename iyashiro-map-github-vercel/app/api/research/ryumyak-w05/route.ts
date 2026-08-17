import { createHash } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

const MAX_CHUNK_BYTES = 256 * 1024;

const CANDIDATE_URLS: Record<string, string[]> = {
  "13": [
    "https://nlftp.mlit.go.jp/ksj/gml/data/W05/W05-08/W05-08_13_GML.zip",
    "https://nlftp.mlit.go.jp/ksj/gml/data/W05/W05-08/W05-08_13.zip",
  ],
  "14": [
    "https://nlftp.mlit.go.jp/ksj/gml/data/W05/W05-08/W05-08_14_GML.zip",
    "https://nlftp.mlit.go.jp/ksj/gml/data/W05/W05-08/W05-08_14.zip",
  ],
};

type CandidateProbe = {
  url: string;
  ok: boolean;
  status: number | null;
  contentType: string | null;
  contentLength: number | null;
  contentRange: string | null;
  firstHex: string | null;
  error: string | null;
};

function parseNonNegativeInteger(value: string | null, fallback: number): number {
  if (value === null || value.trim() === "") return fallback;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

function parsePositiveInteger(value: string | null, fallback: number): number {
  const parsed = parseNonNegativeInteger(value, fallback);
  return parsed > 0 ? parsed : fallback;
}

async function probeUrl(url: string): Promise<CandidateProbe> {
  try {
    const response = await fetch(url, {
      cache: "no-store",
      redirect: "follow",
      headers: { Range: "bytes=0-63", "User-Agent": "RYUMYAK-MEGA06R-R2/1.0" },
    });
    const bytes = new Uint8Array(await response.arrayBuffer());
    const contentRange = response.headers.get("content-range");
    const contentLengthHeader = response.headers.get("content-length");
    const totalFromRange = contentRange?.match(/\/(\d+)$/)?.[1];
    const contentLength = totalFromRange
      ? Number.parseInt(totalFromRange, 10)
      : contentLengthHeader
        ? Number.parseInt(contentLengthHeader, 10)
        : bytes.byteLength || null;

    return {
      url,
      ok: response.ok && bytes.byteLength > 0,
      status: response.status,
      contentType: response.headers.get("content-type"),
      contentLength: Number.isFinite(contentLength) ? contentLength : null,
      contentRange,
      firstHex: Buffer.from(bytes.slice(0, 16)).toString("hex"),
      error: response.ok ? null : `HTTP ${response.status}`,
    };
  } catch (error) {
    return {
      url,
      ok: false,
      status: null,
      contentType: null,
      contentLength: null,
      contentRange: null,
      firstHex: null,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

async function selectWorkingUrl(pref: string): Promise<CandidateProbe> {
  const candidates = CANDIDATE_URLS[pref] ?? [];
  const probes: CandidateProbe[] = [];
  for (const url of candidates) {
    const probe = await probeUrl(url);
    probes.push(probe);
    if (probe.ok) return probe;
  }
  throw new Error(`No working W05 URL for pref=${pref}: ${JSON.stringify(probes)}`);
}

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const pref = params.get("pref") ?? "13";
  const mode = params.get("mode") ?? "probe";

  if (!(pref in CANDIDATE_URLS)) {
    return NextResponse.json({ error: "pref must be 13 or 14" }, { status: 400 });
  }

  if (mode === "probe") {
    const results = await Promise.all(CANDIDATE_URLS[pref].map(probeUrl));
    return NextResponse.json({
      service: "RYUMYAK MEGA-06R R2 bounded W05 fetch proxy",
      pref,
      results,
      generatedAt: new Date().toISOString(),
    });
  }

  if (mode !== "chunk" && mode !== "digest") {
    return NextResponse.json({ error: "mode must be probe, chunk, or digest" }, { status: 400 });
  }

  try {
    const selected = await selectWorkingUrl(pref);
    const sourceUrl = selected.url;

    if (mode === "digest") {
      const response = await fetch(sourceUrl, {
        cache: "no-store",
        redirect: "follow",
        headers: { "User-Agent": "RYUMYAK-MEGA06R-R2/1.0" },
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const bytes = Buffer.from(await response.arrayBuffer());
      return NextResponse.json({
        pref,
        sourceUrl,
        bytes: bytes.length,
        sha256: createHash("sha256").update(bytes).digest("hex"),
        firstHex: bytes.subarray(0, 16).toString("hex"),
      });
    }

    const start = parseNonNegativeInteger(params.get("start"), 0);
    const requestedLength = Math.min(
      parsePositiveInteger(params.get("length"), MAX_CHUNK_BYTES),
      MAX_CHUNK_BYTES,
    );
    const end = start + requestedLength - 1;

    const response = await fetch(sourceUrl, {
      cache: "no-store",
      redirect: "follow",
      headers: {
        Range: `bytes=${start}-${end}`,
        "User-Agent": "RYUMYAK-MEGA06R-R2/1.0",
      },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const fetched = Buffer.from(await response.arrayBuffer());
    const chunk = response.status === 206
      ? fetched
      : fetched.subarray(start, Math.min(start + requestedLength, fetched.length));
    const contentRange = response.headers.get("content-range");
    const totalFromRange = contentRange?.match(/\/(\d+)$/)?.[1];
    const totalBytes = totalFromRange
      ? Number.parseInt(totalFromRange, 10)
      : selected.contentLength ?? (response.status === 200 ? fetched.length : null);

    return NextResponse.json({
      pref,
      sourceUrl,
      start,
      requestedLength,
      returnedLength: chunk.length,
      totalBytes,
      upstreamStatus: response.status,
      contentRange,
      sha256: createHash("sha256").update(chunk).digest("hex"),
      base64: chunk.toString("base64"),
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : String(error) },
      { status: 502 },
    );
  }
}
