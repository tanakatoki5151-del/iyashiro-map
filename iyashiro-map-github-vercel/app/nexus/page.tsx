import type { Metadata } from "next";
import Link from "next/link";
import NexusClient from "./nexus-client";

export const metadata: Metadata = {
  title: "NEXUS 物件判定 | イヤシロ土地判定",
  description: "月額固定費17万円以内・1〜3階・15㎡以上の正式条件、薄さを明示した市場サンプル、外部公式ベンチマーク、全域土地探索を分けて確認するNEXUS物件判定です。",
};

const linkStyle = {
  display: "inline-block",
  padding: "11px 15px",
  borderRadius: 999,
  color: "white",
  textDecoration: "none",
  fontSize: 13,
  fontWeight: 850,
  boxShadow: "0 8px 24px rgba(15,37,44,.24)",
} as const;

export default function NexusPage() {
  return <>
    <div style={{ position: "fixed", right: 16, bottom: 16, zIndex: 1400, display: "grid", justifyItems: "end", gap: 8 }}>
      <Link href="/nexus/discovery" style={{ ...linkStyle, background: "#173d49" }}>
        全域240地点の探索を開く 🧭
      </Link>
      <Link href="/nexus/areas" style={{ ...linkStyle, background: "#766b58", fontSize: 11, padding: "8px 12px" }}>
        旧25地域の監査表
      </Link>
    </div>
    <NexusClient />
  </>;
}
