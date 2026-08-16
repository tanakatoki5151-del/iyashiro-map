import Link from "next/link";
import MapApp from "./map-app";

export default function Home() {
  return (
    <>
      <MapApp />
      <Link
        href="/profile"
        style={{
          position: "fixed",
          right: 16,
          top: 16,
          zIndex: 1200,
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
        }}
      >
        土地カルテ 🗺️
      </Link>
    </>
  );
}
