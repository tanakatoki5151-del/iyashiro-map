import {
  assess,
  defaultForm,
  type AssessmentForm,
  type AssessmentReport,
  type HousingType,
  type MoveEvent,
  type WaterState,
} from "./hcl-engine";
import { ApiError } from "./errors";
import { objectValue, optionalString } from "./validation";

const COMPASS_BEARINGS: Record<string, number> = {
  "北": 0,
  "n": 0,
  "north": 0,
  "北東": 45,
  "ne": 45,
  "northeast": 45,
  "東": 90,
  "e": 90,
  "east": 90,
  "南東": 135,
  "se": 135,
  "southeast": 135,
  "南": 180,
  "s": 180,
  "south": 180,
  "南西": 225,
  "sw": 225,
  "southwest": 225,
  "西": 270,
  "w": 270,
  "west": 270,
  "北西": 315,
  "nw": 315,
  "northwest": 315,
};

const HOUSING_TYPES = new Set<HousingType>([
  "detached",
  "lowrise_apartment",
  "interior_corridor_apartment",
  "tower_apartment",
  "one_room",
  "maisonette",
  "shop_house",
]);
const WATER_STATES = new Set<WaterState>(["unknown", "none", "current", "culvert", "former"]);
const MOVE_EVENTS = new Set<MoveEvent>(["contract", "key_receipt", "goods_move", "first_overnight", "opening"]);

function direction(value: unknown): string {
  if (value === undefined || value === null || value === "") return "";
  if (typeof value !== "string") {
    throw new ApiError(400, "invalid_direction", "方位は0〜359度または8方位の文字列で指定してください。");
  }
  if (!value.trim()) return "";
  const normalized = value.trim().toLowerCase();
  if (normalized in COMPASS_BEARINGS) return String(COMPASS_BEARINGS[normalized]);
  const parsed = Number(normalized.replace(/度$/, ""));
  if (!Number.isFinite(parsed)) {
    throw new ApiError(400, "invalid_direction", `方位「${value}」を0〜359度または8方位で指定してください。`);
  }
  return String(((parsed % 360) + 360) % 360);
}

function fullForm(value: Record<string, unknown>): AssessmentForm {
  const output: AssessmentForm = { ...defaultForm };
  for (const key of Object.keys(defaultForm) as Array<keyof AssessmentForm>) {
    if (!(key in value)) continue;
    const current = defaultForm[key];
    const incoming = value[key];
    if (typeof current === "boolean") {
      if (typeof incoming !== "boolean") throw new ApiError(400, "invalid_hcl_input", `${key} はbooleanで指定してください。`);
      (output as unknown as Record<string, unknown>)[key] = incoming;
    } else {
      const text = optionalString(incoming, 300) ?? "";
      (output as unknown as Record<string, unknown>)[key] = text;
    }
  }
  if (!HOUSING_TYPES.has(output.housingType)) throw new ApiError(400, "invalid_housing_type", "housingTypeが不正です。");
  if (!WATER_STATES.has(output.waterState)) throw new ApiError(400, "invalid_water_state", "waterStateが不正です。");
  if (!MOVE_EVENTS.has(output.moveEvent)) throw new ApiError(400, "invalid_move_event", "moveEventが不正です。");
  return output;
}

function compactHousingType(value: unknown): HousingType {
  if (value === undefined || value === null || value === "") return defaultForm.housingType;
  if (typeof value !== "string" || !HOUSING_TYPES.has(value as HousingType)) {
    throw new ApiError(400, "invalid_housing_type", "housingTypeが不正です。");
  }
  return value as HousingType;
}

function compactBoolean(value: unknown, field: string): boolean {
  if (value === undefined || value === null) return false;
  if (typeof value !== "boolean") {
    throw new ApiError(400, "invalid_hcl_input", `${field} はbooleanで指定してください。`);
  }
  return value;
}

function concerns(value: unknown): string[] {
  if (value === undefined || value === null || value === "") return [];
  if (!Array.isArray(value) && typeof value !== "string") {
    throw new ApiError(400, "invalid_hcl_input", "concernsはstringまたはstring[]で指定してください。");
  }
  const values = Array.isArray(value) ? value : [value];
  if (values.length > 20) throw new ApiError(400, "too_many_concerns", "concernsは20件以下にしてください。");
  return values.flatMap((item) => {
    const normalized = optionalString(item, 200);
    return normalized ? [normalized] : [];
  });
}

export interface HouseCompassResponse {
  schemaVersion: "house-compass/1.0";
  generatedAt: string;
  input: AssessmentForm;
  report: AssessmentReport;
  adapter: {
    mode: "full_form" | "compact_directions";
    contextOnly: {
      bedroomDirection: string | null;
      workDeskDirection: string | null;
      headDirection: string | null;
      buildingAgeBand: string | null;
      concerns: string[];
    };
    notes: string[];
  };
}

export function runHouseCompass(value: unknown, addressOverride?: string | null): HouseCompassResponse {
  const body = objectValue(value, "hcl");
  const formRecord = body.form === undefined || body.form === null
    ? null
    : objectValue(body.form, "hcl.form");
  let form: AssessmentForm;
  let mode: HouseCompassResponse["adapter"]["mode"];
  if (formRecord) {
    form = fullForm(formRecord);
    mode = "full_form";
  } else {
    form = {
      ...defaultForm,
      address: optionalString(body.address, 160) ?? addressOverride ?? "",
      buildingName: optionalString(body.buildingName, 200) ?? "",
      housingType: compactHousingType(body.housingType),
      unitEntranceBearing: direction(body.entranceDirection),
      sharedEntranceBearing: direction(body.sharedEntranceDirection),
      kitchenBearing: direction(body.kitchenDirection),
      facingBearing: direction(body.facingDirection),
      centerKnown: compactBoolean(body.centerKnown, "centerKnown"),
    };
    mode = "compact_directions";
  }
  if (!form.address && addressOverride) form.address = addressOverride;
  const adapterContext = {
    bedroomDirection: optionalString(body.bedroomDirection, 40),
    workDeskDirection: optionalString(body.workDeskDirection, 40),
    headDirection: optionalString(body.headDirection, 40),
    buildingAgeBand: optionalString(body.buildingAgeBand, 80),
    concerns: concerns(body.concerns),
  };
  const report = assess(form);
  return {
    schemaVersion: "house-compass/1.0",
    generatedAt: new Date().toISOString(),
    input: form,
    report,
    adapter: {
      mode,
      contextOnly: adapterContext,
      notes: [
        "HCL bounded engineのT01〜T10を使用し、合計点・多数決・健康財運予測は行いません。",
        "寝室・作業机・枕方位・築年帯・自由懸念は現行bounded engineの判定規則へ自動昇格せず、contextとして保持します。",
      ],
    },
  };
}
