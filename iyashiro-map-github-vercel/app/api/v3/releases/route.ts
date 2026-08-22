import { errorResponse } from "@/app/lib/integration-api/errors";
import { buildIntegratedReleaseCatalog } from "@/app/lib/integration-api/release-catalog";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 15;

export async function GET() {
  try {
    return Response.json(await buildIntegratedReleaseCatalog(), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    return errorResponse(error);
  }
}
