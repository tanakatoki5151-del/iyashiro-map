"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import type { LocationLayer, LocationProfileV2 } from "@/app/lib/location-profile/types";

type LegacyRuntime = {
  theory?: { score?: number; label?: string; internalConfidence?: number };
  modern?: { score?: number; label?: string; completeness?: number };
  combined?: { score?: number; label?: string; provisional?: boolean; reasons?: string[] };
};

const layerLabels: Record<string, string> = {
  placeGraph: "歴史・場所の履歴",
  v10Legacy: "V10 土地履歴",
  v11Terrain: "V11 歴史・地形",
  veil: "重大履歴・伝承",
  underland: "地下・水",
  limen: "祭祀・境界",
  ecoscape: "環境・植生",
  kaso: "建物・家相",
};

function availabilityLabel(layer: LocationLayer) {
  if (layer.availability === "available") return "接続済み";
  if (layer.availability === "partial") return "部分接続";
  if (layer.availability === "not_applicable") return "対象外";
  if (layer.availability === "error") return "取得エラー";
  return "未接続";
}

function ScoreCard({ title, value, label, sub }: { title: string; value?: number; label?: string; sub?: string }) {
  return (
    <div style={{ border: "1px solid #e6e1da", borderRadius: 16, padding: 16, background: "#fff" }}>
      <div style={{ color: "#716b64", fontSize: 12 }}>{title}</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 5 }}>
        <strong style={{ fontSize: 30 }}>{value ?? "—"}</strong>
        {typeof value === "number" && <span style={{ color: "#817a72" }}>/100</span>}
      </div>
      <div style={{ fontWeight: 650 }}>{label ?? "判定なし"}</div>
      {sub && <div style={{ color: "#817a72", fontSize: 12, marginTop: 6 }}>{sub}</div>}
    </div>
  );
}

