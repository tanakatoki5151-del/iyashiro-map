import { errorResponse } from "@/app/lib/integration-api/errors";
import { intakeProperty } from "@/app/lib/integration-api/property-intake";
import { readJsonBody } from "@/app/lib/integration-api/validation";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 15;

export async function GET() {
  const { SUPPORTED_PROPERTY_HOSTS } = await import("@/app/lib/integration-api/property-intake");
  return Response.json({
    schemaVersion: "property-intake-capabilities/3.0",
    supportedHosts: SUPPORTED_PROPERTY_HOSTS,
    policy: "User-initiated, single-page, allowlisted HTTPS extraction only. No crawling.",
  });
}

export async function POST(request: Request) {
  try {
    return Response.json(await intakeProperty(await readJsonBody(request)), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    return errorResponse(error);
  }
}
