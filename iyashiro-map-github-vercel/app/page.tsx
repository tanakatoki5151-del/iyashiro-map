import Link from "next/link";
import MapApp from "./map-app";

const linkStyle = {
  padding: "9px 13px",
  borderRadius: 999,
  background: "rgba(255,255,255,.94)",
  border: "1px solid rgba(32,29,26,.14)",
  boxShadow: "0 6px 22px rgba(0,0,0,.10)",
  color: "#225f6f",
  textDecoration: "none",
  fontSize: 13,
  fontWeight: 700,
  backdropFilter: "blur(8px)",
} as const;

export default function Home() {
  return (
    <>
      <MapApp />
      <nav
        aria-label="関連ツール"
        style={{
          position: "fixed",
          right: 16,
          top: 16,
          zIndex: 1200,
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-end",
          gap: 8,
        }}
      >
        <Link href="/integrated" style={linkStyle}>統合コパイロット ✦</Link>
        <Link href="/nexus" style={linkStyle}>NEXUS 物件判定 🧬</Link>
        <Link href="/profile" style={linkStyle}>土地カルテ 🗺️</Link>
      </nav>
    </>
  );
}
