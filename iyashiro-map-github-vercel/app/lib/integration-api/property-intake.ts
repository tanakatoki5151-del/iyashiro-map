import { lookup } from "node:dns/promises";
import { isIP } from "node:net";
import { ApiError } from "./errors";
import { isPrivateOrLocalAddress } from "./network-safety";
import { containsReflectedUrlSecret } from "./listing-url-safety";
import { objectValue, optionalFiniteNumber, optionalString } from "./validation";

export const SUPPORTED_PROPERTY_HOSTS = [
  "suumo.jp",
  "www.homes.co.jp",
  "homes.co.jp",
  "www.athome.co.jp",
  "athome.co.jp",
  "www.chintai.net",
  "chintai.net",
  "realestate.yahoo.co.jp",
  "www.housecom.jp",
  "housecom.jp",
  "www.housemate-navi.jp",
  "housemate-navi.jp",
  "www.goodrooms.jp",
  "goodrooms.jp",
] as const;

const SUPPORTED_HOST_SET = new Set<string>(SUPPORTED_PROPERTY_HOSTS);
const MAXIMUM_URL_LENGTH = 2_048;
const MAXIMUM_HTML_BYTES = 1_250_000;
const FETCH_TIMEOUT_MS = 8_000;
const MAXIMUM_REDIRECTS = 3;

export interface PropertyFields {
  name: string | null;
  address: string | null;
  station: string | null;
  areaM2: number | null;
  layout: string | null;
  memo: string | null;
}

export interface PropertyIntakeResult extends PropertyFields {
  schemaVersion: "property-intake/3.0";
  source: "url" | "manual";
  url: string | null;
  site: string | null;
  snapshot: {
    requestedUrl: string | null;
    finalUrl: string | null;
    fetchedAt: string | null;
  };
  provenance: {
    extracted: Omit<PropertyFields, "memo"> | null;
    manualOverrides: PropertyFields;
  };
  extraction: {
    status: "extracted" | "manual_only" | "manual_required" | "blocked" | "fetch_failed";
    supportedHost: boolean;
    method: string;
    pageTitle: string | null;
    warnings: string[];
  };
}

function numeric(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "string") return null;
  const normalized = value.replace(/[,，]/g, "").trim();
  if (!normalized) return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function decodeHtml(value: string): string {
  return value
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">");
}

function cleanVisibleText(html: string): string {
  return decodeHtml(
    html
      .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
      .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " "),
  ).trim().slice(0, 160_000);
}

function metaContent(html: string, key: string): string | null {
  const escaped = key.replace(/[.*+?^$()|[\]{}\\]/g, "\\$&");
  const patterns = [
    new RegExp(`<meta[^>]+(?:property|name)=["']${escaped}["'][^>]+content=["']([^"']*)["'][^>]*>`, "i"),
    new RegExp(`<meta[^>]+content=["']([^"']*)["'][^>]+(?:property|name)=["']${escaped}["'][^>]*>`, "i"),
  ];
  for (const pattern of patterns) {
    const found = pattern.exec(html)?.[1];
    if (found) return decodeHtml(found).trim().slice(0, 500) || null;
  }
  return null;
}

function titleFromHtml(html: string): string | null {
  const title = metaContent(html, "og:title") ??
    decodeHtml(/<title[^>]*>([\s\S]*?)<\/title>/i.exec(html)?.[1] ?? "").trim();
  return title ? title.slice(0, 300) : null;
}

function jsonLdObjects(html: string): unknown[] {
  const values: unknown[] = [];
  const expression = /<script[^>]+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
  for (const match of html.matchAll(expression)) {
    if (values.length >= 100) break;
    try {
      const parsed = JSON.parse(decodeHtml(match[1]).trim()) as unknown;
      if (Array.isArray(parsed)) values.push(...parsed.slice(0, 100 - values.length));
      else values.push(parsed);
    } catch {
      // Broken JSON-LD is common. Bounded page-text extraction remains available.
    }
  }
  return values;
}

function firstStructuredValue(values: unknown[], keys: string[]): unknown {
  const wanted = new Set(keys);
  const queue = [...values];
  let visited = 0;
  while (queue.length && visited < 5_000) {
    const value = queue.shift();
    visited += 1;
    if (!value || typeof value !== "object") continue;
    if (Array.isArray(value)) {
      queue.push(...value.slice(0, 100));
      continue;
    }
    for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
      if (wanted.has(key) && nested !== null && nested !== "") return nested;
      if (nested && typeof nested === "object") queue.push(nested);
    }
  }
  return null;
}

function structuredAddress(values: unknown[]): string | null {
  const value = firstStructuredValue(values, ["address"]);
  if (typeof value === "string") return value.trim().slice(0, 160) || null;
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const result = ["addressRegion", "addressLocality", "streetAddress"]
    .map((key) => typeof record[key] === "string" ? record[key].trim() : "")
    .filter(Boolean)
    .join("");
  return result.slice(0, 160) || null;
}

