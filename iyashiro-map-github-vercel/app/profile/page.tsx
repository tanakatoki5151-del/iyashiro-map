import ProfileClient from "./profile-client";

export const metadata = {
  title: "土地カルテ｜イヤシロ土地判定",
  description: "住所から100mセルと研究レイヤーをまとめて確認する土地カルテ",
};

export default function ProfilePage() {
  return <ProfileClient />;
}
