import type { Metadata } from "next";
import NexusClient from "./nexus-client";

export const metadata: Metadata = {
  title: "NEXUS 物件判定 | イヤシロ土地判定",
  description: "月額固定費17万円以内・1〜3階・15㎡以上の正式条件、薄さを明示した市場サンプル、外部公式ベンチマーク、土地研究を分けて確認するNEXUS物件判定です。",
};

export default function NexusPage() {
  return <NexusClient />;
}
