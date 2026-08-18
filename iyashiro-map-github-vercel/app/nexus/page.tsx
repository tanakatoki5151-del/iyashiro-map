import type { Metadata } from "next";
import Link from "next/link";
import NexusClient from "./nexus-client";

export const metadata: Metadata = {
  title: "NEXUS 物件判定 | イヤシロ土地判定",
  description: "月額固定費17万円以内・1〜3階・15㎡以上の正式条件、薄さを明示した市場サンプル、外部公式ベンチマーク、土地研究を分けて確認するNEXUS物件判定です。",
};

export default function NexusPage() {
  return <>
    <div style={{ position: "fixed", right: 16, bottom: 16, zIndex: 1400 }}>
      <Link href="/nexus/areas" style={{ display: "inline-block", padding: "11px 15px", borderRadius: 999, background: "#173d49", color: "white", textDecoration: "none", fontSize: 13, fontWeight: 850, boxShadow: "0 8px 24px rgba(15,37,44,.24)" }}>
        25地域の研究マップを開く 🗺️
      </Link>
    </div>
    <NexusClient />
  </>;
}
