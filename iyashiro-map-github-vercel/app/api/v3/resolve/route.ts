import { errorResponse } from "@/app/lib/integration-api/errors";
import { parseResolveInput, resolveLocation } from "@/app/lib/integration-api/resolution";
import { readJsonBody } from "@/app/lib/integration-api/validation";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 15;

export async function POST(request: Request) {
  try {
    const body = await readJsonBody(request);
    return Response.json(await resolveLocation(parseResolveInput(body)), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    return errorResponse(error);
  }
}
