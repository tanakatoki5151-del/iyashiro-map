"use client";

import Link from "next/link";
import { FormEvent, useState, type CSSProperties } from "react";
import type { LocationLayer, LocationProfileV2 } from "@/app/lib/location-profile/types";
import type { NexusPolicyAssessment, NexusPolicyGate } from "@/app/lib/nexus/policy";

type FormState = {
  propertyName: string;
  address: string;
  town: string;
  sourceUrl: string;
  total: string;
  area: string;
  floor: string;
  currentness: "confirmed" | "stale" | "unknown";
  identity: "exact" | "partial" | "unknown";
};

const initialForm: FormState = {
  propertyName: "",
  address: "",
  town: "",
  sourceUrl: "",
  total: "",
  area: "",
  floor: "",
  currentness: "unknown",
  identity: "unknown",
};

const layerLabels: Record<string, string> = {
  placeGraph: "歴史・場所の履歴",
  v10Legacy: "土地履歴",
  v11Terrain: "歴史・地形",
  veil: "重大履歴・伝承",
  underland: "地下・水",
  limen: "祭祀・境界",
  ecoscape: "環境・植生",
  kaso: "建物・家相",
  landHistory: "土地利用の履歴",
  burial: "墓地・埋葬",
  facilities: "周辺施設",
};

const card: CSSProperties = {
  background: "#fff",
  border: "1px solid #e5e0d9",
  borderRadius: 18,
  padding: 20,
};

function fieldStyle(): CSSProperties {
  return {
    width: "100%",
    boxSizing: "border-box",
    marginTop: 5,
    padding: "12px 13px",
    borderRadius: 11,
    border: "1px solid #d5d0c9",
    background: "#fff",
    fontSize: 15,
    color: "#211e1b",
  };
}

function gateTone(gate: NexusPolicyGate) {
  if (!gate.hardGate) return { bg: "#eef3f5", border: "#cbd8dc", text: "#335965", mark: "参考" };
  if (gate.status === "pass") return { bg: "#eaf5ee", border: "#bddbc8", text: "#275d3b", mark: "通過" };
  if (gate.status === "fail") return { bg: "#fff0ea", border: "#e7c2b4", text: "#873e2d", mark: "条件外" };
  return { bg: "#f2f0ed", border: "#d8d3cc", text: "#635d56", mark: "未判定" };
}

function decisionLabel(state: NexusPolicyAssessment["decisionState"]) {
  if (state === "OUTSIDE_POLICY") return "今回の条件から外れています";
  if (state === "NEEDS_INPUT") return "入力が足りません";
  if (state === "READY_FOR_LAND_CHECK") return "条件通過。土地と契約条件を確認する段階です";
  return "条件通過。現在性と同一性の再確認が必要です";
}

function availabilityLabel(layer: LocationLayer) {
  if (layer.availability === "available") return "接続済み";
  if (layer.availability === "partial") return "部分接続";
  if (layer.availability === "not_applicable") return "対象外";
  if (layer.availability === "error") return "取得エラー";
  return "未接続";
}

function yen(value: number | null | undefined) {
  return value == null ? "—" : `${Math.round(value).toLocaleString("ja-JP")}円`;
}

function signedYen(value: number | null | undefined) {
  if (value == null) return "—";
  return `${value > 0 ? "+" : ""}${Math.round(value).toLocaleString("ja-JP")}円`;
}

