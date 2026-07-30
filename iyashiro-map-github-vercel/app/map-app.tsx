"use client";

import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type * as Leaflet from "leaflet";
import type { DiagnosisResult } from "./lib/diagnose";

type Mode = "theory" | "modern" | "combined";
type Candidate = { label: string; lat: number; lng: number };
type GridCell = {
  lat: number;
  lng: number;
  bounds: [[number, number], [number, number]];
  theory: { score: number; confidence: number; label: string };
  modern: { score: number; completeness: number; label: string };
  combined: { score: number; provisional: boolean; label: string };
};
type PrecomputedGridCell = {
  lat: number;
  lng: number;
  bounds: [[number, number], [number, number]];
  label: string;
  originalScore: number;
  originalFit: number;
  auxiliaryTerrainScore: number;
  detailScore: number;
  neighborhoodScore: number;
  confidence: number;
};
type PrecomputedGrid = {
  generatedAt: string;
  center: {
    lat: number;
    lng: number;
    name: string;
    address: string;
    radiusMeters: number;
    stepMeters: number;
  };
  region?: {
    id: string;
    kind: string;
    name: string;
    stepMeters: number;
    radiusMeters?: number;
    bufferMeters?: number;
    stations?: Array<{
      name: string;
      lat: number;
      lng: number;
    }>;
  };
  bounds: [[number, number], [number, number]];
  cells: PrecomputedGridCell[];
};

const MODES: Array<{ key: Mode; label: string }> = [
  { key: "theory", label: "イヤシロ仮説" },
  { key: "modern", label: "土地リスク" },
  { key: "combined", label: "住むなら" },
];
const HAZARDS = [
  ["flood", "洪水浸水想定", "https://disaportaldata.gsi.go.jp/raster/01_flood_l2_shinsuishin_data/{z}/{x}/{y}.png"],
  ["inner", "内水浸水", "https://disaportaldata.gsi.go.jp/raster/02_naisui_data/{z}/{x}/{y}.png"],
  ["highTide", "高潮", "https://disaportaldata.gsi.go.jp/raster/03_hightide_l2_shinsuishin_data/{z}/{x}/{y}.png"],
  ["tsunami", "津波", "https://disaportaldata.gsi.go.jp/raster/04_tsunami_newlegend_data/{z}/{x}/{y}.png"],
  ["landslide", "土砂災害", "https://disaportaldata.gsi.go.jp/raster/05_dosekiryukeikaikuiki/{z}/{x}/{y}.png"],
  ["wetland", "明治期の低湿地", "https://cyberjapandata.gsi.go.jp/xyz/swale/{z}/{x}/{y}.png"],
] as const;
const OVERVIEW_BOUNDS: [[number, number], [number, number]] = [
  [35.28, 139.43],
  [35.84, 139.94],
];
const CUOLEGA_BOUNDS: [[number, number], [number, number]] = [
  [35.626804, 139.709974],
  [35.707652, 139.80949],
];
const CUOLEGA_CENTER = { lat: 35.667228, lng: 139.759732 };
const DENENTOSHI_BOUNDS: [[number, number], [number, number]] = [
  [35.595239, 139.614686],
  [35.676087, 139.714162],
];
const ALL_PRECOMPUTED_BOUNDS: [[number, number], [number, number]] = [
  [35.595239, 139.614686],
  [35.707652, 139.80949],
];
const DENENTOSHI_STATIONS = [
  { name: "渋谷", lat: 35.659939, lng: 139.699738 },
  { name: "池尻大橋", lat: 35.650869, lng: 139.684594 },
  { name: "三軒茶屋", lat: 35.643726, lng: 139.671962 },
  { name: "駒沢大学", lat: 35.633193, lng: 139.661156 },
  { name: "桜新町", lat: 35.631724, lng: 139.645369 },
  { name: "用賀", lat: 35.626437, lng: 139.633264 },
  { name: "二子玉川", lat: 35.611387, lng: 139.629109 },
] as const;

