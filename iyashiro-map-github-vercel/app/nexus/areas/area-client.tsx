"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  landAreaMatrix,
  landAreaMatrixSummary,
  type LandResearchLane,
  type LandResearchPriority,
  type LandResearchReadiness,
} from "@/app/lib/nexus/land-area-matrix-v1";

const laneLabels: Record<LandResearchLane, string> = {
  ZONE_DEEPEN_NOW: "周辺セルまでゾーン化",
  CELL_FACT_CLOSE: "確定セルの調査を閉じる",
  POINT_CLOSE: "住所から100m地点を確定",
  AREA_POINT_SEED: "代表地点を新規設定",
};

const readinessLabels: Record<LandResearchReadiness, string> = {
  A: "複数研究が地点接続済み",
  B: "代表セルあり、調査の穴が残る",
  C: "住所・地点接続が途中",
  D: "町丁目段階から開始",
};

function readinessStyle(readiness: LandResearchReadiness): React.CSSProperties {
  if (readiness === "A") return { background: "#e4f2e8", color: "#285a38", borderColor: "#b7d7c0" };
  if (readiness === "B") return { background: "#e8f0f5", color: "#315870", borderColor: "#bfd1dc" };
  if (readiness === "C") return { background: "#fff4dd", color: "#75561e", borderColor: "#ead09a" };
  return { background: "#f1efec", color: "#665f58", borderColor: "#d8d2ca" };
}

function priorityStyle(priority: LandResearchPriority): React.CSSProperties {
  if (priority === "P0") return { background: "#173d49", color: "white" };
  if (priority === "P1") return { background: "#dcebef", color: "#234e5a" };
  return { background: "#ece8e1", color: "#605950" };
}

function selectStyle(): React.CSSProperties {
  return { padding: "10px 12px", borderRadius: 10, border: "1px solid #d7d0c8", background: "white", fontSize: 14, color: "#25211e" };
}

