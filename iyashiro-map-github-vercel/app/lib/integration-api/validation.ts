import { ApiError } from "./errors";
import { classifyOptionalNumericInput } from "./normalization";
import { classifyRequestOrigin } from "./origin-safety.mjs";

export function enforceJsonRequestBoundary(request: Request): void {
  const mediaType = (request.headers.get("content-type") ?? "").split(";", 1)[0].trim().toLowerCase();
  if (!/^application\/(?:json|[a-z0-9.+-]+\+json)$/.test(mediaType)) {
    throw new ApiError(415, "json_content_type_required", "Content-Type: application/json が必要です。");
  }
  if (request.headers.get("sec-fetch-site") === "cross-site") {
    throw new ApiError(403, "cross_site_request_rejected", "cross-site POSTは受け付けません。");
  }
  const origin = request.headers.get("origin");
  if (origin !== null) {
    const originStatus = classifyRequestOrigin({
      origin,
      requestUrl: request.url,
      host: request.headers.get("host"),
      forwardedHost: request.headers.get("x-forwarded-host"),
      forwardedProto: request.headers.get("x-forwarded-proto"),
      vercel: process.env.VERCEL ?? null,
    });
    if (originStatus === "invalid") {
      throw new ApiError(403, "invalid_origin", "Origin headerが不正です。");
    }
    if (originStatus !== "allowed") {
      throw new ApiError(403, "cross_origin_request_rejected", "same-origin POSTだけを受け付けます。");
    }
  }
}

export async function readJsonBody(
  request: Request,
  maximumBytes = 64 * 1024,
): Promise<unknown> {
  enforceJsonRequestBoundary(request);
  const declared = Number(request.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > maximumBytes) {
    throw new ApiError(413, "payload_too_large", `入力は${maximumBytes} bytes以下にしてください。`);
  }
  if (!request.body) throw new ApiError(400, "invalid_json", "JSON本文が必要です。");
  const reader = request.body.getReader();
  const decoder = new TextDecoder();
  let received = 0;
  let text = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      received += value.byteLength;
      if (received > maximumBytes) {
        throw new ApiError(413, "payload_too_large", `入力は${maximumBytes} bytes以下にしてください。`);
      }
      text += decoder.decode(value, { stream: true });
    }
    text += decoder.decode();
  } finally {
    await reader.cancel().catch(() => undefined);
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new ApiError(400, "invalid_json", "JSONの形式を確認してください。");
  }
}

export function objectValue(value: unknown, field = "body"): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ApiError(400, "invalid_input", `${field} はJSON objectで指定してください。`);
  }
  return value as Record<string, unknown>;
}

export function optionalString(value: unknown, maximumLength: number): string | null {
  if (value === undefined || value === null || value === "") return null;
  if (typeof value !== "string") throw new ApiError(400, "invalid_input", "文字列項目の形式が不正です。");
  const normalized = value.trim();
  if (!normalized) return null;
  if (normalized.length > maximumLength) {
    throw new ApiError(400, "invalid_input", `文字列は${maximumLength}文字以下にしてください。`);
  }
  return normalized;
}

export function optionalFiniteNumber(
  value: unknown,
  options: { minimum?: number; maximum?: number } = {},
): number | null {
  const parsed = classifyOptionalNumericInput(value);
  if (parsed.kind === "missing") return null;
  if (parsed.kind === "invalid") {
    const message = parsed.reason === "type"
      ? "数値項目はnumberまたはnumeric stringで指定してください。"
      : parsed.reason === "blank"
        ? "空白だけの数値項目は指定できません。"
        : "数値項目の形式が不正です。";
    throw new ApiError(400, "invalid_input", message);
  }
  const number = parsed.value;
  if (options.minimum !== undefined && number < options.minimum) {
    throw new ApiError(400, "invalid_input", `${options.minimum}以上で指定してください。`);
  }
  if (options.maximum !== undefined && number > options.maximum) {
    throw new ApiError(400, "invalid_input", `${options.maximum}以下で指定してください。`);
  }
  return number;
}

export function finiteCoordinate(latValue: unknown, lonValue: unknown): { lat: number; lon: number } | null {
  const lat = optionalFiniteNumber(latValue, { minimum: -90, maximum: 90 });
  const lon = optionalFiniteNumber(lonValue, { minimum: -180, maximum: 180 });
  if (lat === null && lon === null) return null;
  if (lat === null || lon === null) {
    throw new ApiError(400, "invalid_coordinate", "lat と lon は両方指定してください。");
  }
  return { lat, lon };
}

export function roundNumber(value: number, digits = 6): number {
  const scale = 10 ** digits;
  return Math.round(value * scale) / scale;
}
