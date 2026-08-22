export type Verdict = "候補に残す" | "確認する" | "保留" | "見送る";

export type HousingType =
  | "detached"
  | "lowrise_apartment"
  | "interior_corridor_apartment"
  | "tower_apartment"
  | "one_room"
  | "maisonette"
  | "shop_house";

export type WaterState = "unknown" | "none" | "current" | "culvert" | "former";

export type MoveEvent = "contract" | "key_receipt" | "goods_move" | "first_overnight" | "opening";

export interface AssessmentForm {
  address: string;
  housingType: HousingType;
  buildingName: string;
  unit: string;
  facingBearing: string;
  bearingUncertainty: string;
  sharedEntranceBearing: string;
  unitEntranceBearing: string;
  kitchenBearing: string;
  stoveType: string;
  centerKnown: boolean;
  irregularOutline: boolean;
  frontOpen: boolean;
  rearSupport: boolean;
  directRoadAxis: boolean;
  drainageKnown: boolean;
  waterState: WaterState;
  waterPosition: string;
  waterDistance: string;
  waterVisible: boolean;
  waterAudible: boolean;
  waterEncloses: boolean;
  waterApproachesFront: boolean;
  waterDirectAxis: boolean;
  birthDate: string;
  birthTime: string;
  currentAddress: string;
  moveBearing: string;
  moveBearingUncertainty: string;
  candidateA: string;
  candidateB: string;
  candidateC: string;
  moveEvent: MoveEvent;
  ritualInterest: boolean;
}

export interface TrackFinding {
  track: string;
  name: string;
  layer: string;
  verdict: Verdict;
  affectsDecision: boolean;
  sourceMode: "原典直結" | "現代住宅への置換" | "観測" | "限定実装" | "歴史説明" | "任意相談" | "研究閉鎖／製品凍結" | "研究再開／製品退役";
  whatItSees: string;
  sourceMeaning: string;
  thisCase: string;
  action: string;
  confidence: "高" | "中" | "低";
}

export interface CandidateComparison {
  candidateId: "A" | "B" | "C";
  label: string;
  localDateTime: string;
  entered: boolean;
  eventType: MoveEvent;
  eventLabel: string;
  verdict: "確認する" | "保留";
  rank: null;
  missingCalendarLayers: string[];
  nextAction: string;
}

export interface AssessmentReport {
  assessmentId: string;
  generatedAt: string;
  destination: string;
  overallVerdict: Verdict;
  headline: string;
  tracks: TrackFinding[];
  candidateComparisons: CandidateComparison[];
  nextActions: string[];
  missing: string[];
  sixLayers: Array<{ name: string; tracks: string; note: string }>;
  policy: {
    totalScore: null;
    majorityVote: false;
    historicalWaterVotes: false;
    healthWealthPrediction: false;
  };
}

export const housingLabels: Record<HousingType, string> = {
  detached: "戸建て",
  lowrise_apartment: "低層マンション",
  interior_corridor_apartment: "内廊下マンション",
  tower_apartment: "タワーマンション",
  one_room: "1R・1K",
  maisonette: "メゾネット",
  shop_house: "店舗併用住宅",
};

export const moveEventLabels: Record<MoveEvent, string> = {
  contract: "契約日",
  key_receipt: "鍵受取",
  goods_move: "搬入",
  first_overnight: "初泊",
  opening: "開業",
};

const verdictRank: Record<Verdict, number> = {
  "候補に残す": 0,
  "確認する": 1,
  "保留": 2,
  "見送る": 3,
};