export default function AreaClient() {
  const [priority, setPriority] = useState<"ALL" | LandResearchPriority>("ALL");
  const [readiness, setReadiness] = useState<"ALL" | LandResearchReadiness>("ALL");
  const [query, setQuery] = useState("");

  const rows = useMemo(() => landAreaMatrix.filter((area) => {
    if (priority !== "ALL" && area.priority !== priority) return false;
    if (readiness !== "ALL" && area.readiness !== readiness) return false;
    const needle = query.trim().toLowerCase();
    if (!needle) return true;
    return `${area.ward}${area.town}${area.primaryUnknown}${area.nextAction}${area.signals.join(" ")}`.toLowerCase().includes(needle);
  }), [priority, readiness, query]);

  return <main style={{ minHeight: "100vh", background: "#f5f3ee", color: "#211e1b", fontFamily: '-apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP",sans-serif' }}>
    <div style={{ maxWidth: 1160, margin: "0 auto", padding: "28px 18px 72px" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, marginBottom: 18 }}>
        <div>
          <div style={{ fontSize: 12, color: "#726a62", letterSpacing: ".08em" }}>LAND-FIRST RESEARCH CONTROL</div>
          <h1 style={{ margin: "4px 0", fontSize: 31 }}>住む地域の研究マップ 🗺️🧬</h1>
        </div>
        <nav style={{ display: "flex", gap: 12, fontSize: 13 }}>
          <Link href="/nexus" style={{ color: "#245f70", fontWeight: 800, textDecoration: "none" }}>物件判定</Link>
          <Link href="/profile" style={{ color: "#245f70", fontWeight: 800, textDecoration: "none" }}>土地カルテ</Link>
          <Link href="/" style={{ color: "#245f70", fontWeight: 800, textDecoration: "none" }}>地図</Link>
        </nav>
      </header>

      <section style={{ background: "#132d36", color: "white", borderRadius: 19, padding: 20, marginBottom: 14 }}>
        <div style={{ fontSize: 12, opacity: .72 }}>25地域の土地研究を、良し悪しではなく「どこまで判明したか」で管理</div>
        <h2 style={{ margin: "5px 0 7px", fontSize: 23 }}>居住おすすめ順位ではありません</h2>
        <div style={{ fontSize: 13, lineHeight: 1.7, opacity: .82 }}>A〜Dは研究成熟度、P0〜P2は調査を閉じる順番です。土地情報の0件、未調査、該当なしを安全へ読み替えません。家賃市場は別カードで現実性だけを確認します。</div>
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 9, marginBottom: 14 }}>
        <div style={{ background: "white", borderRadius: 14, padding: 14, border: "1px solid #e4ded7" }}>対象地域<br/><b style={{ fontSize: 23 }}>{landAreaMatrixSummary.areaCount}</b></div>
        <div style={{ background: "#e4f2e8", borderRadius: 14, padding: 14, border: "1px solid #b7d7c0" }}>研究A<br/><b style={{ fontSize: 23 }}>{landAreaMatrixSummary.readiness.A}</b></div>
        <div style={{ background: "#e8f0f5", borderRadius: 14, padding: 14, border: "1px solid #bfd1dc" }}>研究B<br/><b style={{ fontSize: 23 }}>{landAreaMatrixSummary.readiness.B}</b></div>
        <div style={{ background: "#fff4dd", borderRadius: 14, padding: 14, border: "1px solid #ead09a" }}>研究C<br/><b style={{ fontSize: 23 }}>{landAreaMatrixSummary.readiness.C}</b></div>
        <div style={{ background: "#f1efec", borderRadius: 14, padding: 14, border: "1px solid #d8d2ca" }}>研究D<br/><b style={{ fontSize: 23 }}>{landAreaMatrixSummary.readiness.D}</b></div>
        <div style={{ background: "white", borderRadius: 14, padding: 14, border: "1px solid #e4ded7" }}>市場Reference<br/><b style={{ fontSize: 23 }}>{landAreaMatrixSummary.market.reference}</b></div>
      </section>

      <section style={{ background: "#fff7e6", border: "1px solid #ead49d", borderRadius: 15, padding: 15, marginBottom: 14, fontSize: 13, lineHeight: 1.65 }}>
        <b>市場拡張は別レーンで実行します。</b> 28ジョブを作成し、Raw {landAreaMatrixSummary.rawTarget.toLocaleString("ja-JP")}件、重複・身元確認後のCanonical {landAreaMatrixSummary.canonicalTarget.toLocaleString("ja-JP")}件を第一目標にしています。このメガステップで新規に取り込んだRawは {landAreaMatrixSummary.newRawInThisMegaStep}件で、まだ実行キュー段階です。
      </section>

      <section style={{ display: "flex", flexWrap: "wrap", gap: 9, alignItems: "center", background: "white", border: "1px solid #e4ded7", borderRadius: 15, padding: 13, marginBottom: 14 }}>
        <select aria-label="優先度" value={priority} onChange={(event) => setPriority(event.target.value as "ALL" | LandResearchPriority)} style={selectStyle()}>
          <option value="ALL">優先度すべて</option><option value="P0">P0 最優先</option><option value="P1">P1 次点</option><option value="P2">P2 比較枠</option>
        </select>
        <select aria-label="研究成熟度" value={readiness} onChange={(event) => setReadiness(event.target.value as "ALL" | LandResearchReadiness)} style={selectStyle()}>
          <option value="ALL">成熟度すべて</option><option value="A">A 複数研究接続</option><option value="B">B 代表セルあり</option><option value="C">C 地点接続途中</option><option value="D">D 町丁目段階</option>
        </select>
        <input aria-label="地域検索" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="地域名・未確認事項を検索" style={{ ...selectStyle(), flex: "1 1 230px" }} />
        <span style={{ fontSize: 12, color: "#746d65" }}>表示 {rows.length} / {landAreaMatrix.length}</span>
      </section>

      <section style={{ display: "grid", gap: 12 }}>
        {rows.map((area) => <article key={`${area.ward}-${area.town}`} style={{ background: "white", border: "1px solid #e2ddd6", borderRadius: 18, padding: 18, boxShadow: "0 5px 22px rgba(36,32,28,.045)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start", flexWrap: "wrap" }}>
            <div>
              <div style={{ fontSize: 12, color: "#766f67" }}>研究閉鎖順 #{area.order} ・ {area.ward}</div>
              <h2 style={{ margin: "3px 0 7px", fontSize: 22 }}>{area.town}</h2>
              <div style={{ display: "flex", gap: 7, flexWrap: "wrap" }}>
                <span style={{ ...priorityStyle(area.priority), padding: "5px 9px", borderRadius: 999, fontSize: 11, fontWeight: 850 }}>{area.priority}</span>
                <span style={{ ...readinessStyle(area.readiness), padding: "5px 9px", borderRadius: 999, border: "1px solid", fontSize: 11, fontWeight: 850 }}>研究 {area.readiness}</span>
                <span style={{ background: "#f0f4f5", color: "#3c5b64", padding: "5px 9px", borderRadius: 999, fontSize: 11, fontWeight: 750 }}>{laneLabels[area.lane]}</span>
                <span style={{ background: area.marketReadiness === "REFERENCE" ? "#e8f2e9" : "#f2efeb", color: area.marketReadiness === "REFERENCE" ? "#315d3e" : "#6a625a", padding: "5px 9px", borderRadius: 999, fontSize: 11, fontWeight: 750 }}>市場 {area.marketReadiness}</span>
              </div>
            </div>
            <div style={{ minWidth: 190, background: "#f7f5f1", borderRadius: 13, padding: 12, fontSize: 12, lineHeight: 1.6 }}>
              代表セル<br/><b>{area.representativeCell ?? "未確定"}</b><br/>
              {readinessLabels[area.readiness]}
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(145px,1fr))", gap: 8, marginTop: 14 }}>
            <div style={{ background: "#f7f5f1", borderRadius: 12, padding: 11 }}>家賃既知<br/><b>{area.knownRentUnits}住戸</b></div>
            <div style={{ background: "#f7f5f1", borderRadius: 12, padding: 11 }}>建物数<br/><b>{area.distinctBuildings}棟</b></div>
            <div style={{ background: "#f7f5f1", borderRadius: 12, padding: 11 }}>V3条件内<br/><b>{area.policyV3EligibleUnits}住戸</b></div>
            <div style={{ background: "#f7f5f1", borderRadius: 12, padding: 11 }}>30住戸まで<br/><b>あと {Math.max(0, 30 - area.knownRentUnits)}件</b></div>
            <div style={{ background: "#f7f5f1", borderRadius: 12, padding: 11 }}>15建物まで<br/><b>あと {Math.max(0, 15 - area.distinctBuildings)}棟</b></div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 12, marginTop: 14 }}>
            <div style={{ borderLeft: "4px solid #c28c31", paddingLeft: 12 }}><div style={{ fontSize: 11, color: "#776d60" }}>いま一番大きい不明</div><div style={{ marginTop: 4, lineHeight: 1.6 }}>{area.primaryUnknown}</div></div>
            <div style={{ borderLeft: "4px solid #2f7182", paddingLeft: 12 }}><div style={{ fontSize: 11, color: "#687379" }}>次のメガアクション</div><div style={{ marginTop: 4, lineHeight: 1.6, fontWeight: 700 }}>{area.nextAction}</div></div>
          </div>

          <details style={{ marginTop: 13 }}><summary style={{ cursor: "pointer", fontSize: 13, color: "#295e6b", fontWeight: 800 }}>判明している研究シグナルを見る</summary><ul style={{ marginBottom: 0, lineHeight: 1.65, fontSize: 13 }}>{area.signals.map((signal) => <li key={signal}>{signal}</li>)}</ul></details>
        </article>)}
      </section>

      {rows.length === 0 && <div style={{ background: "white", borderRadius: 15, padding: 20 }}>条件に合う地域がありません。</div>}
    </div>
  </main>;
}
