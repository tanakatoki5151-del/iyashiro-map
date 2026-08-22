import { createHmac, timingSafeEqual } from "node:crypto";

const TOKEN_PREFIX = "ct1";
export const COMPARISON_TOKEN_TTL_MS = 24 * 60 * 60 * 1_000;
export const MAX_COMPARISON_TOKEN_PAYLOAD_BYTES = 24 * 1024;
export const MAX_COMPARISON_TOKEN_WIRE_BYTES =
  TOKEN_PREFIX.length + 1 + 4 * Math.ceil(MAX_COMPARISON_TOKEN_PAYLOAD_BYTES / 3) + 1 + 64;

export type ComparisonTokenDecodeResult =
  | { ok: true; payload: unknown }
  | { ok: false; reason: "format" | "size" | "signature" | "payload" | "secret" };

function signature(value: string, secret: string): string {
  return createHmac("sha256", secret).update(value).digest("hex");
}

export function comparisonTokenWindowIsValid(
  issuedMs: number,
  expiresMs: number,
  nowMs = Date.now(),
): boolean {
  return Number.isFinite(issuedMs) &&
    Number.isFinite(expiresMs) &&
    issuedMs <= nowMs + 5 * 60 * 1_000 &&
    expiresMs > nowMs &&
    expiresMs > issuedMs &&
    expiresMs - issuedMs <= COMPARISON_TOKEN_TTL_MS;
}

export function encodeComparisonToken(payload: unknown, secret: string): string {
  if (secret.trim().length < 32) throw new RangeError("comparison_token_secret_too_short");
  const json = JSON.stringify(payload);
  const bytes = Buffer.byteLength(json, "utf8");
  if (bytes > MAX_COMPARISON_TOKEN_PAYLOAD_BYTES) {
    throw new RangeError("comparison_token_payload_too_large");
  }
  const body = Buffer.from(json, "utf8").toString("base64url");
  const signed = `${TOKEN_PREFIX}.${body}`;
  return `${signed}.${signature(signed, secret)}`;
}

export function decodeComparisonToken(
  token: string,
  secret: string,
): ComparisonTokenDecodeResult {
  if (secret.trim().length < 32) return { ok: false, reason: "secret" };
  if (token.length > MAX_COMPARISON_TOKEN_WIRE_BYTES) return { ok: false, reason: "size" };
  const parts = token.split(".");
  if (parts.length !== 3 || parts[0] !== TOKEN_PREFIX || !/^[A-Za-z0-9_-]+$/.test(parts[1]) || !/^[a-f0-9]{64}$/i.test(parts[2])) {
    return { ok: false, reason: "format" };
  }
  const expected = Buffer.from(signature(`${parts[0]}.${parts[1]}`, secret), "hex");
  const received = Buffer.from(parts[2], "hex");
  if (received.length !== expected.length || !timingSafeEqual(received, expected)) {
    return { ok: false, reason: "signature" };
  }
  try {
    const decoded = Buffer.from(parts[1], "base64url");
    if (decoded.length > MAX_COMPARISON_TOKEN_PAYLOAD_BYTES || decoded.toString("base64url") !== parts[1]) {
      return { ok: false, reason: "size" };
    }
    return { ok: true, payload: JSON.parse(decoded.toString("utf8")) as unknown };
  } catch {
    return { ok: false, reason: "payload" };
  }
}
