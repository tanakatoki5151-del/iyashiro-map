"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

type Result = {
  sampleId: string;
  municipality: string;
  stratum: string;
  zoneNameJa: string;
  townChomeTop: string;
  cellId: string;
  lat: number;
  lng: number;
  lenses: {
    ryumyak: Record<string, unknown>;
    v10: { availability: string; title: string | null; originalScore: number | null; detailScore: number | null; confidence: number | null };
    underland: { availability: string; moistureAttentionClass?: string; confidence?: string; historicalWaterContext?: string };
    ecoscape: { availability: string; aggregateStateP25?: string; favorablePillarsP25?: number; cautionPillarsP25?: number; robustCandidateShare300m?: number; robustCandidateShare500m?: number };
    placegraph: { availability: string; indexStatus?: string; totalLinks?: number; absenceClaimAllowed: boolean };
  };
  researchQueueReasons: string[];
};

type ResponseBody = {
  frame: { totalSamples: number; municipalityCount: number; samplesPerMunicipality: number; municipalities: string[]; strata: string[]; filteredSamples: number };
  pagination: { offset: number; limit: number; returned: number; nextOffset: number | null };
  results: Result[];
};

const STRATA: Record<string, string> = {
  A_LOCAL_TOP: "龍脈・自治体内上位",
  B_UPPER_QUARTILE: "龍脈・上位帯",
  C_LOCAL_MEDIAN: "龍脈・中位",
  D_UNCERTAINTY_REVIEW: "不確実・反証確認",
  E_LOCAL_BOTTOM_CONTROL: "龍脈・低位対照",
  F_NO_RYUMYAK_ELIGIBLE_ZONE_CONTROL: "龍脈ゾーンなし対照",
};

const card: React.CSSProperties = { padding: 12, borderRadius: 12, border: "1px solid #e4e0d7", background: "#f7f6f1", fontSize: 12, lineHeight: 1.6 };
const select: React.CSSProperties = { width: "100%", marginTop: 5, padding: "11px 12px", borderRadius: 10, border: "1px solid #d7d2c9", background: "white" };

function fmt(value: unknown, digits = 1) { return typeof value === "number" ? value.toFixed(digits) : "—"; }
function pct(value: unknown) { return typeof value === "number" ? `${Math.round(value * 100)}%` : "—"; }
function Pill({ children }: { children: React.ReactNode }) { return <span style={{ display: "inline-block", padding: "4px 8px", borderRadius: 999, background: "#e9f0ef", color: "#31515a", fontSize: 11, fontWeight: 800 }}>{children}</span>; }

