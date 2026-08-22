import type { Metadata } from "next";
import IntegratedCopilot from "@/app/components/integration/integrated-copilot";

export const metadata: Metadata = {
  title: "土地選び・物件判定コパイロット | イヤシロ土地判定マップ",
  description:
    "住所・座標・物件URLから、R3、V15.3、RYUMYAK、ORBIT、歴史、HOUSE COMPASS LABを分離表示して比較します。",
};

export default function IntegratedPage() {
  return <IntegratedCopilot />;
}
