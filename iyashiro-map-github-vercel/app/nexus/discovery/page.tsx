import type { Metadata } from "next";
import DiscoveryClient from "./discovery-client";

export const metadata: Metadata = {
  title: "全域240地点の比較探索 | NEXUS",
  description: "東京23区・横浜・川崎の48自治体を5層ずつ比較し、龍脈・地形・地下水・環境・場所履歴を独立表示する土地探索画面です。居住おすすめ順位ではありません。",
};

export default function NexusDiscoveryPage() {
  return <DiscoveryClient />;
}
