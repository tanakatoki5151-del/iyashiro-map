export type LandResearchReadiness = "A" | "B" | "C" | "D";
export type LandResearchPriority = "P0" | "P1" | "P2";
export type LandResearchLane = "ZONE_DEEPEN_NOW" | "CELL_FACT_CLOSE" | "POINT_CLOSE" | "AREA_POINT_SEED";
export type MarketReadiness = "REFERENCE" | "THIN";

export type LandAreaResearch = {
  order: number;
  priority: LandResearchPriority;
  ward: string;
  town: string;
  lane: LandResearchLane;
  readiness: LandResearchReadiness;
  representativeCell: string | null;
  knownRentUnits: number;
  distinctBuildings: number;
  policyV3EligibleUnits: number;
  marketReadiness: MarketReadiness;
  primaryUnknown: string;
  nextAction: string;
  signals: string[];
};

export const LAND_AREA_MATRIX_VERSION = "NEXUS_LAND_AREA_MATRIX_V1_20260818" as const;

export const landAreaMatrix: LandAreaResearch[] = [
  { order: 1, priority: "P0", ward: "渋谷区", town: "上原二丁目", lane: "POINT_CLOSE", readiness: "C", representativeCell: null, knownRentUnits: 2, distinctBuildings: 2, policyV3EligibleUnits: 2, marketReadiness: "THIN", primaryUnknown: "代表点、100mセル、各Projectの地点Fact", nextAction: "代表建物3件の番地、座標、100mセルを閉じる", signals: ["候補物件はあるが地点接続が未完了", "各Projectは照会可能、地点Factは未統合"] },
  { order: 2, priority: "P0", ward: "渋谷区", town: "上原三丁目", lane: "ZONE_DEEPEN_NOW", readiness: "A", representativeCell: "g193-226", knownRentUnits: 4, distinctBuildings: 4, policyV3EligibleUnits: 4, marketReadiness: "THIN", primaryUnknown: "重大履歴、境界、事件、環境の地点readbackと複数セル代表性", nextAction: "周辺3〜5セルへ広げ、連続ゾーンとして検証する", signals: ["V10候補セル 61/65/62、confidence 89", "UNDERLAND地域モデルでは水・湿気リスク低め", "PLACEGRAPHは部分接続、既知関係なしを安全とは解釈しない"] },
  { order: 3, priority: "P0", ward: "目黒区", town: "駒場四丁目", lane: "CELL_FACT_CLOSE", readiness: "B", representativeCell: "g199-227", knownRentUnits: 2, distinctBuildings: 1, policyV3EligibleUnits: 2, marketReadiness: "THIN", primaryUnknown: "V10正式Factカード、地下・重大履歴の地点readback", nextAction: "g199-227を各Projectへ照会し、地点カルテを閉じる", signals: ["100mセルは確定", "UNDERLAND・VEIL・LIMENはTOP10研究ポインタあり", "市場は1建物依存"] },
  { order: 4, priority: "P0", ward: "渋谷区", town: "大山町", lane: "CELL_FACT_CLOSE", readiness: "B", representativeCell: "g191-222", knownRentUnits: 3, distinctBuildings: 3, policyV3EligibleUnits: 3, marketReadiness: "THIN", primaryUnknown: "境界polygon、地下・重大履歴・祭祀境界の地点Fact", nextAction: "高境界注意をpolygonで確認し、他Projectを接続する", signals: ["V10候補セル 54/59/62、confidence 74", "代表セルは接続済み", "境界の精密形状確認が重要"] },
  { order: 5, priority: "P0", ward: "目黒区", town: "東が丘一丁目", lane: "ZONE_DEEPEN_NOW", readiness: "A", representativeCell: "g237-217 / g234-218", knownRentUnits: 2, distinctBuildings: 2, policyV3EligibleUnits: 2, marketReadiness: "THIN", primaryUnknown: "2セル間と周辺の連続性、重大履歴・境界・事件の地点readback", nextAction: "2セルと周辺8セルをゾーン化して比較する", signals: ["V10候補セル 68/71/65 conf80、62/65/64 conf81", "UNDERLAND地域モデルでは水・湿気リスク低め", "2つの確定セルがありゾーン検証へ進める"] },
  { order: 6, priority: "P0", ward: "世田谷区", town: "北沢五丁目", lane: "POINT_CLOSE", readiness: "C", representativeCell: null, knownRentUnits: 4, distinctBuildings: 4, policyV3EligibleUnits: 4, marketReadiness: "THIN", primaryUnknown: "物件代表点と100mセル、Project結果の同一地点統合", nextAction: "代表建物3件の番地回復後、全Projectへ一括照会する", signals: ["Project B・VEIL・UNDERLANDに研究ポインタあり", "物件と研究地点の橋が未完成"] },
  { order: 7, priority: "P0", ward: "世田谷区", town: "北沢一丁目", lane: "POINT_CLOSE", readiness: "C", representativeCell: null, knownRentUnits: 2, distinctBuildings: 2, policyV3EligibleUnits: 2, marketReadiness: "THIN", primaryUnknown: "正確な代表セル、parcel照合、各Projectの地点Fact", nextAction: "地籍図で確認済みのparcel群から代表セルを固定する", signals: ["地籍図・歴史資料の研究が進行", "セル固定前なので地域評価へ昇格しない"] },
  { order: 8, priority: "P0", ward: "目黒区", town: "柿の木坂二丁目", lane: "CELL_FACT_CLOSE", readiness: "B", representativeCell: "複数セル候補", knownRentUnits: 3, distinctBuildings: 2, policyV3EligibleUnits: 1, marketReadiness: "THIN", primaryUnknown: "代表セル選定、V10・地下・重大履歴の地点Fact", nextAction: "複数住戸セルを集約し、町丁目の代表3セルを確定する", signals: ["V10側にexact cell候補あり", "PLACEGRAPHの地理情報を利用可能"] },
  { order: 9, priority: "P0", ward: "目黒区", town: "目黒本町五丁目", lane: "POINT_CLOSE", readiness: "C", representativeCell: null, knownRentUnits: 6, distinctBuildings: 6, policyV3EligibleUnits: 5, marketReadiness: "THIN", primaryUnknown: "番地既知5建物の100mセル接続と全Project地点Fact", nextAction: "番地既知5建物を一括で地点接続する", signals: ["建物の多様性は比較的良い", "土地側の地点接続がボトルネック"] },
  { order: 10, priority: "P0", ward: "千代田区", town: "一番町", lane: "AREA_POINT_SEED", readiness: "D", representativeCell: null, knownRentUnits: 2, distinctBuildings: 1, policyV3EligibleUnits: 2, marketReadiness: "THIN", primaryUnknown: "号室、番地、代表セル、土地Fact全般", nextAction: "物件ではなく町丁目の代表5セルから土地研究を開始する", signals: ["市場も土地も1建物・町丁目依存", "代表地点の新規設定が必要"] },
  { order: 11, priority: "P1", ward: "目黒区", town: "八雲四丁目", lane: "CELL_FACT_CLOSE", readiness: "B", representativeCell: "g241-219", knownRentUnits: 3, distinctBuildings: 3, policyV3EligibleUnits: 3, marketReadiness: "THIN", primaryUnknown: "高境界polygon、他Project地点Fact、周辺連続性", nextAction: "境界polygon確認と周辺8セル接続を行う", signals: ["V10候補セル 67/70/65、confidence 82", "高境界のため形状確認が必要"] },
  { order: 12, priority: "P1", ward: "世田谷区", town: "代沢二丁目", lane: "ZONE_DEEPEN_NOW", readiness: "A", representativeCell: "g200-222 / g199-219", knownRentUnits: 4, distinctBuildings: 2, policyV3EligibleUnits: 4, marketReadiness: "THIN", primaryUnknown: "事件・環境readback、ゾーン連続性、0件の意味", nextAction: "2セルと周辺をゾーン化し、未調査Projectだけ追加する", signals: ["V10候補セル 70/67/64 conf84、73/76/61 conf93", "UNDERLAND部分研究あり", "VEIL厳格陽性0、LIMEN直接陽性0は安全保証ではない"] },
  { order: 13, priority: "P1", ward: "大田区", town: "中馬込一丁目", lane: "AREA_POINT_SEED", readiness: "D", representativeCell: null, knownRentUnits: 3, distinctBuildings: 3, policyV3EligibleUnits: 3, marketReadiness: "THIN", primaryUnknown: "建物identity、番地、100mセル、土地Fact", nextAction: "低価格候補3件の建物identityと代表セルを閉じる", signals: ["市場候補はある", "町丁目情報から地点Factへ未接続"] },
  { order: 14, priority: "P1", ward: "渋谷区", town: "富ヶ谷二丁目", lane: "CELL_FACT_CLOSE", readiness: "B", representativeCell: "g196-233", knownRentUnits: 4, distinctBuildings: 4, policyV3EligibleUnits: 4, marketReadiness: "THIN", primaryUnknown: "代表点精度、他Project地点Fact、周辺連続性", nextAction: "番地既知建物を基準に周辺セルへ広げる", signals: ["V10候補セル 64/62/62、confidence 77", "PLACEGRAPHポインタあり"] },
  { order: 15, priority: "P1", ward: "大田区", town: "久が原四丁目", lane: "AREA_POINT_SEED", readiness: "D", representativeCell: null, knownRentUnits: 3, distinctBuildings: 3, policyV3EligibleUnits: 3, marketReadiness: "THIN", primaryUnknown: "代表点、100mセル、全Project地点Fact", nextAction: "候補3建物の住所回復とセル接続を先行する", signals: ["低層・広めの市場候補あり", "土地は町丁目段階"] },
  { order: 16, priority: "P1", ward: "世田谷区", town: "等々力七丁目", lane: "CELL_FACT_CLOSE", readiness: "B", representativeCell: "g252-202", knownRentUnits: 3, distinctBuildings: 3, policyV3EligibleUnits: 3, marketReadiness: "THIN", primaryUnknown: "他Project地点Factと代表セルの町丁目代表性", nextAction: "g252-202と周辺セルを全Projectへ接続する", signals: ["V10候補セル 69/73/63、confidence 82", "代表セル確定済み"] },
  { order: 17, priority: "P1", ward: "品川区", town: "小山台二丁目", lane: "POINT_CLOSE", readiness: "C", representativeCell: null, knownRentUnits: 1, distinctBuildings: 1, policyV3EligibleUnits: 1, marketReadiness: "THIN", primaryUnknown: "番地既知物件の100mセルと全Project地点Fact", nextAction: "グランシルク小山台をセル化し周辺へ拡張する", signals: ["exact address候補あり", "市場・土地とも1物件依存"] },
  { order: 18, priority: "P1", ward: "目黒区", town: "東が丘二丁目", lane: "CELL_FACT_CLOSE", readiness: "B", representativeCell: "g233-211", knownRentUnits: 3, distinctBuildings: 2, policyV3EligibleUnits: 2, marketReadiness: "THIN", primaryUnknown: "他Project地点Factと別セルとの比較", nextAction: "東が丘一丁目との連続ゾーン比較を行う", signals: ["V10普通地 51/55/58、confidence 80", "東が丘一丁目との相対比較に向く"] },
  { order: 19, priority: "P1", ward: "目黒区", town: "八雲五丁目", lane: "CELL_FACT_CLOSE", readiness: "B", representativeCell: "g243-216ほか", knownRentUnits: 22, distinctBuildings: 3, policyV3EligibleUnits: 21, marketReadiness: "THIN", primaryUnknown: "他Project地点Fact、住戸・建物偏重、町丁目内セル差", nextAction: "多数の住戸を建物重複なしの3〜5代表セルへ圧縮する", signals: ["V10普通地 55/52/60、confidence 81", "22住戸あるが3建物に集中", "住戸数だけで市場が厚いとは扱わない"] },
  { order: 20, priority: "P1", ward: "大田区", town: "北千束二丁目", lane: "POINT_CLOSE", readiness: "C", representativeCell: null, knownRentUnits: 6, distinctBuildings: 7, policyV3EligibleUnits: 4, marketReadiness: "THIN", primaryUnknown: "セレ北千束のセル接続と全Project地点Fact", nextAction: "セレ北千束205を起点に住所点から土地Factへ接続する", signals: ["exact room/addressの住戸あり", "建物多様性は比較的確保"] },
  { order: 21, priority: "P1", ward: "大田区", town: "上池台一丁目", lane: "POINT_CLOSE", readiness: "C", representativeCell: null, knownRentUnits: 12, distinctBuildings: 8, policyV3EligibleUnits: 9, marketReadiness: "REFERENCE", primaryUnknown: "8建物の番地、代表セル、土地Fact", nextAction: "市場の厚みを活かし代表5建物を地点接続する", signals: ["25地域で唯一の市場REFERENCE段階", "12住戸・8建物で比較の足場あり", "土地地点接続は未完了"] },
  { order: 22, priority: "P1", ward: "大田区", town: "久が原三丁目", lane: "CELL_FACT_CLOSE", readiness: "B", representativeCell: "g285-237", knownRentUnits: 1, distinctBuildings: 1, policyV3EligibleUnits: 1, marketReadiness: "THIN", primaryUnknown: "他Project地点Factと1物件依存の代表性", nextAction: "周辺セルと別建物で代表性を検証する", signals: ["V10候補セル 55/59/55、confidence 73", "市場標本は1件のみ"] },
  { order: 23, priority: "P2", ward: "豊島区", town: "目白三丁目", lane: "AREA_POINT_SEED", readiness: "D", representativeCell: null, knownRentUnits: 4, distinctBuildings: 4, policyV3EligibleUnits: 4, marketReadiness: "THIN", primaryUnknown: "番地、代表セル、土地Fact", nextAction: "目白居住比較用に代表3セルを新規設定する", signals: ["現住地域との比較軸", "土地は町丁目段階"] },
  { order: 24, priority: "P2", ward: "世田谷区", town: "代沢一丁目", lane: "AREA_POINT_SEED", readiness: "D", representativeCell: null, knownRentUnits: 5, distinctBuildings: 5, policyV3EligibleUnits: 5, marketReadiness: "THIN", primaryUnknown: "建物identity、番地、代表セル、土地Fact", nextAction: "5建物のidentityから町丁目代表セルを作る", signals: ["5建物の市場入口あり", "地点研究は未接続"] },
  { order: 25, priority: "P2", ward: "大田区", town: "中馬込二丁目", lane: "AREA_POINT_SEED", readiness: "D", representativeCell: null, knownRentUnits: 5, distinctBuildings: 5, policyV3EligibleUnits: 4, marketReadiness: "THIN", primaryUnknown: "建物identity、番地、代表セル、土地Fact", nextAction: "5建物を住所回復し、中馬込一丁目と連続比較する", signals: ["市場入口は5建物", "中馬込一丁目とのゾーン比較が必要"] },
];

export const landAreaMatrixSummary = {
  asOfJST: "2026-08-18 22:45 JST",
  areaCount: landAreaMatrix.length,
  readiness: { A: 3, B: 9, C: 7, D: 6 },
  priority: { P0: 10, P1: 12, P2: 3 },
  market: { reference: 1, thin: 24 },
  marketScaleJobs: 28,
  rawTarget: 3_000,
  canonicalTarget: 1_500,
  newRawInThisMegaStep: 0,
} as const;
