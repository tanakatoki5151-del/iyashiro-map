import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";

const root = new URL("../app/lib/location-profile/", import.meta.url);
const chunks = [0, 1, 2, 3].map((index) => {
  const text = readFileSync(new URL(`ecoscape-runtime-chunk-${index}.ts`, root), "utf8");
  const match = text.match(/^export default (.*);\s*$/s);
  if (!match) throw new Error(`chunk ${index} is not a JSON string export`);
  return JSON.parse(match[1]);
});
const encoded = chunks.join("");
const compressed = Buffer.from(encoded, "base64");
const summary = {
  chunkLengths: chunks.map((chunk) => chunk.length),
  encodedLength: encoded.length,
  encodedMod4: encoded.length % 4,
  compressedLength: compressed.length,
  compressedSha256: createHash("sha256").update(compressed).digest("hex"),
  compressedFirst32Hex: compressed.subarray(0, 32).toString("hex"),
  compressedLast32Hex: compressed.subarray(Math.max(0, compressed.length - 32)).toString("hex"),
  completeGzip: false,
};
try {
  const raw = gunzipSync(compressed);
  summary.completeGzip = true;
  summary.rawLength = raw.length;
  summary.rawSha256 = createHash("sha256").update(raw).digest("hex");
} catch (error) {
  summary.gunzipError = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
}
console.log(JSON.stringify(summary, null, 2));
