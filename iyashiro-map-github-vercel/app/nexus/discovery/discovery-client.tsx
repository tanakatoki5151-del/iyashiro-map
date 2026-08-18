"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

type DiscoveryResult = {
  sampleId: string;
  municipality: string;
  metro: string;
  stratum: string;
  zoneNameJa: string;
  townChomeTop: string;
  cellId: string;
  lat: number;
  lng: number;
  sampleRole: string;
  residencePriority: null;
  residenceRecommendation: null;
  lenses: {
    ryumyak: Record<string, unknown>;
    v10: {
      availability: string;
      title: string | null;
      originalScore: number | null;
      detailScore: number | null;
      confidence: number | null;
    };
    underland: {
      availability: string;
      moistureAttentionClass?: string;
      confidence?: string;
      historicalWaterContext?: string;
      coverageStatus?: string;
    };
    ecoscape: {
      availability: string;
      aggregateStateP25?: string;
      robustEnvironmentalCandidate?: boolean;
      thresholdStable?: boolean;
      favorablePillarsP25?: number;
      cautionPillarsP25?: number;
      robustCandidateShare300m?: number;
      robustCandidateShare500m?: number;
    };
    placegraph: {
      availability: string;
      indexStatus?: string;
      totalLinks?: number;
      featureQueryableLinks?: number;
      absenceClaimAllowed: boolean;
    };
  };
  researchQueueReasons: string[];
};

type DiscoveryResponse = {
  schemaVersion: string;
  waveVersion: string;
  asOfJST: string;
  semantics: {
    residenceRanking: boolean;
    syntheticTotalScore: boolean;
    marketInfluenceOnLandDiscovery: string;
    ryumyakRole: string;
    unknownMeansSafe: boolean;
  };
  notes: readonly string[];
  frame: {
    totalSamples: number;
    municipalityCount: number;
    samplesPerMunicipality: number;
    municipalities: string[];
    strata: string[];
    filteredSamples: number;
  };
  pagination: {
    offset: number;
    limit: number;
    returned: number;
    nextOffset: number | null;
  };
  results: DiscoveryResult[];
};

const STRATUM_LABELS: Record<string, string> = {
  A_LOCAL_TOP: "龍脈・自治体内上位",
  B_UPPER_QUARTILE: "龍脈・上位帯",
  C_LOCAL_MEDIAN: "龍脈・中位",
  D_UNCERTAINTY_REVIEW: "不確実・反証確認",
  E_LOCAL_BOTTOM_CONTROL: "龍脈・低位対照",
  F_NO_RYUMYAK_ELIGIBLE_ZONE_CONTROL: "龍脈ゾーンなし対照",
};

const STRATUM_HELP: Record<string, string> = {
  A_LOCAL_TOP: "自治体内で龍脈レンズが最も高い地点。良い土地確定ではありません。",
  B_UPPER_QUARTILE: "上位帯から選んだ比較地点。",
  C_LOCAL_MEDIAN: "自治体内の中間付近。上位だけを見る偏りを防ぎます。",
  D_UNCERTAINTY_REVIEW: "水形状や境界に敏感な地点。理論の反証確認を優先します。",
  E_LOCAL_BOTTOM_CONTROL: "自治体内の低位地点。上位との差が他レンズにも出るか検証します。",
  F_NO_RYUMYAK_ELIGIBLE_ZONE_CONTROL: "龍脈Atlasに候補ゾーンがない江東区の対照地点です。",
};

function pill(text: string, background = "#eef3f4", color = "#31515a") {
  return <span style={{ display: "inline-block", padding: "4px 8px", borderRadius: 999, background, color, fontSize: 11, fontWeight: 750 }}>{text}</span>;
}

function percent(value: unknown) {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "—";
}

function number(value: unknown, digits = 1) {
  return typeof value === "number" ? value.toFixed(digits) : "—";
}

function LensCard({ title, children, tone = "#f6f7f4" }: { title: string; children: React.ReactNode; tone?: string }) {
  return <div style={{ padding: 12, borderRadius: 13, background: tone, border: "1px solid #e5e4de", minHeight: 112 }}>
    <div style={{ fontSize: 12, color: "#626862", fontWeight: 800, marginBottom: 7 }}>{title}</div>
    <div style={{ fontSize: 12, lineHeight: 1.6, color: "#2d302d" }}>{children}</div>
  </div>;
}

