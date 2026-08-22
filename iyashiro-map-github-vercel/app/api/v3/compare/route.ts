import { compareCandidates } from "@/app/lib/integration-api/assessment";
import { errorResponse } from "@/app/lib/integration-api/errors";
import { readJsonBody } from "@/app/lib/integration-api/validation";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 60;

export async function POST(request: Request) {
  try {
    return Response.json(await compareCandidates(await readJsonBody(request, 2 * 1024 * 1024)), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    return errorResponse(error);
  }
}
