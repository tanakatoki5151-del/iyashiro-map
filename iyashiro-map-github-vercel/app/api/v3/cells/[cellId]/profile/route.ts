import { errorResponse } from "@/app/lib/integration-api/errors";
import { buildCellProfile } from "@/app/lib/integration-api/profile";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 15;

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ cellId: string }> },
) {
  try {
    const { cellId } = await params;
    return Response.json(await buildCellProfile(cellId), {
      headers: {
        "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400",
      },
    });
  } catch (error) {
    return errorResponse(error);
  }
}
