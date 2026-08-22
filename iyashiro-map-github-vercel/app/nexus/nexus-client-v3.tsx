"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import type { LocationProfileV2 } from "@/app/lib/location-profile/types";
import type { NexusPolicyAssessment } from "@/app/lib/nexus/policy";

type FormState = {
  propertyName: string;
  address: string;
  town: string;
  total: string;
  area: string;
  floor: string;
  currentness: "confirmed" | "stale" | "unknown";
  identity: "exact" | "partial" | "unknown";
};

const initial: FormState = { propertyName: "", address: "", town: "", total: "", area: "", floor: "", currentness: "unknown", identity: "unknown" };
const field: React.CSSProperties = { width: "100%", boxSizing: "border-box", padding: "12px 13px", border: "1px solid #d8d2ca", borderRadius: 11, background: "#fff", fontSize: 15 };

function yen(v: number | null | undefined) { return v == null ? "—" : `${Math.round(v).toLocaleString("ja-JP")}円`; }
function pct(v: number | null | undefined) { return v == null ? "—" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(1)}%`; }

export default function NexusClientV3() {
  const [form, setForm] = useState<FormState>(initial);
  const [result, setResult] = useState<NexusPolicyAssessment | null>(null);
  const [profile, setProfile] = useState<LocationProfileV2 | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setForm((x) => ({ ...x, [k]: v }));

  async function submit(e: FormEvent) {
    e.preventDefault(); setLoading(true); setError(null); setProfile(null);
    try {
      const town = form.town.trim();
      if (form.address.trim()) {
        const p = await fetch(`/api/profile?q=${encodeURIComponent(form.address.trim())}`);
        if (p.ok) {
          const data = await p.json() as LocationProfileV2;
          setProfile(data);
        }
      }
      const r = await fetch("/api/nexus", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...form, town, totalMonthlyFixedJPY: form.total, areaSquareMeters: form.area }) });
      const data = await r.json() as NexusPolicyAssessment & { message?: string };
      if (!r.ok) throw new Error(data.message ?? "判定できませんでした。");
      setResult(data);
    } catch (err) { setError(err instanceof Error ? err.message : "判定できませんでした。"); }
    finally { setLoading(false); }
  }

  return <main style={{ minHeight: "100vh", background: "#f6f4ef", color: "#201d1a", fontFamily: '-apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP",sans-serif' }}>
    <div style={{ maxWidth: 1080, margin: "0 auto", padding: "28px 18px 72px" }}>
      <header style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center", marginBottom: 18 }}>
        <div><div style={{ fontSize: 12, color: "#736d66" }}>LAND-FIRST / MARKET-SCALE</div><h1 style={{ margin: "3px 0", fontSize: 30 }}>NEXUS 物件判定 🧬🏠</h1></div>
        <div style={{ display: "flex", gap: 12, fontSize: 13 }}><Link href="/profile" style={{ color: "#245f70", fontWeight: 800, textDecoration: "none" }}>土地カルテ</Link><Link href="/" style={{ color: "#245f70", fontWeight: 800, textDecoration: "none" }}>地図</Link></div>
      </header>

      <section style={{ padding: 18, borderRadius: 18, background: "#132d36", color: "white", marginBottom: 16 }}>
        <div style={{ fontSize: 12, opacity: .72 }}>正式条件 V3</div>
        <div style={{ fontSize: 21, fontWeight: 850, marginTop: 5 }}>月の固定費17万円以内 ・ 1〜3階 ・ 15㎡以上</div>
        <div style={{ fontSize: 12, opacity: .78, lineHeight: 1.65, marginTop: 7 }}>㎡単価は参考値として表示しますが、除外条件にはしません。現在の270正式住戸では196件がこの条件を通過します。</div>
      </section>

      <section style={{ padding: 15, borderRadius: 15, background: "#fff7e6", border: "1px solid #ead49d", marginBottom: 16, fontSize: 13, lineHeight: 1.65 }}>
        <b>相場の扱いを修正しました。</b> 現在の内部相場は257住戸・69町丁目で、町丁目あたりの中央値は3住戸です。これは「相場確定」ではなく内部サンプルです。今後は外部公式統計＋数千件規模の市場データ＋厳密な住戸時系列の3層で補強します。
      </section>

      <form onSubmit={submit} style={{ background: "white", border: "1px solid #e4dfd8", borderRadius: 18, padding: 19 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(210px,1fr))", gap: 12 }}>
          <label>物件名<input style={field} value={form.propertyName} onChange={(e)=>set("propertyName",e.target.value)} /></label>
          <label>住所<input style={field} value={form.address} onChange={(e)=>set("address",e.target.value)} placeholder="土地カルテも確認" /></label>
          <label>町丁目<input style={field} value={form.town} onChange={(e)=>set("town",e.target.value)} placeholder="例：東が丘一丁目" /></label>
          <label>月の固定費合計<input style={field} inputMode="numeric" value={form.total} onChange={(e)=>set("total",e.target.value)} placeholder="家賃＋管理費等" /></label>
          <label>面積㎡<input style={field} inputMode="decimal" value={form.area} onChange={(e)=>set("area",e.target.value)} /></label>
          <label>階数<input style={field} inputMode="numeric" value={form.floor} onChange={(e)=>set("floor",e.target.value)} /></label>
          <label>掲載の新しさ<select style={field} value={form.currentness} onChange={(e)=>set("currentness",e.target.value as FormState["currentness"])}><option value="unknown">不明</option><option value="confirmed">現在掲載を確認</option><option value="stale">古い可能性</option></select></label>
          <label>住戸の同一性<select style={field} value={form.identity} onChange={(e)=>set("identity",e.target.value as FormState["identity"])}><option value="unknown">不明</option><option value="exact">住所・建物・号室一致</option><option value="partial">一部一致</option></select></label>
        </div>
        <button disabled={loading} style={{ width: "100%", marginTop: 14, padding: 13, border: 0, borderRadius: 11, background: "#245f70", color: "white", fontWeight: 850, fontSize: 15 }}>{loading ? "判定中…" : "条件・内部市場・土地を分けて確認する"}</button>
      </form>

      {error && <div style={{ marginTop: 14, padding: 13, background: "#fff0ea", borderRadius: 12 }}>{error}</div>}

      {result && <div style={{ marginTop: 16, display: "grid", gap: 14 }}>
        <section style={{ background: result.policyPass ? "#eaf5ee" : "#fff0ea", borderRadius: 17, padding: 18 }}><div style={{ fontSize: 12, opacity: .7 }}>物件条件</div><h2 style={{ margin: "4px 0" }}>{result.policyPass ? "正式条件を通過" : "正式条件外または未入力"}</h2><div>固定費㎡単価：<b>{yen(result.fixedRentPerSqm)}</b> / ㎡（参考値）</div></section>
        <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))", gap: 9 }}>{result.gates.map((g)=><article key={g.gateId} style={{ background: g.status === "fail" ? "#fff0ea" : g.status === "unknown" ? "#f1efeb" : "#eef6f0", borderRadius: 13, padding: 13 }}><b>{g.label}</b><div style={{ fontSize: 12, marginTop: 5 }}>{g.threshold}</div><div style={{ fontSize: 12, marginTop: 5 }}>{g.explanation}</div></article>)}</section>
        {result.marketContext && <section style={{ background: "white", border: "1px solid #dde5e7", borderRadius: 17, padding: 18 }}><div style={{ fontSize: 12, color: "#68757a" }}>内部募集サンプル / {result.marketContext.sampleQuality}</div><h2 style={{ margin: "4px 0 10px" }}>{result.marketContext.town}</h2><div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 8 }}><div>中央値<br/><b>{yen(result.marketContext.medianTotalJPY)}</b></div><div>中央50%<br/><b>{yen(result.marketContext.p25TotalJPY)}〜{yen(result.marketContext.p75TotalJPY)}</b></div><div>入力との差<br/><b>{pct(result.marketContext.differenceFromMedianPct)}</b></div><div>標本<br/><b>{result.marketContext.sampleCount}住戸 / {result.marketContext.uniqueBuildings}建物</b></div></div><p style={{ fontSize: 12, color: "#706961" }}>地域相場の確定値ではありません。外部公式統計と市場拡張で補強する前提です。</p></section>}
        <section style={{ background: "white", borderRadius: 17, padding: 18 }}><h2 style={{ marginTop: 0 }}>次に確認すること</h2><ol>{result.nextActions.map((x)=><li key={x} style={{ marginBottom: 6 }}>{x}</li>)}</ol></section>
      </div>}

      {profile && <section style={{ marginTop: 14, background: "white", border: "1px solid #e4dfd8", borderRadius: 17, padding: 18 }}><div style={{ fontSize: 12, color: "#716a63" }}>LAND-FIRST</div><h2 style={{ margin: "4px 0" }}>土地カルテ接続</h2><div>100mセル：<b>{profile.spatialContext.cellId}</b></div><p style={{ fontSize: 12, color: "#6d665f" }}>物件の安さと土地研究は合算しません。未調査は未調査として残します。</p><Link href={`/profile?q=${encodeURIComponent(form.address)}`} style={{ color: "#245f70", fontWeight: 800, textDecoration: "none" }}>詳しい土地カルテを開く →</Link></section>}
    </div>
  </main>;
}