const rgb = (hex: string) => {
  const value = Number.parseInt(hex.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
};
const mix = (a: string, b: string, ratio: number) => {
  const first = rgb(a);
  const second = rgb(b);
  return `rgb(${first.map((v, i) => Math.round(v + (second[i] - v) * ratio)).join(",")})`;
};
const originalCellColor = (label: string, score: number) => {
  const strength = 0.42 + 0.58 * (Math.abs(score - 50) / 50);
  if (label === "イヤシロチ候補")
    return mix("#d7ebe6", "#0b7e69", strength);
  if (label === "ケガレチ候補")
    return mix("#ead6de", "#892247", strength);
  if (label === "普通地") return "#c49a35";
  if (label === "高低混在") return "#6d5e94";
  return label === "判定材料不足" ? "#b9bcb8" : "#90948f";
};
const safetyColor = (score: number) =>
  score < 50
    ? mix("#991b1b", "#d97706", score / 50)
    : mix("#d97706", "#16845b", (score - 50) / 50);

export default function MapApp() {
  const nodeRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Leaflet.Map | null>(null);
  const leafletRef = useRef<typeof Leaflet | null>(null);
  const markerRef = useRef<Leaflet.Marker | null>(null);
  const overviewRef = useRef<Leaflet.ImageOverlay | null>(null);
  const cuolegaOverlayRef = useRef<Leaflet.ImageOverlay | null>(null);
  const denentoshiOverlayRef = useRef<Leaflet.ImageOverlay | null>(null);
  const gridRef = useRef<Leaflet.LayerGroup | null>(null);
  const hazardRefs = useRef<Record<string, Leaflet.TileLayer>>({});
  const gridAbort = useRef<AbortController | null>(null);
  const diagnosisAbort = useRef<AbortController | null>(null);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const modeRef = useRef<Mode>("theory");

  const [mode, setMode] = useState<Mode>("theory");
  const [ready, setReady] = useState(false);
  const [revision, setRevision] = useState(0);
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [searching, setSearching] = useState(false);
  const [diagnosing, setDiagnosing] = useState(false);
  const [diagnosis, setDiagnosis] = useState<DiagnosisResult | null>(null);
  const [precomputedGrids, setPrecomputedGrids] = useState<PrecomputedGrid[]>(
    [],
  );
  const [error, setError] = useState<string | null>(null);
  const [gridMessage, setGridMessage] = useState(
    "クオレガ4.5km圏と田園都市線沿線の100m事前計算色を表示しています。",
  );
  const [layersOpen, setLayersOpen] = useState(false);
  const [legendOpen, setLegendOpen] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);
  const [activeHazards, setActiveHazards] = useState<string[]>([]);

  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all(
      [
        "/data/cuolega-grid-v2.json",
        "/data/denentoshi-shibuya-futako-grid-v2.json",
      ].map((url) =>
        fetch(url, {
          signal: controller.signal,
          cache: "force-cache",
        }).then(async (response) => {
          if (!response.ok) throw new Error("precomputed grid unavailable");
          return (await response.json()) as PrecomputedGrid;
        }),
      ),
    )
      .then(setPrecomputedGrids)
      .catch((caught) => {
        if ((caught as Error).name !== "AbortError") {
          setGridMessage(
            "事前計算の色分け画像を表示中。100m詳細区画は再読み込みで取得します。",
          );
        }
      });
    return () => controller.abort();
  }, []);

  const drawMarker = useCallback((lat: number, lng: number) => {
    const L = leafletRef.current;
    const map = mapRef.current;
    if (!L || !map) return;
    markerRef.current?.remove();
    markerRef.current = L.marker([lat, lng], {
      icon: L.divIcon({
        className: "diagnosis-marker-shell",
        html: '<span class="diagnosis-marker"><span></span></span>',
        iconSize: [34, 42],
        iconAnchor: [17, 39],
      }),
      title: "診断地点",
    }).addTo(map);
  }, []);

  const diagnosePoint = useCallback(
    async (
      lat: number,
      lng: number,
      options: { move?: boolean; result?: DiagnosisResult } = {},
    ) => {
      setCandidates([]);
      setError(null);
      if (options.move && mapRef.current) {
        mapRef.current.setView(
          [lat, lng],
          Math.max(14, mapRef.current.getZoom()),
          { animate: true },
        );
      }
      drawMarker(lat, lng);
      window.history.replaceState(
        null,
        "",
        `?lat=${lat.toFixed(6)}&lng=${lng.toFixed(6)}&mode=${modeRef.current}`,
      );
      if (options.result) {
        setDiagnosis(options.result);
        return;
      }
      diagnosisAbort.current?.abort();
      const controller = new AbortController();
      diagnosisAbort.current = controller;
      setDiagnosing(true);
      try {
        const response = await fetch(`/api/diagnose?lat=${lat}&lng=${lng}`, {
          signal: controller.signal,
        });
        const data = (await response.json()) as
          | DiagnosisResult
          | { message?: string };
        if (!response.ok)
          throw new Error(
            "message" in data && data.message
              ? data.message
              : "診断できませんでした。",
          );
        setDiagnosis(data as DiagnosisResult);
      } catch (caught) {
        if ((caught as Error).name !== "AbortError") {
          setDiagnosis(null);
          setError(
            caught instanceof Error ? caught.message : "診断に失敗しました。",
          );
        }
      } finally {
        if (diagnosisAbort.current === controller) setDiagnosing(false);
      }
    },
    [drawMarker],
  );

  useEffect(() => {
    if (!nodeRef.current || mapRef.current) return;
    let disposed = false;
    void import("leaflet").then((L) => {
      if (disposed || !nodeRef.current) return;
      leafletRef.current = L;
      const map = L.map(nodeRef.current, {
        zoomControl: false,
        minZoom: 9,
        maxZoom: 18,
      });
      L.tileLayer(
        "https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png",
        {
          maxZoom: 18,
          attribution:
            '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank">地理院タイル</a>',
        },
      ).addTo(map);
      const overviewPane = map.createPane("iyashiroOverview");
      overviewPane.style.zIndex = "350";
      overviewPane.style.pointerEvents = "none";
      const cuolegaPane = map.createPane("cuolegaGrid");
      cuolegaPane.style.zIndex = "360";
      cuolegaPane.style.pointerEvents = "none";
      const hazardPane = map.createPane("officialHazards");
      hazardPane.style.zIndex = "380";
      hazardPane.style.pointerEvents = "none";
      overviewRef.current = L.imageOverlay(
        "/data/iyashiro-overview.png",
        OVERVIEW_BOUNDS,
        {
          pane: "iyashiroOverview",
          opacity: 0.78,
          alt: "東京23区・横浜市・川崎市のイヤシロ仮説広域色分け",
          className: "iyashiro-overview",
        },
      ).addTo(map);
      cuolegaOverlayRef.current = L.imageOverlay(
        "/data/cuolega-grid-v2.png",
        CUOLEGA_BOUNDS,
        {
          pane: "cuolegaGrid",
          opacity: 0.9,
          alt: "クオレガ東京本社4.5km圏の100mイヤシロ判定",
          className: "cuolega-grid-overlay",
        },
      ).addTo(map);
      denentoshiOverlayRef.current = L.imageOverlay(
        "/data/denentoshi-shibuya-futako-grid-v2.png",
        DENENTOSHI_BOUNDS,
        {
          pane: "cuolegaGrid",
          opacity: 0.9,
          alt: "田園都市線の渋谷駅から二子玉川駅まで・線路中心1km帯の100mイヤシロ判定",
          className: "denentoshi-grid-overlay",
        },
      ).addTo(map);
      L.circle([CUOLEGA_CENTER.lat, CUOLEGA_CENTER.lng], {
        radius: 4_500,
        color: "rgba(24,33,31,.62)",
        weight: 1.5,
        dashArray: "7 7",
        fill: false,
        interactive: false,
      }).addTo(map);
      L.circleMarker([CUOLEGA_CENTER.lat, CUOLEGA_CENTER.lng], {
        radius: 5,
        color: "#fff",
        weight: 2,
        fillColor: "#18211f",
        fillOpacity: 1,
      })
        .bindTooltip("クオレガ東京本社／4.5km圏の中心")
        .addTo(map);
      L.polyline(
        DENENTOSHI_STATIONS.map((station) => [station.lat, station.lng]),
        {
          color: "rgba(24,33,31,.78)",
          weight: 2.2,
          dashArray: "5 6",
          interactive: false,
        },
      ).addTo(map);
      DENENTOSHI_STATIONS.forEach((station) => {
        L.circleMarker([station.lat, station.lng], {
          radius: 4,
          color: "#fff",
          weight: 1.5,
          fillColor: "#0b7e69",
          fillOpacity: 1,
        })
          .bindTooltip(`田園都市線 ${station.name}駅`)
          .addTo(map);
      });
      L.control.zoom({ position: "bottomright" }).addTo(map);
      L.control.scale({ position: "bottomleft", imperial: false }).addTo(map);
      gridRef.current = L.layerGroup().addTo(map);
      map.fitBounds(ALL_PRECOMPUTED_BOUNDS, { padding: [18, 18] });
      map.on("moveend", () => setRevision((v) => v + 1));
      map.on("click", (event) =>
        void diagnosePoint(event.latlng.lat, event.latlng.lng),
      );
      mapRef.current = map;
      setReady(true);
      setRevision((v) => v + 1);
      const params = new URLSearchParams(window.location.search);
      const requestedMode = params.get("mode") as Mode | null;
      if (requestedMode && MODES.some((entry) => entry.key === requestedMode)) {
        modeRef.current = requestedMode;
        setMode(requestedMode);
      }
      const latParam = params.get("lat");
      const lngParam = params.get("lng");
      const lat = latParam === null ? Number.NaN : Number(latParam);
      const lng = lngParam === null ? Number.NaN : Number(lngParam);
      if (Number.isFinite(lat) && Number.isFinite(lng))
        void diagnosePoint(lat, lng, { move: true });
    });
    return () => {
      disposed = true;
      diagnosisAbort.current?.abort();
      gridAbort.current?.abort();
      mapRef.current?.remove();
      mapRef.current = null;
      overviewRef.current = null;
      cuolegaOverlayRef.current = null;
      denentoshiOverlayRef.current = null;
    };
  }, [diagnosePoint]);

  useEffect(() => {
    const map = mapRef.current;
    const overview = overviewRef.current;
    const cuolega = cuolegaOverlayRef.current;
    const denentoshi = denentoshiOverlayRef.current;
    if (!ready || !map || !overview || !cuolega || !denentoshi) return;
    if (mode === "theory") {
      if (!map.hasLayer(overview)) overview.addTo(map);
      if (!map.hasLayer(cuolega)) cuolega.addTo(map);
      if (!map.hasLayer(denentoshi)) denentoshi.addTo(map);
      overview.setOpacity(map.getZoom() >= 13 ? 0.14 : 0.38);
      cuolega.setOpacity(
        map.getZoom() >= 14 && precomputedGrids.length ? 0.18 : 0.9,
      );
      denentoshi.setOpacity(
        map.getZoom() >= 14 && precomputedGrids.length ? 0.18 : 0.9,
      );
    } else {
      if (map.hasLayer(overview)) overview.remove();
      if (map.hasLayer(cuolega)) cuolega.remove();
      if (map.hasLayer(denentoshi)) denentoshi.remove();
    }
  }, [mode, precomputedGrids, ready, revision]);

  useEffect(() => {
    const map = mapRef.current;
    const L = leafletRef.current;
    const layer = gridRef.current;
    if (!ready || !map || !L || !layer) return;
    layer.clearLayers();
    gridAbort.current?.abort();
    if (mode === "theory") {
      if (map.getZoom() < 14) {
        setGridMessage(
          "クオレガ4.5km圏＋田園都市線1km沿線帯を表示中。拡大すると100m区画の数値を確認できます。",
        );
        return;
      }
      if (!precomputedGrids.length) {
        queueMicrotask(() =>
          setGridMessage(
            "100m区画データを読み込み中。色分け画像はすでに表示しています。",
          ),
        );
        return;
      }
      const bounds = map.getBounds();
      const visible = precomputedGrids.flatMap((grid) =>
        grid.cells.filter((cell) =>
          bounds.contains([cell.lat, cell.lng]),
        ),
      );
      visible.forEach((cell) => {
        const rectangle = L.rectangle(cell.bounds, {
          color: "rgba(255,255,255,.68)",
          weight: 0.65,
          fillColor: originalCellColor(cell.label, cell.originalScore),
          fillOpacity: 0.3 + cell.confidence * 0.0048,
        });
        rectangle.bindTooltip(
          `${cell.label}｜地点詳細 ${cell.detailScore}｜原典 ${cell.originalScore}`,
          {
            sticky: true,
            className: "map-tooltip",
          },
        );
        rectangle.on("click", () =>
          void diagnosePoint(cell.lat, cell.lng),
        );
        rectangle.addTo(layer);
      });
      setGridMessage(
        `${visible.length}区画を100m事前計算で表示中。クリックで6項目の詳細を確認できます。`,
      );
      return;
    }
    if (map.getZoom() < 13) {
      setGridMessage(
        "地図をもう少し拡大すると、土地リスクを色分けします。",
      );
      return;
    }
    const bounds = map.getBounds();
    if (
      bounds.getEast() - bounds.getWest() > 0.25 ||
      bounds.getNorth() - bounds.getSouth() > 0.2
    ) {
      setGridMessage("表示範囲が広いため、もう少し拡大してください。");
      return;
    }
    const controller = new AbortController();
    gridAbort.current = controller;
    setGridMessage("公式データから、この範囲を解析しています…");
    const url = new URL("/api/grid", window.location.origin);
    url.searchParams.set("west", String(bounds.getWest()));
    url.searchParams.set("south", String(bounds.getSouth()));
    url.searchParams.set("east", String(bounds.getEast()));
    url.searchParams.set("north", String(bounds.getNorth()));
    void fetch(url, { signal: controller.signal })
      .then(async (response) => {
        const payload = (await response.json()) as {
          cells?: GridCell[];
          message?: string;
        };
        if (!response.ok) throw new Error(payload.message);
        return payload.cells ?? [];
      })
      .then((cells) => {
        if (controller.signal.aborted) return;
        cells.forEach((cell) => {
          const value =
            mode === "modern"
                ? cell.modern
                : cell.combined;
          const score = value.score;
          const opacity =
            mode === "modern"
                ? 0.22 + cell.modern.completeness * 0.0046
                : cell.combined.provisional
                  ? 0.38
                  : 0.62;
          const rectangle = L.rectangle(cell.bounds, {
            color: "rgba(255,255,255,.75)",
            weight: 1,
            fillColor:
              safetyColor(score),
            fillOpacity: opacity,
          });
          rectangle.bindTooltip(`${value.label} ${score}/100`, {
            sticky: true,
            className: "map-tooltip",
          });
          rectangle.on("click", () =>
            void diagnosePoint(cell.lat, cell.lng),
          );
          rectangle.addTo(layer);
        });
        setGridMessage(
          cells.length
            ? `${cells.length}区画を概算表示中。クリックで詳細診断できます。`
            : "対象範囲内の区画がありません。",
        );
      })
      .catch((caught) => {
        if ((caught as Error).name !== "AbortError")
          setGridMessage(
            "色分けを取得できませんでした。地図を動かすと再試行します。",
          );
      });
    return () => controller.abort();
  }, [diagnosePoint, mode, precomputedGrids, ready, revision]);

  useEffect(() => {
    const map = mapRef.current;
    const L = leafletRef.current;
    if (!ready || !map || !L) return;
    HAZARDS.forEach(([key, , url]) => {
      const existing = hazardRefs.current[key];
      const active = activeHazards.includes(key);
      if (active && !existing) {
        const layer = L.tileLayer(url, {
          opacity: 0.72,
          maxZoom: 18,
          pane: "officialHazards",
          attribution:
            key === "wetland"
              ? "国土地理院 明治期の低湿地"
              : "国土交通省 ハザードマップポータル",
        });
        hazardRefs.current[key] = layer;
        layer.addTo(map);
      } else if (!active && existing) {
        existing.remove();
        delete hazardRefs.current[key];
      }
    });
  }, [activeHazards, ready]);

  const searchAddresses = useCallback((value: string) => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    if (value.trim().length < 2) {
      setCandidates([]);
      return;
    }
    setSearching(true);
    searchTimer.current = setTimeout(() => {
      void fetch(`/api/search?q=${encodeURIComponent(value.trim())}`)
        .then(async (response) => {
          const data = (await response.json()) as { candidates?: Candidate[] };
          return response.ok ? data.candidates ?? [] : [];
        })
        .then(setCandidates)
        .finally(() => setSearching(false));
    }, 320);
  }, []);

  const selectCandidate = (candidate: Candidate) => {
    setQuery(candidate.label);
    void diagnosePoint(candidate.lat, candidate.lng, { move: true });
  };

  const submitSearch = async (event: FormEvent) => {
    event.preventDefault();
    if (candidates[0]) return selectCandidate(candidates[0]);
    if (query.trim().length < 2) return;
    setSearching(true);
    try {
      const response = await fetch(`/api/lookup?q=${encodeURIComponent(query)}`);
      const payload = (await response.json()) as
        | (DiagnosisResult & { matchedAddress?: string })
        | { message?: string };
      if (!response.ok)
        throw new Error(
          "message" in payload && payload.message
            ? payload.message
            : "住所が見つかりません。",
        );
      const result = payload as DiagnosisResult & { matchedAddress?: string };
      if (result.matchedAddress) setQuery(result.matchedAddress);
      void diagnosePoint(result.point.lat, result.point.lng, {
        move: true,
        result,
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "検索に失敗しました。");
    } finally {
      setSearching(false);
    }
  };

  const changeMode = (next: Mode) => {
    modeRef.current = next;
    setMode(next);
    const url = new URL(window.location.href);
    url.searchParams.set("mode", next);
    window.history.replaceState(null, "", url);
  };

  const currentLocation = () => {
    if (!navigator.geolocation)
      return setError("この端末では現在地を取得できません。");
    setDiagnosing(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setDiagnosing(false);
        void diagnosePoint(position.coords.latitude, position.coords.longitude, {
          move: true,
        });
      },
      () => {
        setDiagnosing(false);
        setError("位置情報の許可を確認してください。");
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  };

  const modeMeta = useMemo(
    () => MODES.find((entry) => entry.key === mode) ?? MODES[0],
    [mode],
  );
  const displayedScore = diagnosis
    ? mode === "theory"
      ? diagnosis.theory.score
      : mode === "modern"
        ? diagnosis.modern.score
        : diagnosis.combined.score
    : 0;
  const displayedLabel = diagnosis
    ? mode === "theory"
      ? diagnosis.theory.label
      : mode === "modern"
        ? diagnosis.modern.label
        : diagnosis.combined.label
    : "";

  return (
    <main className="map-app">
      <header className="top-shell">
        <div className="brand-row">
          <div>
            <p className="eyebrow">TOKYO · YOKOHAMA · KAWASAKI</p>
            <h1>土地の地形を、読み解く。</h1>
          </div>
          <button
            className="round-button"
            type="button"
            aria-label="使い方と判定方法"
            onClick={() => setInfoOpen(true)}
          >
            i
          </button>
        </div>
        <form className="search-box" onSubmit={submitSearch}>
          <span aria-hidden="true">⌕</span>
          <input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              searchAddresses(event.target.value);
            }}
            placeholder="住所・駅名・施設名を入力"
            aria-label="住所を検索"
          />
          {query && (
            <button
              type="button"
              className="clear-search"
              aria-label="検索文字を消す"
              onClick={() => {
                setQuery("");
                setCandidates([]);
              }}
            >
              ×
            </button>
          )}
          <button className="search-submit" type="submit">
            {searching ? "検索中" : "判定"}
          </button>
          {candidates.length > 0 && (
            <div className="suggestions" role="listbox">
              {candidates.map((candidate) => (
                <button
                  key={`${candidate.lat}-${candidate.lng}`}
                  type="button"
                  role="option"
                  aria-selected="false"
                  onClick={() => selectCandidate(candidate)}
                >
                  <span>{candidate.label}</span>
                  <small>この地点を診断</small>
                </button>
              ))}
            </div>
          )}
        </form>
        <nav className="mode-tabs" aria-label="地図の表示モード">
          {MODES.map((entry) => (
            <button
              key={entry.key}
              type="button"
              className={entry.key === mode ? "active" : ""}
              aria-current={entry.key === mode ? "page" : undefined}
              onClick={() => changeMode(entry.key)}
            >
              {entry.label}
            </button>
          ))}
        </nav>
      </header>

      <section className="map-stage" aria-label="土地判定地図">
        <div ref={nodeRef} className="map-canvas" />
        <div className="map-status">
          <span className={`status-dot ${mode}`} />
          <span>
            <strong>{modeMeta.label}</strong>
            {gridMessage}
          </span>
        </div>
        <div className="map-tools">
          <button
            type="button"
            className={layersOpen ? "active" : ""}
            onClick={() => setLayersOpen((v) => !v)}
          >
            ▱ レイヤー
          </button>
          <button
            type="button"
            onClick={() =>
              mapRef.current?.fitBounds(DENENTOSHI_BOUNDS, {
                padding: [18, 18],
              })
            }
          >
            ⇢ 田園都市線
          </button>
          <button type="button" onClick={currentLocation}>
            ◎ 現在地
          </button>
          <button
            type="button"
            className={legendOpen ? "active" : ""}
            onClick={() => setLegendOpen((v) => !v)}
          >
            ◐ 凡例
          </button>
        </div>
        {layersOpen && (
          <aside className="floating-panel layer-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">SOURCE LAYERS</p>
                <h2>公式ハザードを重ねる</h2>
              </div>
              <button type="button" onClick={() => setLayersOpen(false)}>
                ×
              </button>
            </div>
            <p className="panel-note">
              判定とは別に、元の公開タイルを直接確認できます。
            </p>
            <div className="layer-list">
              {HAZARDS.map(([key, label]) => (
                <label key={key}>
                  <input
                    type="checkbox"
                    checked={activeHazards.includes(key)}
                    onChange={() =>
                      setActiveHazards((current) =>
                        current.includes(key)
                          ? current.filter((item) => item !== key)
                          : [...current, key],
                      )
                    }
                  />
                  {label}
                </label>
              ))}
            </div>
          </aside>
        )}
        {legendOpen && (
          <aside className="floating-panel legend-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">LEGEND</p>
                <h2>{modeMeta.label}の見方</h2>
              </div>
              <button type="button" onClick={() => setLegendOpen(false)}>
                ×
              </button>
            </div>
            <div
              className={`legend-gradient ${mode === "theory" ? "theory-gradient" : "safety-gradient"}`}
            />
            <div className="legend-labels">
              <span>{mode === "theory" ? "ケガレ寄り" : "高リスク"}</span>
              <span>中間</span>
              <span>{mode === "theory" ? "イヤシロ寄り" : "低リスク"}</span>
            </div>
            {mode === "theory" && (
              <div className="classification-legend">
                {[
                  ["#0b7e69", "イヤシロ候補"],
                  ["#892247", "ケガレ候補"],
                  ["#c49a35", "普通地"],
                  ["#6d5e94", "高低混在"],
                  ["#b9bcb8", "材料不足"],
                ].map(([color, label]) => (
                  <span key={label}>
                    <i style={{ background: color }} />
                    {label}
                  </span>
                ))}
              </div>
            )}
            <p className="panel-note">
              {mode === "theory"
                ? "クオレガ4.5km圏と田園都市線の渋谷〜二子玉川・線路中心1km帯は、同じ100mロジックで事前計算済みです。"
                : "未取得データは安全とみなさず暫定表示します。"}
            </p>
          </aside>
        )}
      </section>

      {(diagnosing || diagnosis || error) && (
        <aside className="result-sheet" aria-live="polite">
          <div className="sheet-grabber" />
          {diagnosing && (
            <div className="loading-result">
              <span className="spinner" />
              <div>
                <strong>地形と土地条件を解析中</strong>
                <p>標高・水害・地盤の公式データを照合しています。</p>
              </div>
            </div>
          )}
          {!diagnosing && error && (
            <div className="error-result">
              <div>
                <p className="eyebrow">CHECK REQUIRED</p>
                <strong>この地点は判定できませんでした</strong>
                <p>{error}</p>
              </div>
              <button type="button" onClick={() => setError(null)}>
                閉じる
              </button>
            </div>
          )}
          {!diagnosing && diagnosis && (
            <>
              <div className="result-heading">
                <div>
                  <p className="eyebrow">{diagnosis.scope.name}</p>
                  <h2>{displayedLabel}</h2>
                  <p className="coordinate">
                    {diagnosis.point.addressHint || diagnosis.point.coordinate}
                  </p>
                </div>
                <div
                  className="main-score"
                  style={
                    {
                      "--score-color":
                        mode === "theory"
                          ? originalCellColor(
                              diagnosis.theory.label,
                              diagnosis.theory.originalScore,
                            )
                          : safetyColor(displayedScore),
                    } as React.CSSProperties
                  }
                >
                  <strong>{displayedScore}</strong>
                  <span>/100</span>
                </div>
              </div>
              <div className="terrain-score-grid">
                <article className="original-judgement">
                  <span>1　原典判定</span>
                  <strong>{diagnosis.theory.originalScore}</strong>
                  <small>{diagnosis.theory.label}</small>
                  <em>原典適合 {diagnosis.theory.originalFit}/100</em>
                </article>
                <article>
                  <span>2　補助地形点</span>
                  <strong>{diagnosis.theory.auxiliaryTerrainScore}</strong>
                  <small>相対標高・排水・傾斜</small>
                </article>
                <article className="detail-score-card">
                  <span>3　地点詳細点</span>
                  <strong>{diagnosis.theory.detailScore}</strong>
                  <small>原典80%＋補助20%</small>
                </article>
                <article>
                  <span>4　周辺点</span>
                  <strong>
                    {diagnosis.theory.neighborhoodScore ?? "—"}
                  </strong>
                  <small>
                    {diagnosis.theory.neighborhoodScore === null
                      ? "事前計算圏外"
                      : "半径500m"}
                  </small>
                </article>
                <article>
                  <span>5　判定信頼度</span>
                  <strong>{diagnosis.theory.internalConfidence}</strong>
                  <small>線抽出と縮尺整合</small>
                </article>
              </div>
              <article className="nearby-best-card">
                <div>
                  <span>6　近隣で最も高い場所</span>
                  {diagnosis.theory.nearbyBest ? (
                    <>
                      <strong>
                        地点詳細 {diagnosis.theory.nearbyBest.detailScore}
                      </strong>
                      <small>
                        約{diagnosis.theory.nearbyBest.distanceMeters}m先・
                        {diagnosis.theory.nearbyBest.label}
                      </small>
                    </>
                  ) : (
                    <>
                      <strong>該当なし</strong>
                      <small>1km以内に高信頼の候補なし</small>
                    </>
                  )}
                </div>
                {diagnosis.theory.nearbyBest && (
                  <button
                    type="button"
                    onClick={() =>
                      void diagnosePoint(
                        diagnosis.theory.nearbyBest!.lat,
                        diagnosis.theory.nearbyBest!.lng,
                        { move: true },
                      )
                    }
                  >
                    地図で見る
                  </button>
                )}
              </article>
              <div className="secondary-score-row">
                <span>
                  現代的土地条件 <strong>{diagnosis.modern.score}</strong>
                  <small>{diagnosis.modern.label}</small>
                </span>
                <span>
                  住むなら総合 <strong>{diagnosis.combined.score}</strong>
                  <small>{diagnosis.combined.label}</small>
                </span>
              </div>
              <details className="reason-details" open>
                <summary>この判定になった理由</summary>
                <div className="reason-columns">
                  <div>
                    <h3>イヤシロ仮説</h3>
                    <ul>
                      {diagnosis.theory.reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <h3>現代的土地条件</h3>
                    <ul>
                      {diagnosis.modern.reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </details>
              <div className="result-actions">
                <a
                  href={`/api/diagnose?lat=${diagnosis.point.lat}&lng=${diagnosis.point.lng}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  AI・JSON用の結果を開く
                </a>
                <button type="button" onClick={() => setDiagnosis(null)}>
                  閉じる
                </button>
              </div>
              <p className="disclaimer">{diagnosis.disclaimer}</p>
            </>
          )}
        </aside>
      )}

      {infoOpen && (
        <div className="modal-backdrop">
          <section
            className="info-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="info-title"
          >
            <div className="panel-heading">
              <div>
                <p className="eyebrow">ABOUT THIS MAP</p>
                <h2 id="info-title">判定方法と使い方</h2>
              </div>
              <button type="button" onClick={() => setInfoOpen(false)}>
                ×
              </button>
            </div>
            <div className="info-content">
              <article>
                <span>01</span>
                <div>
                  <h3>イヤシロ仮説</h3>
                  <p>
                    300m、1km、3kmの3縮尺で高位指向線・低位指向線を抽出。高位×高位をイヤシロチ候補、低位×低位をケガレチ候補、高位×低位を普通地として原典判定します。クオレガ4.5km圏6,361区画と、田園都市線の渋谷〜二子玉川・線路中心1km帯2,109区画を100m間隔で事前計算済みです。
                  </p>
                </div>
              </article>
              <article>
                <span>02</span>
                <div>
                  <h3>現代的土地条件</h3>
                  <p>
                    洪水・内水・高潮・津波・土砂災害・傾斜・J-SHIS地盤・明治期低湿地を照合。未着色を安全とは扱いません。
                  </p>
                </div>
              </article>
              <article>
                <span>03</span>
                <div>
                  <h3>住むなら総合</h3>
                  <p>
                    原典判定とは分離して現代的条件を主軸に評価します。地点詳細点は原典ロジック80%＋補助地形20%で、周辺点・判定信頼度・1km以内の最高評価地点も表示します。
                  </p>
                </div>
              </article>
              <article>
                <span>AI</span>
                <div>
                  <h3>AIからも取得</h3>
                  <p>
                    <code>/api/lookup?q=住所</code> または{" "}
                    <code>/api/diagnose?lat=緯度&amp;lng=経度</code>{" "}
                    でJSONを取得できます。{" "}
                    <a href="/openapi.json" target="_blank" rel="noreferrer">
                      OpenAPI仕様
                    </a>
                  </p>
                </div>
              </article>
            </div>
            <p className="modal-disclaimer">
              イヤシロ／ケガレは科学的に確立された土地分類ではありません。居住・購入判断では自治体の最新資料と専門家確認を優先してください。
            </p>
          </section>
        </div>
      )}
    </main>
  );
}
