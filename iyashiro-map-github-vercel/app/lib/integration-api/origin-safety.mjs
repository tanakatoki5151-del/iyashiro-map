const UNSAFE_AUTHORITY = /[,\s/\\@?#]/u;
const UNSAFE_ORIGIN = /[,\s]/u;

function httpProtocol(value) {
  if (value === "http:" || value === "http") return "http:";
  if (value === "https:" || value === "https") return "https:";
  return null;
}

function forwardedProtocol(value) {
  if (value === "http") return "http:";
  if (value === "https") return "https:";
  return null;
}

function canonicalOriginHeader(value) {
  if (
    typeof value !== "string"
    || value.length === 0
    || value !== value.trim()
    || UNSAFE_ORIGIN.test(value)
  ) return null;
  try {
    const parsed = new URL(value);
    if (
      !httpProtocol(parsed.protocol)
      || parsed.username
      || parsed.password
      || parsed.pathname !== "/"
      || parsed.search
      || parsed.hash
      || parsed.origin !== value
    ) return null;
    return parsed.origin;
  } catch {
    return null;
  }
}

function requestOriginEvidence(requestUrl) {
  if (typeof requestUrl !== "string" || requestUrl.length === 0) return null;
  try {
    const parsed = new URL(requestUrl);
    const protocol = httpProtocol(parsed.protocol);
    if (!protocol || parsed.username || parsed.password) return null;
    return { origin: parsed.origin, protocol };
  } catch {
    return null;
  }
}

function authorityOriginEvidence(protocol, authority) {
  if (authority === null || authority === undefined) return { kind: "absent" };
  if (
    !protocol
    || typeof authority !== "string"
    || authority.length === 0
    || authority !== authority.trim()
    || UNSAFE_AUTHORITY.test(authority)
  ) return { kind: "invalid" };
  try {
    const parsed = new URL(protocol + "//" + authority);
    if (
      parsed.protocol !== protocol
      || parsed.username
      || parsed.password
      || parsed.pathname !== "/"
      || parsed.search
      || parsed.hash
    ) return { kind: "invalid" };
    return { kind: "valid", origin: parsed.origin };
  } catch {
    return { kind: "invalid" };
  }
}

/**
 * Classify a browser Origin against origins independently evidenced by the request.
 * Present-but-invalid trust evidence fails closed. Forwarded headers are considered
 * only on Vercel, which overwrites them at its edge.
 *
 * @returns {"allowed" | "invalid" | "rejected"}
 */
export function classifyRequestOrigin({
  origin,
  requestUrl,
  host = null,
  forwardedHost = null,
  forwardedProto = null,
  vercel = null,
}) {
  const suppliedOrigin = canonicalOriginHeader(origin);
  if (!suppliedOrigin) return "invalid";

  const requestEvidence = requestOriginEvidence(requestUrl);
  if (!requestEvidence) return "invalid";
  const candidates = new Set([requestEvidence.origin]);

  const hostEvidence = authorityOriginEvidence(requestEvidence.protocol, host);
  if (hostEvidence.kind === "invalid") return "invalid";
  if (hostEvidence.kind === "valid") candidates.add(hostEvidence.origin);

  if (vercel === "1") {
    const forwardedPairAbsent = forwardedHost === null && forwardedProto === null;
    if (!forwardedPairAbsent) {
      const protocol = forwardedProtocol(forwardedProto);
      if (!protocol) return "invalid";
      const forwardedEvidence = authorityOriginEvidence(protocol, forwardedHost);
      if (forwardedEvidence.kind !== "valid") return "invalid";
      candidates.add(forwardedEvidence.origin);
    }
  }

  return candidates.has(suppliedOrigin) ? "allowed" : "rejected";
}