function percent(value: number | null | undefined) {
  return value == null ? "—" : `${value > 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

export default function NexusClient() {
  const [form, setForm] = useState<FormState>(initialForm);
  const [assessment, setAssessment] = useState<NexusPolicyAssessment | null>(null);
  const [profile, setProfile] = useState<LocationProfileV2 | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [landError, setLandError] = useState<string | null>(null);

  const setField = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const requestAssessment = async (townOrAddress: string) => {
    const response = await fetch("/api/nexus", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        propertyName: form.propertyName,
        address: form.address,
        town: townOrAddress,
        sourceUrl: form.sourceUrl,
        totalMonthlyFixedJPY: form.total,
        areaSquareMeters: form.area,
        floor: form.floor,
        currentness: form.currentness,
        identity: form.identity,
      }),
    });
    const data = (await response.json()) as NexusPolicyAssessment & { message?: string };
    if (!response.ok) throw new Error(data.message ?? "物件判定を作成できませんでした。");
    return data;
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setLandError(null);
    setProfile(null);

    try {
      let marketQuery = form.town.trim() || form.address.trim();
      if (form.address.trim().length >= 2) {
        const landResponse = await fetch(`/api/profile?q=${encodeURIComponent(form.address.trim())}`);
        const landData = (await landResponse.json()) as LocationProfileV2 & { message?: string };
        if (landResponse.ok) {
          setProfile(landData);
          marketQuery = form.town.trim() || landData.location.matchedAddress || form.address.trim();
        } else {
          setLandError(landData.message ?? "土地カルテは取得できませんでした。");
        }
      }
      setAssessment(await requestAssessment(marketQuery));
    } catch (caught) {
      setAssessment(null);
      setError(caught instanceof Error ? caught.message : "物件判定を作成できませんでした。");
    } finally {
      setLoading(false);
    }
  };

  const layers = profile ? (Object.values(profile.layers).filter(Boolean) as LocationLayer[]) : [];
  const market = assessment?.marketContext;

  return (
    <main style={{ minHeight: "100vh", background: "#f6f4ef", color: "#211e1b", fontFamily: '-apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP",sans-serif' }}>
      <div style={{ maxWidth: 1120, margin: "0 auto", padding: "28px 18px 80px" }}>
        <header style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center", marginBottom: 22 }}>
          <div>
            <div style={{ color: "#6f6962", fontSize: 13 }}>土地を先に選び、物件と相場を後から重ねる</div>
            <h1 style={{ fontSize: 31, margin: "3px 0 0" }}>NEXUS 物件判定 🧬🏠</h1>
          </div>
          <div style={{ display: "flex", gap: 12, fontSize: 13 }}>
            <Link href="/profile" style={{ color: "#285f6d", textDecoration: "none", fontWeight: 700 }}>土地カルテ</Link>
            <Link href="/" style={{ color: "#285f6d", textDecoration: "none", fontWeight: 700 }}>地図</Link>
          </div>
        </header>

        <section style={{ padding: 20, borderRadius: 18, background: "#132d36", color: "#fff", marginBottom: 14 }}>
          <div style={{ fontSize: 13, opacity: 0.76 }}>正式な物件条件 V3</div>
          <div style={{ fontSize: 21, fontWeight: 800, marginTop: 4 }}>月の固定費17万円以内 ・ 1〜3階 ・ 15㎡以上</div>
          <div style={{ marginTop: 8, opacity: 0.8, fontSize: 12, lineHeight: 1.65 }}>㎡単価は比較用の参考値で、除外条件にはしません。土地研究を主軸70%、市場データ整備を30%で進めます。</div>
        </section>

        <section style={{ ...card, background: "#fff8e8", borderColor: "#ead7a1", marginBottom: 18 }}>
          <div style={{ color: "#796022", fontSize: 12 }}>市場データの現在地</div>
          <h2 style={{ margin: "4px 0 10px", fontSize: 20 }}>今の270住戸だけでは、地域相場の完成版とは言いません</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 9 }}>
            <div>掲載観測<br /><b>332件</b></div>
            <div>整理済み住戸<br /><b>270件</b></div>
            <div>家賃既知<br /><b>257件</b></div>
            <div>研究町丁目<br /><b>73地域</b></div>
            <div>中央値<br /><b>3住戸/地域</b></div>
            <div>5住戸未満<br /><b>59地域</b></div>
          </div>
          <div style={{ marginTop: 11, color: "#6c624f", fontSize: 12, lineHeight: 1.65 }}>町丁目の数字は探索用の内部サンプルです。初期目標はRaw 3,000件・Canonical 1,500件、次にRaw 5,000件・Canonical 2,500件へ広げます。</div>
        </section>

        <form onSubmit={submit} style={{ ...card, marginBottom: 18 }}>
          <h2 style={{ margin: "0 0 14px", fontSize: 19 }}>物件情報を入力</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 13 }}>
            <label style={{ fontSize: 12, color: "#6d665f" }}>物件名・部屋番号<input value={form.propertyName} onChange={(event) => setField("propertyName", event.target.value)} placeholder="例：○○マンション 203" style={fieldStyle()} /></label>
            <label style={{ fontSize: 12, color: "#6d665f" }}>住所<input value={form.address} onChange={(event) => setField("address", event.target.value)} placeholder="住所から土地カルテも取得" style={fieldStyle()} /></label>
            <label style={{ fontSize: 12, color: "#6d665f" }}>町丁目（任意）<input value={form.town} onChange={(event) => setField("town", event.target.value)} placeholder="例：東が丘一丁目" style={fieldStyle()} /></label>
            <label style={{ fontSize: 12, color: "#6d665f" }}>月の固定費合計<input inputMode="numeric" value={form.total} onChange={(event) => setField("total", event.target.value)} placeholder="家賃＋管理費など" style={fieldStyle()} /></label>
            <label style={{ fontSize: 12, color: "#6d665f" }}>広さ（㎡）<input inputMode="decimal" value={form.area} onChange={(event) => setField("area", event.target.value)} placeholder="例：28.71" style={fieldStyle()} /></label>
            <label style={{ fontSize: 12, color: "#6d665f" }}>階数<input inputMode="numeric" value={form.floor} onChange={(event) => setField("floor", event.target.value)} placeholder="1、2、3" style={fieldStyle()} /></label>
            <label style={{ fontSize: 12, color: "#6d665f" }}>掲載の新しさ<select value={form.currentness} onChange={(event) => setField("currentness", event.target.value as FormState["currentness"])} style={fieldStyle()}><option value="unknown">まだ不明</option><option value="confirmed">現在の掲載を確認済み</option><option value="stale">古い可能性が高い</option></select></label>
            <label style={{ fontSize: 12, color: "#6d665f" }}>同じ部屋だと確認できるか<select value={form.identity} onChange={(event) => setField("identity", event.target.value as FormState["identity"])} style={fieldStyle()}><option value="unknown">まだ不明</option><option value="exact">住所・建物・号室が一致</option><option value="partial">一部だけ一致</option></select></label>
            <label style={{ fontSize: 12, color: "#6d665f" }}>掲載URL（任意）<input value={form.sourceUrl} onChange={(event) => setField("sourceUrl", event.target.value)} placeholder="記録用。自動申込みはしません" style={fieldStyle()} /></label>
          </div>
          <button disabled={loading} style={{ marginTop: 16, width: "100%", padding: "13px 16px", border: 0, borderRadius: 12, background: "#225f6f", color: "#fff", fontSize: 15, fontWeight: 800, cursor: "pointer" }}>{loading ? "判定中…" : "物件・市場・土地を分けて判定する"}</button>
        </form>

        {error && <div style={{ padding: 15, borderRadius: 12, background: "#fff0ea", color: "#873e2d", marginBottom: 18 }}>{error}</div>}

        {assessment && (
          <>
            <section style={{ borderRadius: 18, padding: 20, background: assessment.policyPass ? "#eaf5ee" : assessment.decisionState === "NEEDS_INPUT" ? "#f2f0ed" : "#fff0ea", marginBottom: 18 }}>
              <div style={{ fontSize: 12, color: "#6d665f" }}>現在の結論</div>
              <h2 style={{ margin: "4px 0 5px", fontSize: 22 }}>{decisionLabel(assessment.decisionState)}</h2>
              <div style={{ color: "#655f58", fontSize: 13 }}>固定費の㎡単価：<b>{assessment.fixedRentPerSqm === null ? "—" : `${Math.round(assessment.fixedRentPerSqm).toLocaleString("ja-JP")}円/㎡`}</b>（参考値）</div>
            </section>

            <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(210px,1fr))", gap: 10, marginBottom: 18 }}>
              {assessment.gates.map((gate) => {
                const tone = gateTone(gate);
                return (
                  <article key={gate.gateId} style={{ background: tone.bg, border: `1px solid ${tone.border}`, borderRadius: 15, padding: 15 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}><strong>{gate.label}</strong><span style={{ fontSize: 11, color: tone.text, fontWeight: 800 }}>{tone.mark}</span></div>
                    <div style={{ marginTop: 6, color: "#68615a", fontSize: 12 }}>基準：{gate.threshold}</div>
                    <div style={{ marginTop: 6, fontSize: 13, lineHeight: 1.55 }}>{gate.explanation}</div>
                  </article>
                );
              })}
            </section>

            {market && (
              <section style={{ ...card, borderColor: "#d8e2e5", marginBottom: 18 }}>
                <div style={{ fontSize: 12, color: "#627078" }}>NEXUS内部の町丁目サンプル</div>
                <h2 style={{ margin: "4px 0 4px", fontSize: 21 }}>{market.town}：{market.comparisonLabel ?? "比較する固定費が未入力"}</h2>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 9, marginTop: 14 }}>
                  <div style={{ background: "#f4f8f9", borderRadius: 12, padding: 12 }}>単純中央値<br /><b>{yen(market.medianTotalJPY)}</b></div>
                  <div style={{ background: "#f4f8f9", borderRadius: 12, padding: 12 }}>中央50%の幅<br /><b>{yen(market.p25TotalJPY)}〜{yen(market.p75TotalJPY)}</b></div>
                  <div style={{ background: "#f4f8f9", borderRadius: 12, padding: 12 }}>入力物件との差<br /><b>{signedYen(market.differenceFromMedianJPY)} / {percent(market.differenceFromMedianPct)}</b></div>
                  <div style={{ background: "#f4f8f9", borderRadius: 12, padding: 12 }}>標本<br /><b>{market.sampleCount}住戸・{market.uniqueBuildings}建物</b><br /><span style={{ fontSize: 11 }}>{market.sampleQuality}</span></div>
                </div>
                <div style={{ marginTop: 12, color: "#6e6861", fontSize: 12, lineHeight: 1.65 }}>これは地域相場の完成版ではありません。標本、建物偏り、広さ、築年、徒歩などを確認し、外部公式統計で水準を検算します。</div>
              </section>
            )}

            <section style={{ ...card, marginBottom: 18 }}>
              <div style={{ fontSize: 12, color: "#627078" }}>外部公式ベンチマーク</div>
              <h2 style={{ margin: "4px 0 12px", fontSize: 20 }}>ネット相場は「答え」ではなく、全体水準の検算に使う</h2>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 10 }}>
                {assessment.externalBenchmarks.map((benchmark) => (
                  <a key={benchmark.benchmarkId} href={benchmark.sourceUrl} target="_blank" rel="noreferrer" style={{ padding: 14, borderRadius: 13, background: "#f7f5f1", border: "1px solid #ebe6df", color: "#211e1b", textDecoration: "none" }}>
                    <strong>{benchmark.publisher}</strong>
                    <div style={{ marginTop: 5, fontSize: 13 }}>{benchmark.scope}・{benchmark.period}</div>
                    {benchmark.askingMonthlyJPY !== null && <div style={{ marginTop: 5, fontSize: 13 }}>掲載：<b>{yen(benchmark.askingMonthlyJPY)}</b> / 反響：<b>{yen(benchmark.inquiryMonthlyJPY)}</b></div>}
                    <div style={{ marginTop: 7, color: "#6d665f", fontSize: 11, lineHeight: 1.55 }}>{benchmark.note}</div>
                  </a>
                ))}
              </div>
            </section>

            <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))", gap: 12, marginBottom: 18 }}>
              <article style={card}>
                <h2 style={{ margin: "0 0 10px", fontSize: 18 }}>次に確認すること</h2>
                <ol style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 7, fontSize: 13, lineHeight: 1.55 }}>{assessment.nextActions.map((action) => <li key={action}>{action}</li>)}</ol>
              </article>
              <article style={card}>
                <h2 style={{ margin: "0 0 10px", fontSize: 18 }}>NEXUSの現在地</h2>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(2,1fr)", gap: 8, fontSize: 13 }}>
                  <div>掲載観測<br /><b>{assessment.snapshot.rawObservations}</b></div>
                  <div>整理済み住戸<br /><b>{assessment.snapshot.canonicalUnits}</b></div>
                  <div>条件通過<br /><b>{assessment.snapshot.eligibleUnits}</b></div>
                  <div>主対象＋隣接<br /><b>{assessment.snapshot.primaryTargetUnits}</b></div>
                </div>
                <div style={{ marginTop: 10, color: "#756e67", fontSize: 12 }}>地域を先に選び、候補地の土地研究を閉じてから、物件の現在性と初期費用を確認します。</div>
              </article>
            </section>
          </>
        )}

        {landError && <div style={{ padding: 14, borderRadius: 12, background: "#fff7e6", color: "#785c1d", marginBottom: 18 }}>物件条件は判定済みですが、土地カルテは未取得です：{landError}</div>}

        {profile && (
          <section style={{ ...card, marginBottom: 18 }}>
            <div style={{ color: "#716a63", fontSize: 12 }}>土地カード</div>
            <h2 style={{ margin: "4px 0 6px", fontSize: 21 }}>{profile.location.matchedAddress ?? profile.location.query ?? "指定地点"}</h2>
            <div style={{ color: "#6d665f", fontSize: 13, marginBottom: 14 }}>100mセル <b style={{ color: "#211e1b" }}>{profile.spatialContext.cellId ?? "未確定"}</b> ・ 未調査や該当なしを安全とは扱いません</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 9 }}>
              {layers.map((layer) => (
                <div key={layer.layerId} style={{ padding: 12, borderRadius: 12, background: "#f7f5f1", border: "1px solid #ebe6df" }}>
                  <strong style={{ fontSize: 13 }}>{layerLabels[layer.layerId] ?? layer.project}</strong>
                  <div style={{ marginTop: 5, color: "#6d665f", fontSize: 12 }}>{availabilityLabel(layer)} ・ 確認事項 {layer.findings.length}件</div>
                </div>
              ))}
            </div>
            <Link href={`/profile?q=${encodeURIComponent(profile.location.matchedAddress ?? form.address)}`} style={{ display: "inline-block", marginTop: 14, color: "#225f6f", fontWeight: 800, textDecoration: "none", fontSize: 13 }}>詳しい土地カルテを開く →</Link>
          </section>
        )}

        {assessment && <section style={{ padding: 15, borderRadius: 14, background: "#ece9e3", color: "#625c55", fontSize: 12, lineHeight: 1.7 }}>{assessment.warnings.map((warning) => <div key={warning}>・{warning}</div>)}</section>}
      </div>
    </main>
  );
}