function addressFromText(value: string): string | null {
  const matches = value.match(/(?:東京都|神奈川県)(?:[^\s,，。・|｜<>]{1,14}(?:区|市))[^\s,，。|｜<>]{1,48}/g);
  return matches?.sort((a, b) => b.length - a.length)[0]?.trim().slice(0, 160) ?? null;
}

function extractListing(html: string) {
  const structured = jsonLdObjects(html);
  const pageTitle = titleFromHtml(html);
  const description = metaContent(html, "og:description") ?? metaContent(html, "description");
  const visible = cleanVisibleText(html);
  const combined = `${pageTitle ?? ""} ${description ?? ""} ${visible}`;
  const nameValue = firstStructuredValue(structured, ["name", "headline"]);
  const address = structuredAddress(structured) ?? addressFromText(combined);
  const areaValue = firstStructuredValue(structured, ["floorSize", "area"]);
  const areaM2 = typeof areaValue === "object" && areaValue !== null
    ? numeric((areaValue as Record<string, unknown>).value)
    : numeric(areaValue) ?? numeric(/([0-9]+(?:\.[0-9]+)?)\s*(?:㎡|m2|m²)/i.exec(combined)?.[1] ?? null);
  const layout = /(?:間取り|layout)[^0-9A-Za-z]{0,8}([1-9][SLDKR＋+]{1,6})/i.exec(combined)?.[1] ?? null;
  const station = /([^\s,，。|｜<>]{1,24}(?:駅))\s*(?:徒歩|歩いて?)\s*([0-9]{1,2})\s*分/.exec(combined);
  return {
    pageTitle,
    name: typeof nameValue === "string" ? nameValue.trim().slice(0, 200) : pageTitle,
    address,
    station: station ? `${station[1]} 徒歩${station[2]}分` : null,
    areaM2,
    layout,
    method: address && structuredAddress(structured) ? "json_ld_and_page_text" : "page_text_fallback",
  };
}

function validateListingUrl(value: string): { url: URL; supported: boolean; reason: string | null } {
  if (value.length > MAXIMUM_URL_LENGTH) throw new ApiError(400, "url_too_long", "URLは2048文字以下にしてください。");
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new ApiError(400, "invalid_url", "物件URLの形式を確認してください。");
  }
  if (containsReflectedUrlSecret(url)) {
    throw new ApiError(400, "url_secret_not_allowed", "認証情報またはfragmentを含むURLは保存・取得しません。");
  }
  if (url.protocol !== "https:") {
    return { url, supported: false, reason: "HTTPSの物件ページだけを自動取得します。住所は手入力できます。" };
  }
  if (url.port && url.port !== "443") {
    return { url, supported: false, reason: "非標準portを含むURLは取得しません。" };
  }
  const host = url.hostname.toLowerCase().replace(/\.$/, "");
  if (host === "localhost" || isIP(host) !== 0 || !SUPPORTED_HOST_SET.has(host)) {
    return { url, supported: false, reason: "許可リスト外の掲載サイトです。URLを保持し、住所を手入力してください。" };
  }
  url.hash = "";
  return { url, supported: true, reason: null };
}

async function assertPublicDns(hostname: string, signal: AbortSignal): Promise<void> {
  let onAbort: (() => void) | null = null;
  const aborted = new Promise<never>((_resolve, reject) => {
    onAbort = () => {
      const error = new Error("listing_timeout");
      error.name = "AbortError";
      reject(error);
    };
    if (signal.aborted) onAbort();
    else signal.addEventListener("abort", onAbort, { once: true });
  });
  let addresses: Array<{ address: string; family: number }>;
  try {
    addresses = await Promise.race([lookup(hostname, { all: true, verbatim: true }), aborted]);
  } finally {
    if (onAbort) signal.removeEventListener("abort", onAbort);
  }
  if (!addresses.length || addresses.some((item) => isPrivateOrLocalAddress(item.address))) {
    throw new Error("listing_dns_not_public");
  }
}

async function readTextLimited(response: Response): Promise<string> {
  const declared = Number(response.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > MAXIMUM_HTML_BYTES) throw new Error("listing_response_too_large");
  if (!response.body) return (await response.text()).slice(0, MAXIMUM_HTML_BYTES);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let received = 0;
  let output = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      received += value.byteLength;
      if (received > MAXIMUM_HTML_BYTES) throw new Error("listing_response_too_large");
      output += decoder.decode(value, { stream: true });
    }
    output += decoder.decode();
    return output;
  } finally {
    await reader.cancel().catch(() => undefined);
  }
}

