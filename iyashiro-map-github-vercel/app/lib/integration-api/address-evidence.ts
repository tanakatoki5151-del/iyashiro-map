const KANJI_DIGIT: Record<string, number> = {
  〇: 0,
  零: 0,
  一: 1,
  二: 2,
  三: 3,
  四: 4,
  五: 5,
  六: 6,
  七: 7,
  八: 8,
  九: 9,
};

type AddressComponentKind = "chome" | "ban" | "go" | "segment";

interface AddressComponent {
  kind: AddressComponentKind;
  value: number;
}

function normalizedAddress(value: string): string {
  return value
    .normalize("NFKC")
    .replace(/〒?[0-9]{3}-?[0-9]{4}/g, "")
    .replace(/[‐‑‒–—―ー−]/g, "-")
    .replace(/\s+/g, "")
    .replace(/^(?:東京都|神奈川県)/, "");
}

function kanjiNumber(value: string): number {
  let total = 0;
  let current = 0;
  for (const character of value) {
    if (character === "百") {
      total += (current || 1) * 100;
      current = 0;
    } else if (character === "十") {
      total += (current || 1) * 10;
      current = 0;
    } else {
      current = current * 10 + (KANJI_DIGIT[character] ?? 0);
    }
  }
  return total + current;
}

function componentKind(label: string | undefined): AddressComponentKind {
  if (label === "丁目") return "chome";
  if (label === "番" || label === "番地") return "ban";
  if (label === "号") return "go";
  return "segment";
}

function addressParts(value: string): { stem: string; components: AddressComponent[] } {
  const normalized = normalizedAddress(value);
  const arabicStart = normalized.search(/[0-9]/);
  const kanjiMatch = /[〇零一二三四五六七八九十百]+(?=丁目|番地?|号)/.exec(normalized);
  const starts = [arabicStart, kanjiMatch?.index ?? -1].filter((index) => index >= 0);
  if (!starts.length) return { stem: normalized, components: [] };
  const numberStart = Math.min(...starts);
  const stem = normalized.slice(0, numberStart);
  const numericTail = normalized
    .slice(numberStart)
    .replace(
      /[〇零一二三四五六七八九十百]+(?=丁目|番地?|号)/g,
      (match) => String(kanjiNumber(match)),
    );
  const components: AddressComponent[] = [];
  for (const match of numericTail.matchAll(/([0-9]+)(丁目|番地?|号)?/g)) {
    components.push({
      kind: componentKind(match[2]),
      value: Number(match[1]),
    });
  }
  return { stem, components };
}

function componentsMatch(left: AddressComponent, right: AddressComponent): boolean {
  return left.value === right.value &&
    (left.kind === right.kind || left.kind === "segment" || right.kind === "segment");
}

export function hasPointAddressPrecision(value: string): boolean {
  const normalized = normalizedAddress(value);
  const hasMunicipality = /[^0-9]{1,16}(?:区|市)/.test(normalized);
  const components = addressParts(value).components;
  const hasLotOrHouseNumber = components.some((component) => component.kind === "ban" || component.kind === "go");
  const hasMultiSegmentAddress = components.length >= 2 &&
    components.some((component) => component.kind === "segment");
  return hasMunicipality && (hasLotOrHouseNumber || hasMultiSegmentAddress);
}

export function addressEvidenceIsConsistent(query: string, matchedAddress: string): boolean {
  if (!hasPointAddressPrecision(query) || !hasPointAddressPrecision(matchedAddress)) return false;
  const queryParts = addressParts(query);
  const matchParts = addressParts(matchedAddress);
  return queryParts.stem === matchParts.stem &&
    queryParts.components.length === matchParts.components.length &&
    queryParts.components.every((component, index) => componentsMatch(component, matchParts.components[index]));
}

export function addressEvidenceCanBeRefinedBy(
  extractedAddress: string,
  authoritativeAddress: string,
): boolean {
  if (!hasPointAddressPrecision(authoritativeAddress)) return false;
  if (hasPointAddressPrecision(extractedAddress)) {
    return addressEvidenceIsConsistent(extractedAddress, authoritativeAddress);
  }
  const extracted = addressParts(extractedAddress);
  const authoritative = addressParts(authoritativeAddress);
  return extracted.stem === authoritative.stem &&
    extracted.components.length <= authoritative.components.length &&
    extracted.components.every((component, index) => componentsMatch(component, authoritative.components[index]));
}