export default function ProfileClient() {
  const [query, setQuery] = useState("東京都豊島区目白五丁目8-1");
  const [profile, setProfile] = useState<LocationProfileV2 | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (q: string) => {
    if (q.trim().length < 2) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/profile?q=${encodeURIComponent(q.trim())}`);
      const data = (await response.json()) as LocationProfileV2 & { message?: string };
      if (!response.ok) throw new Error(data.message ?? "土地カルテを取得できませんでした。");
      setProfile(data);
      const url = new URL(window.location.href);
      url.searchParams.set("q", q.trim());
      window.history.replaceState(null, "", url);
    } catch (caught) {
      setProfile(null);
      setError(caught instanceof Error ? caught.message : "土地カルテを取得できませんでした。");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("q");
    const initial = q?.trim() || query;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- URL query initializes the controlled field after hydration
    if (q) setQuery(q);
    void run(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void run(query);
  };

  const legacy = (profile?.legacyRuntime ?? {}) as LegacyRuntime;
  const layers = profile ? Object.values(profile.layers).filter(Boolean) as LocationLayer[] : [];

  return (
    <main style={{ minHeight: "100vh", background: "#f7f5f1", color: "#201d1a", fontFamily: '-apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP",sans-serif' }}>
      <div style={{ maxWidth: 1040, margin: "0 auto", padding: "28px 18px 80px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center", marginBottom: 24 }}>
          <div>
            <div style={{ fontSize: 13, color: "#6e6862" }}>イヤシロ土地判定</div>
            <h1 style={{ margin: "2px 0 0", fontSize: 30 }}>土地カルテ 🗺️</h1>
          </div>
          <Link href="/" style={{ color: "#2a6676", textDecoration: "none", fontSize: 14 }}>← 地図へ戻る</Link>
        </div>

        <form onSubmit={submit} style={{ display: "flex", gap: 8, marginBottom: 24 }}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="住所を入力"
            style={{ flex: 1, minWidth: 0, padding: "13px 14px", borderRadius: 12, border: "1px solid #d6d0c8", fontSize: 16, background: "#fff" }}
          />
          <button disabled={loading} style={{ padding: "0 18px", border: 0, borderRadius: 12, background: "#225f6f", color: "#fff", fontWeight: 700 }}>
            {loading ? "解析中…" : "調べる"}
          </button>
        </form>

        {error && <div style={{ padding: 16, borderRadius: 12, background: "#fff1ec", color: "#9a412f", marginBottom: 20 }}>{error}</div>}

        {profile && (
          <>
            <section style={{ background: "#fff", border: "1px solid #e6e1da", borderRadius: 18, padding: 20, marginBottom: 18 }}>
              <div style={{ color: "#716b64", fontSize: 12 }}>検索地点</div>
              <h2 style={{ margin: "4px 0 6px", fontSize: 22 }}>{profile.location.matchedAddress ?? profile.location.query ?? "指定地点"}</h2>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, fontSize: 13, color: "#6e6862" }}>
                <span>100mセル <b style={{ color: "#201d1a" }}>{profile.spatialContext.cellId}</b></span>
                <span>座標 {profile.location.lat.toFixed(6)}, {profile.location.lng.toFixed(6)}</span>
                <span>精度 {profile.queryAnchor.uncertaintyMeters ?? "—"}m</span>
              </div>
            </section>

            <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 10, marginBottom: 18 }}>
              <ScoreCard title="イヤシロ仮説" value={legacy.theory?.score} label={legacy.theory?.label} sub={legacy.theory?.internalConfidence !== undefined ? `信頼度 ${legacy.theory.internalConfidence}%` : undefined} />
              <ScoreCard title="現代土地条件" value={legacy.modern?.score} label={legacy.modern?.label} sub={legacy.modern?.completeness !== undefined ? `データ充足 ${legacy.modern.completeness}%` : undefined} />
              <ScoreCard title="現在の総合" value={legacy.combined?.score} label={legacy.combined?.label} sub={legacy.combined?.provisional ? "暫定評価" : "主要データ取得済み"} />
            </section>

            <section style={{ background: "#fff", border: "1px solid #e6e1da", borderRadius: 18, padding: 20, marginBottom: 18 }}>
              <h2 style={{ margin: "0 0 5px", fontSize: 19 }}>この土地について分かっていること</h2>
              <p style={{ margin: "0 0 16px", color: "#716b64", fontSize: 13 }}>
                研究プロジェクトの事実は点数へ直接加算せず、確認済み・候補・未調査を分けて表示します。
              </p>
              <div style={{ display: "grid", gap: 10 }}>
                {layers.map((layer) => (
                  <article key={layer.layerId} style={{ border: "1px solid #ebe6df", borderRadius: 14, padding: 14 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
                      <strong>{layerLabels[layer.layerId] ?? layer.project}</strong>
                      <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 999, background: layer.availability === "available" ? "#e9f4ed" : layer.availability === "partial" ? "#fff4da" : "#efeeec", color: "#5f5953" }}>
                        {availabilityLabel(layer)}
                      </span>
                    </div>
                    {layer.layerId === "placeGraph" && (
                      <div style={{ marginTop: 8, fontSize: 13 }}>
                        PLACEGRAPH状態: <b>{String(layer.metadata?.cellClosureStatus ?? "UNKNOWN")}</b>
                        {typeof layer.metadata?.rawLinkCount === "number" && <> ・既知relation {String(layer.metadata.rawLinkCount)}件</>}
                      </div>
                    )}
                    {layer.findings.length > 0 && (
                      <div style={{ marginTop: 9, display: "grid", gap: 7 }}>
                        {layer.findings.map((finding) => (
                          <div key={finding.findingId} style={{ background: "#f8f6f2", borderRadius: 10, padding: 10, fontSize: 13 }}>
                            <b>{finding.title}</b> <span style={{ color: "#786f67" }}>({finding.status} / {finding.evidenceMaturity})</span>
                            <div style={{ color: "#625d57", marginTop: 3 }}>{finding.explanation}</div>
                          </div>
                        ))}
                      </div>
                    )}
                    {layer.warnings.length > 0 && (
                      <div style={{ marginTop: 8, color: "#766f68", fontSize: 12, lineHeight: 1.6 }}>{layer.warnings.join(" ")}</div>
                    )}
                  </article>
                ))}
              </div>
            </section>

            <section style={{ background: "#fff", border: "1px solid #e6e1da", borderRadius: 18, padding: 20 }}>
              <h2 style={{ margin: "0 0 10px", fontSize: 19 }}>調査状況</h2>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 8, fontSize: 13 }}>
                <div><span style={{ color: "#716b64" }}>セル状態</span><br /><b>{profile.coverage.cellClosureStatus}</b></div>
                <div><span style={{ color: "#716b64" }}>資料coverage</span><br /><b>{profile.coverage.sourceCoverageCeiling}</b></div>
                <div><span style={{ color: "#716b64" }}>不存在を断定</span><br /><b>{profile.coverage.absenceClaimAllowed ? "可" : "不可"}</b></div>
              </div>
              <div style={{ marginTop: 12, padding: 12, background: "#f4f1eb", borderRadius: 11, color: "#625d57", fontSize: 12, lineHeight: 1.65 }}>
                情報が見つからないことは、安全・歴史的な不存在を意味しません。現在接続済みの資料と100m運用精度で分かる範囲を表示しています。
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
