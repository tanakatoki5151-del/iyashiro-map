import type { Metadata } from "next";
import AreaClient from "./area-client";

export const metadata: Metadata = {
  title: "住む地域の研究マップ | NEXUS",
  description: "25地域の土地研究成熟度、市場データの厚み、未確認事項、次の研究工程を分離して表示します。居住おすすめ順位ではありません。",
};

export default function NexusAreasPage() {
  return <AreaClient />;
}
