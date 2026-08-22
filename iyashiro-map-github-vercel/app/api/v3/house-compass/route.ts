import { errorResponse } from "@/app/lib/integration-api/errors";
import { runHouseCompass } from "@/app/lib/integration-api/hcl-adapter";
import { readJsonBody } from "@/app/lib/integration-api/validation";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 15;

export async function POST(request: Request) {
  try {
    return Response.json(runHouseCompass(await readJsonBody(request)), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    return errorResponse(error);
  }
}
