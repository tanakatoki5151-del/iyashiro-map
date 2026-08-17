import type { Metadata } from "next";
import NexusClient from "./nexus-client";

export const metadata: Metadata = {
  title: "NEXUS 物件判定 | イヤシロ土地判定",
  description: "家賃条件、掲載の現在性、物件の同一性、土地の調査結果を分けて確認する物件判定画面です。",
};

export default function NexusPage() {
  return <NexusClient />;
}
