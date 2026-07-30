import { NextResponse } from "next/server";

export function GET() {
  return NextResponse.json({
    status: "ok",
    service: "イヤシロ土地判定マップ",
    scope: ["東京23区", "横浜市", "川崎市"],
    schemaVersion: "1.0",
    endpoints: {
      coordinates: "/api/diagnose?lat=35.6812&lng=139.7671",
      address: "/api/lookup?q=東京都千代田区丸の内1丁目",
      search: "/api/search?q=目白駅",
    },
  });
}
