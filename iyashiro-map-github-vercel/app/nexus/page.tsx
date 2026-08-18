import type { Metadata } from "next";
import NexusClientV3 from "./nexus-client-v3";

export const metadata: Metadata = {
  title: "NEXUS 物件判定 | イヤシロ土地判定",
  description: "月17万円・1〜3階・15㎡以上の物件条件、内部募集サンプル、土地研究を分けて確認するNEXUS物件判定です。",
};

export default function NexusPage() {
  return <NexusClientV3 />;
}
