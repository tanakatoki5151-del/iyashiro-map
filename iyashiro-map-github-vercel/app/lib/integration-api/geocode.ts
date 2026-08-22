import { addressEvidenceIsConsistent, hasPointAddressPrecision } from "./address-evidence";
import { isAddressLabelInScope } from "../geo";
import { ApiError } from "./errors";
import { GEOCODE_SIGMA_M, type GeocodeRouteId } from "./grid";
import { optionalString } from "./validation";

type GsiFeature = {
  geometry?: { coordinates?: [number, number] };
  properties?: { title?: string };
};

export interface GeocodedPoint {
  query: string;
  matchedAddress: string;
  lat: number;
  lon: number;
  routeId: GeocodeRouteId;
  sigmaM: number;
}

async function readJsonLimited(response: Response, maximumBytes: number): Promise<unknown> {
  const declared = Number(response.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > maximumBytes) {
    throw new ApiError(502, "geocoder_response_too_large", "住所検索の応答が上限を超えました。");
  }
  if (!response.body) return response.json();
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      received += value.byteLength;
      if (received > maximumBytes) {
        throw new ApiError(502, "geocoder_response_too_large", "住所検索の応答が上限を超えました。");
      }
      chunks.push(value);
    }
  } finally {
    await reader.cancel().catch(() => undefined);
  }
  const joined = new Uint8Array(received);
  let offset = 0;
  for (const chunk of chunks) {
    joined.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    return JSON.parse(new TextDecoder().decode(joined)) as unknown;
  } catch {
    throw new ApiError(502, "geocoder_invalid_response", "住所検索の応答を解釈できませんでした。");
  }
}

export async function geocodeAddress(
  value: unknown,
  routeId: GeocodeRouteId = "GSI_JUKYO_BASE_NUMBER",
): Promise<GeocodedPoint> {
  const query = optionalString(value, 120);
  if (!query || query.length < 2) {
    throw new ApiError(400, "invalid_address", "住所は2〜120文字で指定してください。");
  }
  if (!hasPointAddressPrecision(query)) {
    throw new ApiError(
      422,
      "address_precision_insufficient",
      "100mセル判定には丁目・番地等まで含む住所が必要です。",
    );
  }
  const endpoint = new URL("https://msearch.gsi.go.jp/address-search/AddressSearch");
  endpoint.searchParams.set("q", query);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5_000);
  try {
    const response = await fetch(endpoint, {
      signal: controller.signal,
      cache: "no-store",
      headers: { accept: "application/geo+json,application/json" },
    });
    if (!response.ok) {
      throw new ApiError(502, "geocoder_failed", "住所検索に失敗しました（HTTP " + response.status + "）。");
    }
    const payload = await readJsonLimited(response, 256 * 1024);
    if (!Array.isArray(payload)) {
      throw new ApiError(502, "geocoder_invalid_response", "住所検索の応答形式が不正です。");
    }
    const candidates = (payload as GsiFeature[])
      .map((feature) => ({
        label: typeof feature.properties?.title === "string" ? feature.properties.title.trim() : "",
        lon: Number(feature.geometry?.coordinates?.[0]),
        lat: Number(feature.geometry?.coordinates?.[1]),
      }))
      .filter((candidate) =>
        candidate.label.length > 0 &&
        Number.isFinite(candidate.lat) &&
        Number.isFinite(candidate.lon) &&
        isAddressLabelInScope(candidate.label),
      );
    if (!candidates.length) {
      throw new ApiError(
        404,
        "address_not_found",
        "東京23区・横浜市・川崎市に一致する住所が見つかりませんでした。",
      );
    }
    const match = candidates.find((candidate) =>
      addressEvidenceIsConsistent(query, candidate.label),
    );
    if (!match) {
      throw new ApiError(
        422,
        "address_match_inconsistent",
        "住所検索結果の粒度または住所成分が入力と一致しないため判定を停止しました。",
      );
    }
    return {
      query,
      matchedAddress: match.label,
      lat: match.lat,
      lon: match.lon,
      routeId,
      sigmaM: GEOCODE_SIGMA_M[routeId],
    };
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof Error && error.name === "AbortError") {
      throw new ApiError(504, "geocoder_timeout", "住所検索が時間切れになりました。");
    }
    throw new ApiError(502, "geocoder_failed", "住所検索サービスに接続できませんでした。");
  } finally {
    clearTimeout(timeout);
  }
}
