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
const raw = gunzipSync(compressed);
const frequency = new Map();
for (const byte of raw) frequency.set(byte, (frequency.get(byte) ?? 0) + 1);
const top = [...frequency.entries()].sort((a, b) => b[1] - a[1]).slice(0, 32);
const candidateRecordSizes = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16].map((size) => ({
  size,
  divisible: raw.length % size === 0,
  records: raw.length / size,
  formal120662: raw.length === 120662 * size,
  dense587x462: raw.length === 587 * 462 * size,
}));
console.log(JSON.stringify({
  chunkLengths: chunks.map((chunk) => chunk.length),
  encodedLength: encoded.length,
  compressedLength: compressed.length,
  compressedSha256: createHash("sha256").update(compressed).digest("hex"),
  rawLength: raw.length,
  rawSha256: createHash("sha256").update(raw).digest("hex"),
  first256Hex: raw.subarray(0, 256).toString("hex"),
  last256Hex: raw.subarray(Math.max(0, raw.length - 256)).toString("hex"),
  distinctByteCount: frequency.size,
  topByteFrequency: top,
  candidateRecordSizes,
}, null, 2));