function numberOrNull(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeBearing(value: number): number {
  return ((value % 360) + 360) % 360;
}

function circularDistance(a: number, b: number): number {
  return Math.abs(((a - b + 180) % 360) - 180);
}

function mountainName(bearing: number): string {
  const names = ["子", "癸", "丑", "艮", "寅", "甲", "卯", "乙", "辰", "巽", "巳", "丙", "午", "丁", "未", "坤", "申", "庚", "酉", "辛", "戌", "乾", "亥", "壬"];
  return names[Math.floor((normalizeBearing(bearing) + 7.5) / 15) % 24];
}

function nearMountainBoundary(bearing: number, uncertainty: number): boolean {
  const center = normalizeBearing(bearing);
  return Array.from({ length: 24 }, (_, index) => 7.5 + index * 15).some(
    (edge) => circularDistance(center, edge) <= Math.max(0, uncertainty) + 1e-9,
  );
}

function t07Direction(bearing: number, uncertainty: number): { sector: string | null; candidates: string[] } {
  const center = normalizeBearing(bearing);
  const sectors: Array<[string, number, number]> = [
    ["北", 345, 15], ["北東", 15, 75], ["東", 75, 105], ["南東", 105, 165],
    ["南", 165, 195], ["南西", 195, 255], ["西", 255, 285], ["北西", 285, 345],
  ];
  const boundaries = [15, 75, 105, 165, 195, 255, 285, 345];
  if (boundaries.some((edge) => circularDistance(center, edge) <= Math.max(0, uncertainty) + 1e-9)) {
    const sample = [normalizeBearing(center - uncertainty - 0.001), normalizeBearing(center + uncertainty + 0.001)];
    const candidates = sectors
      .filter(([, start, end]) => sample.some((value) => start > end ? value > start || value < end : value > start && value < end))
      .map(([name]) => name);
    return { sector: null, candidates: [...new Set(candidates)] };
  }
  const sector = sectors.find(([, start, end]) => start > end ? center > start || center < end : center > start && center < end)?.[0] ?? null;
  return { sector, candidates: sector ? [sector] : [] };
}

function buildTrack(input: Omit<TrackFinding, "confidence"> & { confidence?: TrackFinding["confidence"] }): TrackFinding {
  return { confidence: input.confidence ?? "中", ...input };
}

function unique(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

export const defaultForm: AssessmentForm = {
  address: "",
  housingType: "interior_corridor_apartment",
  buildingName: "",
  unit: "",
  facingBearing: "",
  bearingUncertainty: "1.5",
  sharedEntranceBearing: "",
  unitEntranceBearing: "",
  kitchenBearing: "",
  stoveType: "IH",
  centerKnown: false,
  irregularOutline: false,
  frontOpen: false,
  rearSupport: false,
  directRoadAxis: false,
  drainageKnown: false,
  waterState: "unknown",
  waterPosition: "front",
  waterDistance: "",
  waterVisible: false,
  waterAudible: false,
  waterEncloses: false,
  waterApproachesFront: false,
  waterDirectAxis: false,
  birthDate: "",
  birthTime: "",
  currentAddress: "",
  moveBearing: "",
  moveBearingUncertainty: "1",
  candidateA: "",
  candidateB: "",
  candidateC: "",
  moveEvent: "first_overnight",
  ritualInterest: false,
};

export function assess(form: AssessmentForm): AssessmentReport {
  const tracks: TrackFinding[] = [];
  const missing: string[] = [];
  const actions: string[] = [];
  const facing = numberOrNull(form.facingBearing);
  const uncertainty = Math.max(0, numberOrNull(form.bearingUncertainty) ?? 0);
  const unitGate = numberOrNull(form.unitEntranceBearing);
  const sharedGate = numberOrNull(form.sharedEntranceBearing);
  const kitchen = numberOrNull(form.kitchenBearing);
  const moveBearing = numberOrNull(form.moveBearing);
  const moveUncertainty = Math.max(0, numberOrNull(form.moveBearingUncertainty) ?? 0);
  const candidateInputs = [
    ["A", form.candidateA],
    ["B", form.candidateB],
    ["C", form.candidateC],
  ] as const;
  const enteredCandidates = candidateInputs.filter(([, value]) => Boolean(value.trim()));
  const missingCalendarLayers = [
    "民用日から干支日への原典内変換",
    "任意年・地域の節入り・至の正確時刻",
    "出生由来の本人key",
    "方位境界の包含規則と現代測地adapter",
    "年・月・日・時・本人・行為を横断する総優先順位",
    "全入力から結論までを通す原典完成例",
  ];
  const candidateComparisons: CandidateComparison[] = candidateInputs.map(([candidateId, localDateTime]) => ({
    candidateId,
    label: `候補${candidateId}`,
    localDateTime,
    entered: Boolean(localDateTime.trim()),
    eventType: form.moveEvent,
    eventLabel: moveEventLabels[form.moveEvent],
    verdict: localDateTime.trim() ? "保留" : "確認する",
    rank: null,
    missingCalendarLayers: localDateTime.trim() ? [...missingCalendarLayers] : [],
    nextAction: localDateTime.trim()
      ? "干支日・節入り時刻・本人key・方位区分・優先順位を、出典を分けて確定する"
      : `候補${candidateId}の日時を入力する`,
  }));
  const apartment = form.housingType !== "detached" && form.housingType !== "shop_house";

  if (!form.address.trim()) {
    missing.push("候補物件の住所");
    actions.push("候補物件の住所を入力する");
  }

  const t01Ready = facing !== null && form.centerKnown;
  if (!form.centerKnown) actions.push("間取り図で住戸または建物の中心を確認する");
  if (facing === null) actions.push("真北基準で建物または住戸の向きを測る");
  tracks.push(buildTrack({
    track: "T01",
    name: "日本家相",
    layer: apartment ? "住戸" : "土地・建物",
    verdict: t01Ready ? "候補に残す" : "確認する",
    affectsDecision: true,
    sourceMode: apartment ? "現代住宅への置換" : "原典直結",
    whatItSees: "中心、張り欠け、入口、台所、便所などの配置を見ます。",
    sourceMeaning: "79原子は二読者と裁定で70件合意・9件訂正・原典上のOPEN 0件です。全件を候補規則として保持し、物件効果へ自動昇格させません。",
    thisCase: t01Ready
      ? `中心が確認済みで、向きは${facing!.toFixed(1)}°（${mountainName(facing!)}）です。これは配置確認の入口で、吉凶の合計点にはしません。`
      : "中心または向きが不足しているため、間取り上の配置を確定していません。",
    action: t01Ready ? "間取り図上で入口・台所・水回りを重ねて個別確認する" : "中心と向きを測ると、どの原典条件が該当するか決まります",
    confidence: t01Ready ? "中" : "高",
  }));

  const t02Missing: string[] = [];
  if (apartment && unitGate === null) t02Missing.push("住戸玄関");
  if (!apartment && sharedGate === null && unitGate === null) t02Missing.push("街路から入る主入口");
  if (kitchen === null) t02Missing.push("厨房区域");
  if (t02Missing.length) actions.push(`${t02Missing.join("・")}の位置または方位を確認する`);
  const selectedGate = apartment ? unitGate : sharedGate ?? unitGate;
  tracks.push(buildTrack({
    track: "T02",
    name: "陽宅三要・門主灶",
    layer: apartment ? "住戸" : "土地・建物",
    verdict: t02Missing.length ? "確認する" : "候補に残す",
    affectsDecision: true,
    sourceMode: apartment ? "現代住宅への置換" : "原典直結",
    whatItSees: "門、生活の主となる場所、厨房・灶を別の対象として見ます。",
    sourceMeaning: "保有乾隆刻本では灶房門と灶口を区別します。竈座・火門の別系譜を同じ規則へ混ぜません。",
    thisCase: t02Missing.length
      ? `${housingLabels[form.housingType]}として読み分けましたが、${t02Missing.join("・")}が未確定です。`
      : `門は${selectedGate?.toFixed(1)}°、厨房区域は${kitchen?.toFixed(1)}°。${form.stoveType}の操作面を古典の灶口へ自動置換していません。`,
    action: t02Missing.length ? "不足対象を現地または図面で確認する" : "門・主・厨房を三つの対象のまま説明へ進める",
  }));

  const t03Boundary = facing !== null && nearMountainBoundary(facing, uncertainty);
  tracks.push(buildTrack({
    track: "T03",
    name: "八宅・24山",
    layer: apartment ? "住戸" : "土地・建物",
    verdict: facing === null ? "確認する" : t03Boundary ? "保留" : "候補に残す",
    affectsDecision: true,
    sourceMode: "限定実装",
    whatItSees: "建物・住戸の向きを24区分で分類し、門路水の細則を別に扱います。",
    sourceMeaning: "24山の境界では推測せず、細則と門路水は確認できた範囲だけを使います。",
    thisCase: facing === null
      ? "向きがないため24山区分を出していません。"
      : t03Boundary
        ? `${facing.toFixed(1)}°±${uncertainty.toFixed(1)}°は24山の境界に触れるため保留です。`
        : `${facing.toFixed(1)}°は${mountainName(facing)}方として分類できます。`,
    action: facing === null || t03Boundary ? "真北基準、測定位置、誤差を確認して再判定する" : "門・道・現水の実測情報があれば細則を追加する",
    confidence: facing === null || t03Boundary ? "高" : "中",
  }));

  const t04Observed = form.frontOpen || form.rearSupport || form.directRoadAxis || form.drainageKnown;
  if (!t04Observed) actions.push("正面・背後・左右・道路・排水を現地写真か地図で確認する");
  tracks.push(buildTrack({
    track: "T04",
    name: "『陽宅十書』・形勢",
    layer: "土地・建物",
    verdict: !t04Observed || form.directRoadAxis ? "確認する" : "候補に残す",
    affectsDecision: true,
    sourceMode: "観測",
    whatItSees: "家から見た前後左右、道路、水、排水、見え方を観測します。",
    sourceMeaning: "家評価・排水・日時・儀礼を分離。明万暦本の未確定63箇所は1882年別版本407頁の対応範囲まで確認しましたが、語句を逆輸入せず原文未確定の bounded variants として製品判定から隔離しています。",
    thisCase: !t04Observed
      ? "外部形勢の観測がまだありません。"
      : `前方開放=${form.frontOpen ? "はい" : "未確認"}、背後支持=${form.rearSupport ? "はい" : "未確認"}、道路正面軸=${form.directRoadAxis ? "あり" : "なし／未確認"}です。`,
    action: form.directRoadAxis ? "道路が住戸玄関か建物入口のどちらへ向くか、距離・遮蔽とともに現地確認する" : "左右・排水・入口からの見え方を追加する",
  }));

  const waterContextOnly = form.waterState === "former" || form.waterState === "culvert";
  const currentWater = form.waterState === "current";
  if (form.waterState === "unknown") actions.push("現在の川・水路・暗渠・旧河道を区別して確認する");
  if (currentWater && !form.waterDistance) actions.push("現在水までの最短距離と観測地点を確認する");
  tracks.push(buildTrack({
    track: "T05",
    name: "『水龍經』・共通水法",
    layer: "土地・建物",
    verdict: form.waterState === "unknown" || (currentWater && (form.waterApproachesFront || form.waterDirectAxis || !form.waterDistance)) ? "確認する" : "候補に残す",
    affectsDecision: !waterContextOnly,
    sourceMode: currentWater ? "限定実装" : "観測",
    whatItSees: "同じWATER IDを使い、地域300m〜3kmと物件前後左右を二重投票せずに見ます。",
    sourceMeaning: "473図単位は32合意・441訂正・外交的OPEN 0です。訂正7件のblind独立再読も完了し、6件維持・RQ412の1件を訂正しました。R7詳細ZIP不在のためbyte比較は未主張です。411独立形の20形状語彙は形状層だけに使い、歴史的吉凶文を現代の資産・健康予測へ移しません。",
    thisCase: form.waterState === "unknown"
      ? "水の種類と時代が未確認です。"
      : form.waterState === "none"
        ? "入力範囲に水なしとして記録しました。地図未確認なら再確認が必要です。"
        : waterContextOnly
          ? `${form.waterState === "culvert" ? "暗渠" : "旧河道"}は歴史背景だけに表示し、現水と同じ判定票にしていません。`
          : `現在水は${form.waterPosition || "位置未入力"}、距離${form.waterDistance || "未入力"}m。抱く=${form.waterEncloses ? "はい" : "未確認"}、正面へ向かう=${form.waterApproachesFront || form.waterDirectAxis ? "要確認" : "なし／未確認"}です。`,
    action: currentWater ? "地図上の同じ水路番号、流向、建物との位置関係を確認する" : "歴史水は背景説明にとどめ、現在水の有無を別に確認する",
  }));

  tracks.push(buildTrack({
    track: "T06",
    name: "玄空",
    layer: "時間",
    verdict: "保留",
    affectsDecision: false,
    sourceMode: "研究閉鎖／製品凍結",
    whatItSees: "元運、基本盤、順逆、山・向、替星、建築時期の系譜を調べます。",
    sourceMeaning: "1935年一次資料43〜44頁の四運・子向き例は、二つの独立手順で九宮すべてを再現しました。一方、替星例・時代変更・集合住宅adapterの根拠が閉じないため製品判定は凍結しています。",
    thisCase: facing === null ? "向きも未入力で、玄空盤は作成していません。" : `${facing.toFixed(1)}°は記録しますが、歴史例の再現をこの住戸の飛星盤へ外挿しません。`,
    action: "v1の物件結論には加算せず、研究境界を表示する",
    confidence: "高",
  }));

  let t07Case = "本人・現住所・移動方位・候補日時を入力すると、行為を分けて比較します。";
  let t07Verdict: Verdict = "確認する";
  if (!form.birthDate) missing.push("本人の生年月日");
  if (!form.currentAddress) missing.push("現在住所");
  if (moveBearing === null) missing.push("現在地から候補地への真北方位");
  if (!enteredCandidates.length) missing.push("候補日時");
  if (form.birthDate && moveBearing !== null && enteredCandidates.length) {
    const direction = t07Direction(moveBearing, moveUncertainty);
    if (!direction.sector) {
      t07Verdict = "保留";
      t07Case = `移動方位${moveBearing.toFixed(1)}°±${moveUncertainty.toFixed(1)}°は区画境界です。候補=${direction.candidates.join("・") || "未確定"}。`;
      actions.push("現住所と候補住所の代表点を固定し、移動方位の境界を再計算する");
    } else {
      t07Verdict = "保留";
      const labels = enteredCandidates.map(([candidateId]) => `候補${candidateId}`).join("・");
      t07Case = `真北方位は${moveBearing.toFixed(1)}°（${direction.sector}）。${labels}を「${moveEventLabels[form.moveEvent]}」として別々に記録しました。原典内の暦変換と総優先順位が閉じていないため、年星などの近似計算で順位を作りません。`;
      actions.push("全候補について、正確な干支日・節入り・本人key・方位区分・総優先順位の原典根拠を確認する");
    }
  } else {
    actions.push("生年月日・現在住所・移動方位・候補日時をそろえる");
  }
  tracks.push(buildTrack({
    track: "T07",
    name: "方鑑・九星・移動",
    layer: "本人・移動・時間",
    verdict: t07Verdict,
    affectsDecision: true,
    sourceMode: "限定実装",
    whatItSees: "本人、現在地、候補地、候補日時を別層で照合します。",
    sourceMeaning: "年・月・日・時、方位、本人関係を分け、契約・鍵受取・搬入・初泊を一つの引越日に畳みません。",
    thisCase: t07Case,
    action: "不足する暦層は確認事項として残し、合計点や多数決を使わない",
    confidence: "低",
  }));

  tracks.push(buildTrack({
    track: "T08",
    name: "陰陽道・行為別歴史",
    layer: "移動・時間",
    verdict: "候補に残す",
    affectsDecision: false,
    sourceMode: "歴史説明",
    whatItSees: "引越、旅行、改築、入居、開業、造営を別の行為として説明します。",
    sourceMeaning: "引越・旅行・造営は限定的な歴史背景、入居は近接アダプター、改築・開業は未接続です。",
    thisCase: "家そのものの点数には使わず、選んだ行為の歴史説明だけを付けます。",
    action: "実際に比較したい行為名を確定する",
  }));

  tracks.push(buildTrack({
    track: "T09",
    name: "神道・家祓相談",
    layer: "儀礼",
    verdict: "候補に残す",
    affectsDecision: false,
    sourceMode: "任意相談",
    whatItSees: "住宅形式と希望に応じ、神社・管理会社へ確認する項目を整理します。",
    sourceMeaning: "儀礼は任意で、効能保証・物件点数・全国一律の料金や受付条件を作りません。",
    thisCase: form.ritualInterest ? "任意相談を希望として記録しました。物件ごとの許可と神社の受付条件を確認します。" : "希望なし。鑑定結果へ影響させません。",
    action: form.ritualInterest ? "神社へ祭名・場所・準備・初穂料を、管理側へ実施可否を確認する" : "必要になった時だけ任意相談を開く",
    confidence: "高",
  }));

  tracks.push(buildTrack({
    track: "T10",
    name: "奇門等",
    layer: "時間",
    verdict: "保留",
    affectsDecision: false,
    sourceMode: "研究再開／製品退役",
    whatItSees: "T07で答えきれない日時・出発時刻の独自価値を検証します。",
    sourceMeaning: "一次資料336頁を確認し、歴史的なA/B/Cの3 fixtureを再現しました。ただし任意年の現代契約日へ外挿できないため production は retired のままです。",
    thisCase: "研究用の歴史例だけを保持し、今回の候補日へ投票させません。",
    action: "v1ではT07の不足をT10で埋めない",
    confidence: "高",
  }));

  const decisionTracks = tracks.filter((track) => track.affectsDecision);
  const overallVerdict = decisionTracks.reduce<Verdict>(
    (worst, track) => verdictRank[track.verdict] > verdictRank[worst] ? track.verdict : worst,
    "候補に残す",
  );
  const headline: Record<Verdict, string> = {
    "候補に残す": "現時点では候補に残せます。未確認層は次の行動として残しています。",
    "確認する": "候補から外す段階ではありません。先に確認すると判断が進みます。",
    "保留": "境界または重要情報が未確定です。測定・日付確認後に再判定します。",
    "見送る": "根拠のある停止条件が確認されたため、今回の条件では見送ります。",
  };

  return {
    assessmentId: `HCL-${Date.now().toString(36).toUpperCase()}`,
    generatedAt: new Date().toISOString(),
    destination: form.address || "住所未入力",
    overallVerdict,
    headline: headline[overallVerdict],
    tracks,
    candidateComparisons,
    nextActions: unique(actions),
    missing: unique(missing),
    sixLayers: [
      { name: "土地・建物", tracks: "T01・T03・T04・T05", note: "敷地・外形・道路・水を観測" },
      { name: "住戸", tracks: "T01・T02・T03", note: "中心・入口・生活域・厨房" },
      { name: "時間", tracks: "T06・T07・T10", note: "実装・凍結境界を分離" },
      { name: "本人", tracks: "T07", note: "生年月日と本人関係" },
      { name: "移動", tracks: "T07・T08", note: "現在地・候補地・行為・日時" },
      { name: "儀礼", tracks: "T09", note: "任意相談。物件点数へ不算入" },
    ],
    policy: {
      totalScore: null,
      majorityVote: false,
      historicalWaterVotes: false,
      healthWealthPrediction: false,
    },
  };
}
