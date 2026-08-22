export type RequestOriginEvidence = {
  origin: string;
  requestUrl: string;
  host?: string | null;
  forwardedHost?: string | null;
  forwardedProto?: string | null;
  vercel?: string | null;
};

export function classifyRequestOrigin(
  evidence: RequestOriginEvidence,
): "allowed" | "invalid" | "rejected";