export default function DiscoveryClient() {
  const [data, setData] = useState<ResponseBody | null>(null);
  const [municipality, setMunicipality] = useState("");
  const [stratum, setStratum] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (offset = 0, append = false) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ offset: String(offset), limit: "20" });
      if (municipality) params.set("municipality", municipality);
      if (stratum) params.set("stratum", stratum);
      const response = await fetch(`/api/nexus/discovery-wave1?${params}`);
      const payload = (await response.json()) as ResponseBody & { message?: string };
      if (!response.ok) throw new Error(payload.message ?? "探索データを取得できませんでした。");
      setData((current) => append && current ? { ...payload, results: [...current.results, ...payload.results] } : payload);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "探索データを取得できませんでした。");
    } finally {
      setLoading(false);
    }
  }, [municipality, stratum]);

  useEffect(() => { void load(); }, [load]);

  return <main style={{ minHeight: "100vh", background: "#f4f1e9", color: "#201f1b", fontFamily: '-apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP",sans-serif' }}>
    <div style={{ maxWidth: 1240, margin: "0 auto", padding: "28px 18px 80px" }}>
      <header style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap", marginBottom: 18 }}>
        <div>
          <div style={{ color: "#68716f", fontSize: 12, fontWeight: 850 }}>PHASE15・FULL DOMAIN DISCOVERY</div>
          <h1 style={{ margin: "5px 0 7px", fontSize: 32 }}>全域240地点の比較探索 🧭</h1>
          <div style={{ color: "#6b6760", maxWidth: 820, fontSize: 13, lineHeight: 1.7 }}>48自治体を5地点ずつ比較する研究標本です。居住おすすめ順位ではなく、次に深掘る地点を発見するための画面です。</div>
        </div>
        <div style={{ display: "flex", gap: 10 }}><Link href="/nexus" style={{ color: "#225f6f", fontWeight: 800, textDecoration: "none" }}>物件判定</Link><Link href="/nexus/areas" style={{ color: "#766b58", fontWeight: 750, textDecoration: "none" }}>旧25地域監査</Link></div>
      </header>

      <section style={{ padding: 19, borderRadius: 18, background: "#173d49", color: "white", marginBottom: 14 }}>
        <div style={{ fontSize: 12, opacity: .72 }}>探索契約</div>
        <h2 style={{ margin: "4px 0 7px", fontSize: 21 }}>旧P0を優先しない。龍脈上位だけを見ない。総合点を作らない。</h2>
        <div style={{ fontSize: 12, lineHeight: 1.65, opacity: .82 }}>龍脈、V10、地下・水、環境、PLACEGRAPHを独立表示します。不明は安全に変換せず、家賃や在庫は土地の第一次探索順位に使いません。</div>
      </section>

      {data && <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(145px,1fr))", gap: 8, marginBottom: 14 }}>
        {[["比較地点", `${data.frame.totalSamples}`], ["自治体", `${data.frame.municipalityCount}`], ["自治体ごと", `${data.frame.samplesPerMunicipality}層`], ["絞込み後", `${data.frame.filteredSamples}`]].map(([label, value]) => <div key={label} style={{ ...card, background: "white" }}><span style={{ color: "#777167" }}>{label}</span><strong style={{ display: "block", marginTop: 3, fontSize: 19 }}>{value}</strong></div>)}
      </section>}

      <section style={{ ...card, background: "white", padding: 15, marginBottom: 15, display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 12 }}>
        <label style={{ fontSize: 12, color: "#68635c" }}>自治体<select value={municipality} onChange={(e) => setMunicipality(e.target.value)} style={select}><option value="">全48自治体</option>{data?.frame.municipalities.map((name) => <option key={name}>{name}</option>)}</select></label>
        <label style={{ fontSize: 12, color: "#68635c" }}>比較層<select value={stratum} onChange={(e) => setStratum(e.target.value)} style={select}><option value="">全比較層</option>{data?.frame.strata.map((name) => <option key={name} value={name}>{STRATA[name] ?? name}</option>)}</select></label>
      </section>

      {error && <div style={{ padding: 14, borderRadius: 12, background: "#fff0ea", color: "#883e2d", marginBottom: 14 }}>{error}</div>}
      {loading && !data && <div style={{ padding: 22, textAlign: "center" }}>全域比較を読み込み中…</div>}

      <section style={{ display: "grid", gap: 13 }}>
        {data?.results.map((item) => {
          const r = item.lenses.ryumyak;
          const ryumyakAvailable = r.availability === "available";
          return <article key={item.sampleId} style={{ padding: 17, borderRadius: 18, background: "white", border: "1px solid #dedad1" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <div><div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}><Pill>{item.sampleId}</Pill><Pill>{item.municipality}</Pill><Pill>{STRATA[item.stratum] ?? item.stratum}</Pill></div><h2 style={{ margin: "8px 0 4px", fontSize: 19 }}>{item.zoneNameJa}</h2><div style={{ color: "#777168", fontSize: 12 }}>{item.townChomeTop} ・ {item.cellId}</div></div>
              <Link href={`/profile?lat=${item.lat}&lng=${item.lng}`} style={{ color: "#225f6f", fontSize: 12, fontWeight: 800, textDecoration: "none" }}>地点カルテ →</Link>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(185px,1fr))", gap: 8, marginTop: 13 }}>
              <div style={{ ...card, background: "#f5f1e8" }}><b>RYUMYAK・独立レンズ</b><br />{ryumyakAvailable ? <>順位 {String(r.rank)} / 3,327<br />独立値 {fmt(r.score)}<br />龍 {fmt(r.long25)}・砂 {fmt(r.sha20)}・水 {fmt(r.shui30)}・穴/明堂 {fmt(r.xueMingtang25)}</> : <>候補ゾーンなしの対照地点。良し悪しの結論ではありません。</>}</div>
              <div style={card}><b>V10・地形仮説</b><br />{item.lenses.v10.title ?? "未接続"}<br />原典 {item.lenses.v10.originalScore ?? "—"}・詳細 {item.lenses.v10.detailScore ?? "—"}<br />信頼度 {item.lenses.v10.confidence ?? "—"}</div>
              <div style={{ ...card, background: "#edf5f6" }}><b>UNDERLAND・地下と水</b><br />{item.lenses.underland.moistureAttentionClass ?? "不明"}<br />歴史水文脈 {item.lenses.underland.historicalWaterContext ?? "—"}<br />資料確度 {item.lenses.underland.confidence ?? "—"}</div>
              <div style={{ ...card, background: "#eef5ed" }}><b>ECOSCAPE・環境</b><br />{item.lenses.ecoscape.aggregateStateP25 ?? "不明"}<br />好条件 {item.lenses.ecoscape.favorablePillarsP25 ?? "—"}・注意 {item.lenses.ecoscape.cautionPillarsP25 ?? "—"}<br />頑健候補率 300m {pct(item.lenses.ecoscape.robustCandidateShare300m)} / 500m {pct(item.lenses.ecoscape.robustCandidateShare500m)}</div>
              <div style={{ ...card, background: "#f3f0f5" }}><b>PLACEGRAPH・場所履歴</b><br />{item.lenses.placegraph.indexStatus ?? "部分接続"}<br />索引リンク {item.lenses.placegraph.totalLinks ?? 0}件<br />0件は不存在・安全を意味しません。</div>
            </div>

            <details style={{ marginTop: 11 }}><summary style={{ cursor: "pointer", color: "#38616b", fontSize: 12, fontWeight: 800 }}>次の研究キュー {item.researchQueueReasons.length}件</summary><ul style={{ margin: "7px 0 0", paddingLeft: 19, color: "#6c665e", fontSize: 12, lineHeight: 1.65 }}>{item.researchQueueReasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></details>
          </article>;
        })}
      </section>

      {data && data.pagination.nextOffset !== null && <button disabled={loading} onClick={() => void load(data.pagination.nextOffset ?? 0, true)} style={{ marginTop: 15, width: "100%", padding: 13, border: 0, borderRadius: 12, background: "#225f6f", color: "white", fontWeight: 850 }}>{loading ? "読み込み中…" : "次の20地点を表示"}</button>}

      <div style={{ marginTop: 18, padding: 14, borderRadius: 13, background: "#e9e5dc", color: "#625d55", fontSize: 12, lineHeight: 1.7 }}>この画面は探索標本です。居住順位、推薦、安全宣言ではありません。Wave2は複数レンズの一致、不一致、不明率から研究対象を選びます。</div>
    </div>
  </main>;
}
