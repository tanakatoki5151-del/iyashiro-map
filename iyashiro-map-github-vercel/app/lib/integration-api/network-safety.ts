import { isIP } from "node:net";

function parseIpv4(address: string): number[] | null {
  const parts = address.split(".").map(Number);
  return parts.length === 4 && parts.every((part) => Number.isInteger(part) && part >= 0 && part <= 255)
    ? parts
    : null;
}

function mappedIpv4(address: string): string | null {
  const dotted = /^(?:(?:0{1,4}:){5}|::)ffff:(\d+\.\d+\.\d+\.\d+)$/.exec(address)?.[1];
  if (dotted) return dotted;
  const hexadecimal = /^(?:(?:0{1,4}:){5}|::)ffff:([0-9a-f]{1,4}):([0-9a-f]{1,4})$/.exec(address);
  if (!hexadecimal) return null;
  const high = Number.parseInt(hexadecimal[1], 16);
  const low = Number.parseInt(hexadecimal[2], 16);
  return [high >> 8, high & 255, low >> 8, low & 255].join(".");
}

function ipv6BigInt(address: string): bigint | null {
  if (address.includes(".")) return null;
  const halves = address.split("::");
  if (halves.length > 2) return null;
  const left = halves[0] ? halves[0].split(":") : [];
  const right = halves.length === 2 && halves[1] ? halves[1].split(":") : [];
  const missing = 8 - left.length - right.length;
  if ((halves.length === 1 && missing !== 0) || (halves.length === 2 && missing < 1)) return null;
  const groups = [...left, ...Array(missing).fill("0"), ...right];
  if (groups.length !== 8 || groups.some((group) => !/^[0-9a-f]{1,4}$/i.test(group))) return null;
  return groups.reduce((value, group) => (value << BigInt(16)) | BigInt(Number.parseInt(group, 16)), BigInt(0));
}

function inIpv6Prefix(address: bigint, prefix: string, bits: number): boolean {
  const prefixValue = ipv6BigInt(prefix);
  if (prefixValue === null) return false;
  const shift = BigInt(128 - bits);
  return address >> shift === prefixValue >> shift;
}

const NON_GLOBAL_IPV6_PREFIXES = [
  ["2001::", 23],
  ["2001:db8::", 32],
  ["2002::", 16],
  ["3fff::", 20],
] as const;

export function isPrivateOrLocalAddress(address: string): boolean {
  const normalized = address.toLowerCase().split("%")[0];
  const v4 = parseIpv4(mappedIpv4(normalized) ?? normalized);
  if (v4) {
    const [a, b, c] = v4;
    return a === 0 || a === 10 || a === 127 || a >= 224 ||
      (a === 100 && b >= 64 && b <= 127) ||
      (a === 169 && b === 254) ||
      (a === 172 && b >= 16 && b <= 31) ||
      (a === 192 && b === 168) ||
      (a === 192 && b === 0 && (c === 0 || c === 2)) ||
      (a === 192 && b === 88 && c === 99) ||
      (a === 198 && (b === 18 || b === 19)) ||
      (a === 198 && b === 51 && c === 100) ||
      (a === 203 && b === 0 && c === 113);
  }
  if (isIP(normalized) === 6) {
    const first = Number.parseInt(normalized.split(":")[0] || "0", 16);
    const binary = ipv6BigInt(normalized);
    const globallyRoutableUnicast = (first & 0xe000) === 0x2000;
    return normalized === "::" ||
      normalized === "::1" ||
      normalized.startsWith("::") ||
      binary === null ||
      !globallyRoutableUnicast ||
      NON_GLOBAL_IPV6_PREFIXES.some(([prefix, bits]) => inIpv6Prefix(binary, prefix, bits)) ||
      (first & 0xfe00) === 0xfc00 ||
      (first & 0xffc0) === 0xfe80 ||
      (first & 0xffc0) === 0xfec0 ||
      (first & 0xff00) === 0xff00;
  }
  return true;
}
