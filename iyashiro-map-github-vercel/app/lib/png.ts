import { decode } from "fast-png";
import { tilePixel } from "./geo";

type DecodedTile = {
  width: number;
  height: number;
  channels: number;
  depth: number;
  data: Uint8Array | Uint16Array;
};
export type Pixel = { r: number; g: number; b: number; a: number };
const pngCache = new Map<string, Promise<DecodedTile | null>>();

async function getPng(url: string): Promise<DecodedTile | null> {
  const cached = pngCache.get(url);
  if (cached) return cached;
  const request = (async () => {
    try {
      const response = await fetch(url, {
        headers: { accept: "image/png,image/*;q=0.8" },
      });
      if (!response.ok) return null;
      return decode(
        new Uint8Array(await response.arrayBuffer()),
      ) as DecodedTile;
    } catch {
      return null;
    }
  })();
  pngCache.set(url, request);
  if (pngCache.size > 360) {
    pngCache.delete(pngCache.keys().next().value as string);
  }
  return request;
}

function pixelFromTile(tile: DecodedTile, x: number, y: number): Pixel | null {
  if (x < 0 || y < 0 || x >= tile.width || y >= tile.height) return null;
  const index = (y * tile.width + x) * tile.channels;
  const maximum = tile.depth === 16 ? 65_535 : 255;
  const normalize = (value: number | undefined) =>
    Math.round(((value ?? 0) / maximum) * 255);
  if (tile.channels === 1) {
    const value = normalize(tile.data[index]);
    return { r: value, g: value, b: value, a: 255 };
  }
  if (tile.channels === 2) {
    const value = normalize(tile.data[index]);
    return {
      r: value,
      g: value,
      b: value,
      a: normalize(tile.data[index + 1]),
    };
  }
  return {
    r: normalize(tile.data[index]),
    g: normalize(tile.data[index + 1]),
    b: normalize(tile.data[index + 2]),
    a: tile.channels >= 4 ? normalize(tile.data[index + 3]) : 255,
  };
}

export async function sampleRasterPixel(
  template: string,
  lat: number,
  lng: number,
  zoom: number,
) {
  const { x, y, pixelX, pixelY } = tilePixel(lat, lng, zoom);
  const url = template
    .replace("{z}", String(zoom))
    .replace("{x}", String(x))
    .replace("{y}", String(y));
  const tile = await getPng(url);
  return tile ? pixelFromTile(tile, pixelX, pixelY) : null;
}

const DEM_TEMPLATES = [
  "https://cyberjapandata.gsi.go.jp/xyz/dem5a_png/{z}/{x}/{y}.png",
  "https://cyberjapandata.gsi.go.jp/xyz/dem5b_png/{z}/{x}/{y}.png",
  "https://cyberjapandata.gsi.go.jp/xyz/dem5c_png/{z}/{x}/{y}.png",
  "https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png",
];

function elevationFromPixel(pixel: Pixel | null) {
  if (!pixel || pixel.a === 0) return null;
  const unsigned = pixel.r * 65_536 + pixel.g * 256 + pixel.b;
  if (unsigned === 8_388_608) return null;
  return (unsigned < 8_388_608 ? unsigned : unsigned - 16_777_216) * 0.01;
}

export async function getElevation(lat: number, lng: number, zoom = 13) {
  for (const template of DEM_TEMPLATES) {
    const elevation = elevationFromPixel(
      await sampleRasterPixel(template, lat, lng, zoom),
    );
    if (elevation !== null && Number.isFinite(elevation)) return elevation;
  }
  return null;
}

export function colorDistance(pixel: Pixel, color: [number, number, number]) {
  return Math.sqrt(
    (pixel.r - color[0]) ** 2 +
      (pixel.g - color[1]) ** 2 +
      (pixel.b - color[2]) ** 2,
  );
}