async function fetchAllowedListing(startUrl: URL, signal: AbortSignal): Promise<{ html: string; finalUrl: URL }> {
  let current = startUrl;
  for (let redirects = 0; redirects <= MAXIMUM_REDIRECTS; redirects += 1) {
    await assertPublicDns(current.hostname, signal);
    const response = await fetch(current, {
      signal,
      redirect: "manual",
      cache: "no-store",
      credentials: "omit",
      referrerPolicy: "no-referrer",
      headers: {
        accept: "text/html,application/xhtml+xml",
        "user-agent": "Mozilla/5.0 (compatible; IyashiroPropertyIntake/3.0; user-initiated)",
      },
    });
    if (response.status >= 300 && response.status < 400) {
      const location = response.headers.get("location");
      await response.body?.cancel().catch(() => undefined);
      if (!location) throw new Error("listing_redirect_without_location");
      const checked = validateListingUrl(new URL(location, current).toString());
      if (!checked.supported) throw new Error("listing_redirect_not_allowed");
      current = checked.url;
      continue;
    }
    if (!response.ok) throw new Error(`listing_http_${response.status}`);
    const contentType = (response.headers.get("content-type") ?? "").toLowerCase();
    if (!contentType.includes("text/html") && !contentType.includes("application/xhtml+xml")) {
      await response.body?.cancel().catch(() => undefined);
      throw new Error("listing_not_html");
    }
    return { html: await readTextLimited(response), finalUrl: current };
  }
  throw new Error("listing_redirect_limit");
}

function manualFields(value: unknown): PropertyFields {
  const record = value === undefined || value === null ? {} : objectValue(value, "manual");
  return {
    name: optionalString(record.name ?? record.buildingName, 200),
    address: optionalString(record.address, 160),
    station: optionalString(record.station, 120),
    areaM2: optionalFiniteNumber(record.areaM2 ?? record.areaSqm, { minimum: 1, maximum: 10_000 }),
    layout: optionalString(record.layout, 40),
    memo: optionalString(record.memo, 1_000),
  };
}

function propertyProvenance(
  manual: PropertyFields,
  extracted: ReturnType<typeof extractListing> | null = null,
): PropertyIntakeResult["provenance"] {
  return {
    extracted: extracted
      ? {
          name: extracted.name,
          address: extracted.address,
          station: extracted.station,
          areaM2: extracted.areaM2,
          layout: extracted.layout,
        }
      : null,
    manualOverrides: { ...manual },
  };
}

export async function intakeProperty(value: unknown): Promise<PropertyIntakeResult> {
  const body = objectValue(value);
  const manual = manualFields(body.manual ?? body);
  const urlValue = optionalString(body.propertyUrl ?? body.url, MAXIMUM_URL_LENGTH);
  if (!urlValue) {
    return {
      schemaVersion: "property-intake/3.0",
      source: "manual",
      url: null,
      site: null,
      ...manual,
      snapshot: { requestedUrl: null, finalUrl: null, fetchedAt: null },
      provenance: propertyProvenance(manual),
      extraction: {
        status: "manual_only",
        supportedHost: false,
        method: "manual",
        pageTitle: null,
        warnings: ["手入力値です。募集元・現地・重要事項説明で確認してください。"],
      },
    };
  }

  const checked = validateListingUrl(urlValue);
  if (!checked.supported) {
    return {
      schemaVersion: "property-intake/3.0",
      source: "url",
      url: checked.url.toString(),
      site: checked.url.hostname,
      ...manual,
      snapshot: { requestedUrl: urlValue, finalUrl: null, fetchedAt: null },
      provenance: propertyProvenance(manual),
      extraction: {
        status: "blocked",
        supportedHost: false,
        method: "manual_fallback",
        pageTitle: null,
        warnings: [checked.reason ?? "安全制限により自動取得しません。", "住所と物件条件を手入力してください。"],
      },
    };
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const { html, finalUrl } = await fetchAllowedListing(checked.url, controller.signal);
    const extracted = extractListing(html);
    const fetchedAt = new Date().toISOString();
    const address = manual.address ?? extracted.address;
    return {
      schemaVersion: "property-intake/3.0",
      source: "url",
      url: checked.url.toString(),
      site: finalUrl.hostname,
      name: manual.name ?? extracted.name,
      address,
      station: manual.station ?? extracted.station,
      areaM2: manual.areaM2 ?? extracted.areaM2,
      layout: manual.layout ?? extracted.layout,
      memo: manual.memo,
      snapshot: {
        requestedUrl: urlValue,
        finalUrl: finalUrl.toString(),
        fetchedAt,
      },
      provenance: propertyProvenance(manual, extracted),
      extraction: {
        status: address ? "extracted" : "manual_required",
        supportedHost: true,
        method: extracted.method,
        pageTitle: extracted.pageTitle,
        warnings: [
          ...(!address ? ["住所を自動抽出できませんでした。住所を手入力してください。"] : []),
          "掲載情報は更新・重複・募集終了があり得ます。募集元へ確認してください。",
        ],
      },
    };
  } catch (error) {
    return {
      schemaVersion: "property-intake/3.0",
      source: "url",
      url: checked.url.toString(),
      site: checked.url.hostname,
      ...manual,
      snapshot: { requestedUrl: urlValue, finalUrl: null, fetchedAt: null },
      provenance: propertyProvenance(manual),
      extraction: {
        status: "fetch_failed",
        supportedHost: true,
        method: "manual_fallback",
        pageTitle: null,
        warnings: [
          error instanceof Error && error.name === "AbortError"
            ? "掲載ページの取得が時間切れになりました。"
            : "掲載サイトの取得制限または安全制限により自動抽出できませんでした。",
          "住所と物件条件を手入力してください。",
        ],
      },
    };
  } finally {
    clearTimeout(timeout);
  }
}