export default function DiscoveryClient() {
  const [data, setData] = useState<DiscoveryResponse | null>(null);
  const [municipality, setMunicipality] = useState("");
  const [stratum, setStratum] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (nextOffset = 0, append = false) => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ offset: String(nextOffset), limit: "20" });
    if (municipality) params.set("municipality", municipality);
    if (stratum) params.set("stratum", stratum);
    try {
      const response = await fetch(`/api/nexus/discovery-wave1?${params.toString()}`);
      const payload = (await response.json()) as DiscoveryResponse & { message?: string };
      if (!response.ok) throw new Error(payload.message ?? "探索データを取得できませんでした。");
      setData((current) => append && current
        ? { ...payload, results: [...current.results, ...payload.results] }
        : payload);
      setOffset(nextOffset);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "探索データを取得できませんでした。");
    } finally {
      setLoading(false);
    }
  }, [municipality, stratum]);

  useEffect(() => { void load(0, false); }, [load]);

  const summary = useMemo(() => {
    if (!data) return null;
    const visible = data.results;
    return {
      placegraphIndexed: visible.filter((item) => (item.lenses.placegraph.totalLinks ?? 0) > 0).length,
      underlandAvailable: visible.filter((item) => item.lenses.underland.availability === "available").length,
      ecoscapeAvailable: visible.filter((item) => item.lenses.ecoscape.availability === "available").length,
      v10Available: visible.filter((item) => item.lenses.v10.availability === "available").length,
    };
  }, [data]);

  return <main style={{ minHeight: "100vh", background: "#f4f1e9", color: "#201f1b", fontFamily: '-apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP",sans-serif' }}>
    <div style={{ maxWidth: 1240, margin: "0 auto", padding: "28px 18px 80px" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, marginBottom: 18, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 12, color: "#68716f", letterSpacing: ".08em", fontWeight: 800 }}>PHASE15・FULL DOMAIN DISCOVERY</div>
          <h1 style={{ margin: "5px 0 7px", fontSize: 32 }}>全域240地点の比較探索 🧭</h1>
          <div style={{ color: "#6b6760", lineHeight: 1.65, maxWidth: 800, fontSize: 13 }}>東京23区・横浜・川崎の48自治体を各5地点ずつ比較します。これは居住おすすめ順位ではなく、次に深掘る土地を発見する研究標本です。</div>
        </div>
        <div style={{ display: "flex", gap: 9, flexWrap: "wrap" }}>
          <Link href="/nexus" style={{ color: "#225f6f", textDecoration: "none", fontWeight: 800 }}>物件判定へ</Link>
          <Link href="/nexus/areas" style={{ color: "#766b58", textDecoration: "none", fontWeight: 750 }}>旧25地域監査</Link>
        </div>
      </header>

      <section style={{ background: "#173d49", color: "white", padding: 20, borderRadius: 18, marginBottom: 14 }}>
        <div style={{ fontSize: 13, opacity: .74 }}>探索契約</div>
        <h2 style={{ margin: "4px 0 8px", fontSize: 21 }}>旧P0を優先しない。龍脈上位だけを見ない。総合点を作らない。</h2>
        <div style={{ opacity: .8, lineHeight: 1.65, fontSize: 12 }}>龍脈、V10、地下・水、環境、PLACEGRAPHを独立表示します。不明は安全に変換せず、家賃や物件数は土地の第一次探索順位に使いません。</div>
      </section>

      {data && <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 9, marginBottom: 14 }}>
        {[
          ["比較地点", `${data.frame.totalSamples}地点`],
          ["自治体", `${data.frame.municipalityCount}自治体`],
          ["1自治体", `${data.frame.samplesPerMunicipality}層`],
          ["現在の絞込み", `${data.frame.filteredSamples}地点`],
          ["V10接続・表示分", `${summary?.v10Available ?? 0}/${data.results.length}`],
          ["地下接続・表示分", `${summary?.underlandAvailable ?? 0}/${data.results.length}`],
        ].map(([label, value]) => <div key={label} style={{ background: "#fff", border: "1px solid #e3dfd5", borderRadius: 14, padding: 13 }}><div style={{ fontSize: 11, color: "#777167" }}>{label}</div><strong style={{ display: "block", marginTop: 4, fontSize: 18 }}>{value}</strong></div>)}
      </section>}

      <section style={{ background: "white", border: "1px solid #e3dfd5", borderRadius: 17, padding: 16, marginBottom: 16 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 12 }}>
          <label style={{ fontSize: 12, color: "#68635c" }}>自治体
            <select value={municipality} onChange={(event) => { setMunicipality(event.target.value); setOffset(0); }} style={{ width: "100%", marginTop: 5, padding: "11px 12px", borderRadius: 10, border: "1px solid #d7d2c9", background: "white" }}>
              <option value="">全48自治体</option>
              {data?.frame.municipalities.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
          <label style={{ fontSize: 12, color: "#68635c" }}>比較層
            <select value={stratum} onChange={(event) => { setStratum(event.target.value); setOffset(0); }} style={{ width: "100%", marginTop: 5, padding: "11px 12px", borderRadius: 10, border: "1px solid #d7d2c9", background: "white" }}>
              <option value="">全比較層</option>
              {data?.frame.strata.map((name) => <option key={name} value={name}>{STRATUM_LABELS[name] ?? name}</option>)}
            </select>
          </label>
        </div>
        {stratum && <div style={{ marginTop: 10, padding: 10, borderRadius: 10, background: "#f3f1eb", fontSize: 12, color: "#686158" }}>{STRATUM_HELP[stratum]}</div>}
      </section>

      {error && <div style={{ padding: 14, borderRadius: 12, background: "#fff0ea", color: "#883e2d", marginBottom: 14 }}>{error}</div>}
      {loading && !data && <div style={{ padding: 22, textAlign: "center", color: "#6c6860" }}>全域比較を読み込み中…</div>}

      <section style={{ display: "grid", gap: 14 }}>
        {data?.results.map((item) => {
          const ryumyak = item.lenses.ryumyak;
          const ryumyakAvailable = ryumyak.availability === "available";
          return <article key={item.sampleId} style={{ background: "white", border: "1px solid #dedad1", borderRadius: 18, padding: 17 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "flex-start" }}>
              <div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 7 }}>{pill(item.sampleId)}{pill(item.municipality, "#e8f1f1")}{pill(STRATUM_LABELS[item.stratum] ?? item.stratum, "#f2ecdf", "#6b5837")}</div>
                <h2 style={{ margin: 0, fontSize: 19 }}>{item.zoneNameJa}</h2>
                <div style={{ marginTop: 5, color: "#777168", fontSize: 12 }}>代表町丁目：{item.townChomeTop} ・ 100mセル {item.cellId}</div>
              </div>
              <Link href={`/profile?lat=${item.lat}&lng=${item.lng}`} style={{ color: "#225f6f", textDecoration: "none", fontSize: 12, fontWeight: 800 }}>地点カルテを開く →</Link>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))", gap: 9, marginTop: 14 }}>
              <LensCard title="RYUMYAK・独立レンズ" tone="#f5f1e8">
                {ryumyakAvailable ? <><b>順位 {String(ryumyak.rank)} / 3,327</b><br />独立スコア {number(ryumyak.score)}<br />龍 {number(ryumyak.long25)}・砂 {number(ryumyak.sha20)}・水 {number(ryumyak.shui30)}・穴/明堂 {number(ryumyak.xueMingtang25)}<br /><span style={{ color: "#6f6658" }}>{String(ryumyak.decisionConfidence)}</span></> : <>候補ゾーンなしの対照地点。龍脈が悪いという意味でも、土地が不適という意味でもありません。</>}
              </LensCard>
              <LensCard title="V10・地形仮説">
                <b>{item.lenses.v10.title ?? "未接続"}</b><br />原典 {item.lenses.v10.originalScore ?? "—"}・詳細 {item.lenses.v10.detailScore ?? "—"}<br />信頼度 {item.lenses.v10.confidence ?? "—"}
              </LensCard>
              <LensCard title="UNDERLAND・地下と水" tone="#edf5f6">
                <b>{item.lenses.underland.moistureAttentionClass ?? "不明"}</b><br />地下水帯 {item.lenses.underland.historicalWaterContext ?? "—"}<br />資料確度 {item.lenses.underland.confidence ?? "—"}
              </LensCard>
              <LensCard title="ECOSCAPE・環境" tone="#eef5ed">
                <b>{item.lenses.ecoscape.aggregateStateP25 ?? "不明"}</b><br />好条件 {item.lenses.ecoscape.favorablePillarsP25 ?? "—"}・注意 {item.lenses.ecoscape.cautionPillarsP25 ?? "—"}<br />頑健候補率 300m {percent(item.lenses.ecoscape.robustCandidateShare300m)} / 500m {percent(item.lenses.ecoscape.robustCandidateShare500m)}
              </LensCard>
              <LensCard title="PLACEGRAPH・場所履歴" tone="#f3f0f5">
                <b>{item.lenses.placegraph.indexStatus ?? "部分接続"}</b><br />索引リンク {item.lenses.placegraph.totalLinks ?? 0}件<br />索引なしは、歴史的に何もない・安全という意味ではありません。
              </LensCard>
            </div>

            <details style={{ marginTop: 12 }}>
              <summary style={{ cursor: "pointer", color: "#38616b", fontSize: 12, fontWeight: 800 }}>次の研究キュー {item.researchQueueReasons.length}件</summary>
              <ul style={{ margin: "8px 0 0", paddingLeft: 19, color: "#6c665e", fontSize: 12, lineHeight: 1.65 }}>{item.researchQueueReasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
            </details>
          </article>;
        })}
      </section>

      {data?.pagination.nextOffset !== null && <button disabled={loading} onClick={() => void load(data.pagination.nextOffset ?? offset + 20, true)} style={{ marginTop: 16, width: "100%", padding: 13, border: 0, borderRadius: 12, background: "#225f6f", color: "white", fontWeight: 850, cursor: "pointer" }}>{loading ? "読み込み中…" : "次の20地点を表示"}</button>}

      <section style={{ marginTop: 18, padding: 15, borderRadius: 14, background: "#e9e5dc", color: "#625d55", fontSize: 12, lineHeight: 1.7 }}>
        ・この画面は探索標本です。順位、推薦、土地の安全宣言ではありません。<br />
        ・旧P0/P1は検証履歴として残しますが、ここでは優先権を持ちません。<br />
        ・Wave2は、複数レンズの一致、不一致、不明の多さを根拠に研究対象を選びます。
      </section>
    </div>
  </main>;
}
