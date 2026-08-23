"use client";

import {
  FormEvent,
  KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type * as Leaflet from "leaflet";
import LandDossierPanel from "./components/land-dossier-panel";
import type { LandDossier } from "./lib/land-dossier-types";
import {
  gridAssessmentNeedsReview,
  type GridAssessment,
} from "./lib/grid-presentation";

type Mode = "theory" | "modern" | "combined";
type SheetLevel = "peek" | "half" | "full";
type Candidate = { label: string; lat: number; lng: number };
type DossierTarget =
  | { kind: "point"; lat: number; lng: number; label?: string }
  | { kind: "query"; query: string };

type GridCell = {
  lat: number;
  lng: number;
  bounds: [[number, number], [number, number]];
  theory: { score: number; confidence: number; label: string };
  modern: GridAssessment & { completeness: number };
  combined: GridAssessment;
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
  schemaVersion: string;
  engine: {
    name: string;
  };
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

const MODES: Array<{ key: Mode; label: string; shortLabel: string }> = [
  { key: "theory", label: "従来地形仮説（比較）", shortLabel: "地形の比較" },
  { key: "modern", label: "公的リスク地図", shortLabel: "公的リスク" },
  { key: "combined", label: "従来地形比較＋公的リスク", shortLabel: "重ねて見る" },
];
const LEGACY_COMPARISON_ENGINE = "directional-line-crossing-v2";
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

const REVIEW_CELL_COLOR = "#8b928f";
export default function MapApp() {
  const nodeRef = useRef<HTMLDivElement | null>(null);
  const dossierSheetRef = useRef<HTMLElement | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const mapRef = useRef<Leaflet.Map | null>(null);
  const leafletRef = useRef<typeof Leaflet | null>(null);
  const markerRef = useRef<Leaflet.Marker | null>(null);
  const overviewRef = useRef<Leaflet.ImageOverlay | null>(null);
  const cuolegaOverlayRef = useRef<Leaflet.ImageOverlay | null>(null);
  const denentoshiOverlayRef = useRef<Leaflet.ImageOverlay | null>(null);
  const gridRef = useRef<Leaflet.LayerGroup | null>(null);
  const hazardRefs = useRef<Record<string, Leaflet.TileLayer>>({});
  const gridAbort = useRef<AbortController | null>(null);
  const dossierAbort = useRef<AbortController | null>(null);
  const dossierRequestId = useRef(0);
  const searchAbort = useRef<AbortController | null>(null);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const modeRef = useRef<Mode>("theory");

  const [mode, setMode] = useState<Mode>("theory");
  const [ready, setReady] = useState(false);
  const [revision, setRevision] = useState(0);
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [activeCandidateIndex, setActiveCandidateIndex] = useState(-1);
  const [searching, setSearching] = useState(false);
  const [loadingDossier, setLoadingDossier] = useState(false);
  const [dossier, setDossier] = useState<LandDossier | null>(null);
  const [precomputedGrids, setPrecomputedGrids] = useState<PrecomputedGrid[]>(
    [],
  );
  const [error, setError] = useState<string | null>(null);
  const [gridMessage, setGridMessage] = useState(
    "従来の地形仮説を見比べるための参考地図です。凍結V10正本と現行V15.3は、地点を選んだ後の詳細で確認できます。",
  );
  const [layersOpen, setLayersOpen] = useState(false);
  const [legendOpen, setLegendOpen] = useState(false);
  const [sheetLevel, setSheetLevel] = useState<SheetLevel>("half");
  const [infoOpen, setInfoOpen] = useState(false);
  const [activeHazards, setActiveHazards] = useState<string[]>([]);

  const closeDossier = useCallback(() => {
    dossierRequestId.current += 1;
    dossierAbort.current?.abort();
    setLoadingDossier(false);
    setDossier(null);
    setError(null);
    window.requestAnimationFrame(() => searchInputRef.current?.focus());
  }, []);

  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);


  useEffect(() => {
    dossierSheetRef.current?.scrollTo({ top: 0, behavior: "auto" });
  }, [
    sheetLevel,
    loadingDossier,
    dossier?.location.lat,
    dossier?.location.lng,
  ]);
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
          const data = (await response.json()) as PrecomputedGrid;
          if (
            data.schemaVersion !== "2.0" ||
            data.engine?.name !== LEGACY_COMPARISON_ENGINE
          )
            throw new Error("unexpected comparison grid provenance");
          return data;
        }),
      ),
    )
      .then(setPrecomputedGrids)
      .catch((caught) => {
        if ((caught as Error).name !== "AbortError") {
          setGridMessage(
            "従来の地形仮説・広域比較画像を表示中です。100m比較区画は再読み込みで取得します。凍結V10正本は地点詳細で確認してください。",
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
        html: '<span class="diagnosis-marker" data-testid="selected-location-marker"><span></span></span>',
        iconSize: [34, 42],
        iconAnchor: [17, 39],
      }),
      title: "選択した地点",
    }).addTo(map);
  }, []);

  const loadDossier = useCallback(
    async (
      target: DossierTarget,
      options: { move?: boolean } = {},
    ) => {
      const requestId = ++dossierRequestId.current;
      if (searchTimer.current) {
        clearTimeout(searchTimer.current);
        searchTimer.current = null;
      }
      searchAbort.current?.abort();
      setCandidates([]);
      setActiveCandidateIndex(-1);
      setSearching(false);
      setError(null);
      setDossier(null);

      const showSelectedPoint = (lat: number, lng: number) => {
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
          "?lat=" +
            lat.toFixed(6) +
            "&lng=" +
            lng.toFixed(6) +
            "&mode=" +
            modeRef.current,
        );
      };

      const parameters = new URLSearchParams();
      if (target.kind === "point") {
        parameters.set("lat", String(target.lat));
        parameters.set("lng", String(target.lng));
        if (target.label) parameters.set("label", target.label);
        showSelectedPoint(target.lat, target.lng);
      } else {
        parameters.set("q", target.query);
      }

      dossierAbort.current?.abort();
      const controller = new AbortController();
      dossierAbort.current = controller;
      setSheetLevel("half");
      setLoadingDossier(true);
      try {
        const response = await fetch(
          "/api/v3/dossier?" + parameters.toString(),
          { signal: controller.signal },
        );
        const data = (await response.json()) as
          | LandDossier
          | { message?: string; error?: string };
        if (
          controller.signal.aborted ||
          requestId !== dossierRequestId.current
        ) {
          return;
        }
        if (!response.ok) {
          throw new Error(
            ("message" in data && data.message) ||
              ("error" in data && data.error) ||
              "この地点の土地情報をまとめられませんでした。",
          );
        }
        if (
          !("schemaVersion" in data) ||
          data.schemaVersion !== "land-dossier/1.0"
        ) {
          throw new Error("土地情報の形式を確認できませんでした。");
        }
        if (target.kind === "query") {
          setQuery(data.location.label);
          showSelectedPoint(data.location.lat, data.location.lng);
        }
        setDossier(data);
      } catch (caught) {
        if (
          (caught as Error).name !== "AbortError" &&
          !controller.signal.aborted &&
          requestId === dossierRequestId.current
        ) {
          setDossier(null);
          setError(
            caught instanceof Error
              ? caught.message
              : "土地情報の取得に失敗しました。",
          );
        }
      } finally {
        if (
          dossierAbort.current === controller &&
          requestId === dossierRequestId.current
        ) {
          setLoadingDossier(false);
        }
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
          alt: "東京23区・横浜市・川崎市の従来地形仮説・広域比較色分け（V10正本ではありません）",
          className: "iyashiro-overview",
        },
      ).addTo(map);
      cuolegaOverlayRef.current = L.imageOverlay(
        "/data/cuolega-grid-v2.png",
        CUOLEGA_BOUNDS,
        {
          pane: "cuolegaGrid",
          opacity: 0.9,
          alt: "クオレガ東京本社4.5km圏の従来地形仮説・100m比較",
          className: "cuolega-grid-overlay",
        },
      ).addTo(map);
      denentoshiOverlayRef.current = L.imageOverlay(
        "/data/denentoshi-shibuya-futako-grid-v2.png",
        DENENTOSHI_BOUNDS,
        {
          pane: "cuolegaGrid",
          opacity: 0.9,
          alt: "田園都市線の渋谷駅から二子玉川駅まで・線路中心1km帯の従来地形仮説・100m比較",
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
        void loadDossier({ kind: "point", lat: event.latlng.lat, lng: event.latlng.lng }),
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
        void loadDossier({ kind: "point", lat, lng }, { move: true });
    });
    return () => {
      disposed = true;
      dossierAbort.current?.abort();
      searchAbort.current?.abort();
      if (searchTimer.current) clearTimeout(searchTimer.current);
      gridAbort.current?.abort();
      mapRef.current?.remove();
      mapRef.current = null;
      overviewRef.current = null;
      cuolegaOverlayRef.current = null;
      denentoshiOverlayRef.current = null;
    };
  }, [loadDossier]);

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
          "従来地形仮説のクオレガ4.5km圏＋田園都市線1km沿線帯を比較表示中。拡大すると100m参考区画を確認できます。凍結V10正本と現行V15.3は地点詳細に表示します。",
        );
        return;
      }
      if (!precomputedGrids.length) {
        queueMicrotask(() =>
          setGridMessage(
            "従来地形仮説の100m比較区画を読み込み中。広域比較画像はすでに表示しています。",
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
          bubblingMouseEvents: false,
        });
        rectangle.bindTooltip(
          `従来地形仮説（V10正本ではありません）：${cell.label}｜地点詳細 ${cell.detailScore}｜交会ロジック点 ${cell.originalScore}`,
          {
            sticky: true,
            className: "map-tooltip",
          },
        );
        rectangle.on("click", () =>
          void loadDossier({ kind: "point", lat: cell.lat, lng: cell.lng }),
        );
        rectangle.addTo(layer);
      });
      setGridMessage(
        `従来地形仮説の比較区画を${visible.length}件表示中。クリックすると、凍結V10正本・現行V15.3・龍脈・回避条件・土地情報をまとめて確認できます。`,
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
            mode === "modern" ? cell.modern : cell.combined;
          const needsReview = gridAssessmentNeedsReview(value);
          const score = value.score;
          const opacity = needsReview
            ? 0.52
            : mode === "modern"
              ? 0.22 + cell.modern.completeness * 0.0046
              : 0.62;
          const tooltip =
            needsReview || score === null
              ? "資料不足・要確認｜未取得データを安全扱いしません"
              : `${value.label} ${score}/100`;
          const rectangle = L.rectangle(cell.bounds, {
            color: "rgba(255,255,255,.75)",
            weight: 1,
            fillColor:
              needsReview || score === null
                ? REVIEW_CELL_COLOR
                : safetyColor(score),
            fillOpacity: opacity,
            bubblingMouseEvents: false,
          });
          rectangle.bindTooltip(tooltip, {
            sticky: true,
            className: "map-tooltip",
          });
          rectangle.on("click", () =>
            void loadDossier({ kind: "point", lat: cell.lat, lng: cell.lng }),
          );
          rectangle.addTo(layer);
        });
        setGridMessage(
          cells.length
            ? `${cells.length}区画を概算表示中。クリックでこの地点の全情報を確認できます。`
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
  }, [loadDossier, mode, precomputedGrids, ready, revision]);

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

  useEffect(() => {
    if (!loadingDossier && (dossier || error)) {
      dossierSheetRef.current?.focus();
    }
  }, [dossier, error, loadingDossier]);

  const searchAddresses = useCallback((value: string) => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchAbort.current?.abort();
    setActiveCandidateIndex(-1);
    const normalized = value.trim();
    if (normalized.length < 2) {
      setCandidates([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    searchTimer.current = setTimeout(() => {
      const controller = new AbortController();
      searchAbort.current = controller;
      void fetch(
        `/api/search?q=${encodeURIComponent(normalized)}`,
        { signal: controller.signal },
      )
        .then(async (response) => {
          const data = (await response.json()) as { candidates?: Candidate[] };
          return response.ok ? data.candidates ?? [] : [];
        })
        .then((nextCandidates) => {
          if (!controller.signal.aborted) setCandidates(nextCandidates);
        })
        .catch((caught) => {
          if ((caught as Error).name !== "AbortError") setCandidates([]);
        })
        .finally(() => {
          if (searchAbort.current === controller) {
            searchAbort.current = null;
            setSearching(false);
          }
        });
    }, 320);
  }, []);

  const selectCandidate = (candidate: Candidate) => {
    setQuery(candidate.label);
    setActiveCandidateIndex(-1);
    void loadDossier(
      {
        kind: "point",
        lat: candidate.lat,
        lng: candidate.lng,
        label: candidate.label,
      },
      { move: true },
    );
  };

  const handleSearchKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" && candidates.length > 0) {
      event.preventDefault();
      setActiveCandidateIndex((current) =>
        current >= candidates.length - 1 ? 0 : current + 1,
      );
      return;
    }
    if (event.key === "ArrowUp" && candidates.length > 0) {
      event.preventDefault();
      setActiveCandidateIndex((current) =>
        current <= 0 ? candidates.length - 1 : current - 1,
      );
      return;
    }
    if (event.key === "Enter" && activeCandidateIndex >= 0) {
      event.preventDefault();
      selectCandidate(candidates[activeCandidateIndex]);
      return;
    }
    if (event.key === "Escape") {
      setCandidates([]);
      setActiveCandidateIndex(-1);
    }
  };

  const submitSearch = async (event: FormEvent) => {
    event.preventDefault();
    const normalizedQuery = query.trim();
    if (normalizedQuery.length < 2) return;

    setSearching(true);
    setError(null);
    try {
      await loadDossier(
        { kind: "query", query: normalizedQuery },
        { move: true },
      );
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
    const requestId = ++dossierRequestId.current;
    dossierAbort.current?.abort();
    setDossier(null);
    setError(null);
    setSheetLevel("half");
    setLoadingDossier(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        if (requestId !== dossierRequestId.current) return;
        setLoadingDossier(false);
        void loadDossier({ kind: "point", lat: position.coords.latitude, lng: position.coords.longitude }, {
          move: true,
        });
      },
      () => {
        if (requestId !== dossierRequestId.current) return;
        setLoadingDossier(false);
        setError("位置情報の許可を確認してください。");
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  };

  const modeMeta = useMemo(
    () => MODES.find((entry) => entry.key === mode) ?? MODES[0],
    [mode],
  );
  const dossierOpen = loadingDossier || Boolean(dossier) || Boolean(error);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const frame = window.requestAnimationFrame(() =>
      map.invalidateSize({ pan: false }),
    );
    const timer = window.setTimeout(
      () => map.invalidateSize({ pan: false }),
      280,
    );
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timer);
    };
  }, [dossierOpen]);

  useEffect(() => {
    const handleEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (infoOpen) setInfoOpen(false);
      else if (dossierOpen) closeDossier();
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [closeDossier, dossierOpen, infoOpen]);


  return (
    <main className={`map-app${dossierOpen ? " map-app--dossier-open" : ""}`}>
      <header className="top-shell">
        <div className="brand-row">
          <div>
            <p className="eyebrow">東京23区・横浜市・川崎市</p>
            <h1>土地を選んで、結論から見る。</h1>
          </div>
          <button
            className="round-button"
            type="button"
            aria-label="使い方と判定方法"
            onClick={() => setInfoOpen(true)}
          >
            ?
          </button>
        </div>
        <form className="search-box" data-testid="location-search" onSubmit={submitSearch}>
          <span className="search-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <circle cx="10.5" cy="10.5" r="6.5" />
              <path d="m15.5 15.5 5 5" />
            </svg>
          </span>
          <input
            ref={searchInputRef}
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={candidates.length > 0}
            aria-controls={candidates.length > 0 ? "location-suggestions" : undefined}
            aria-activedescendant={
              activeCandidateIndex >= 0
                ? "location-suggestion-" + activeCandidateIndex
                : undefined
            }
            value={query}
            onChange={(event) => {
              dossierRequestId.current += 1;
              dossierAbort.current?.abort();
              setLoadingDossier(false);
              setDossier(null);
              setError(null);
              setQuery(event.target.value);
              searchAddresses(event.target.value);
            }}
            onKeyDown={handleSearchKeyDown}
            placeholder="住所・地名・駅名を入力"
            aria-label="住所・地名・駅名を検索"
          />
          {query && (
            <button
              type="button"
              className="clear-search"
              aria-label="検索文字を消す"
              onClick={() => {
                setQuery("");
                setCandidates([]);
                setActiveCandidateIndex(-1);
                if (searchTimer.current) {
                  clearTimeout(searchTimer.current);
                  searchTimer.current = null;
                }
                dossierRequestId.current += 1;
                dossierAbort.current?.abort();
                searchAbort.current?.abort();
                setSearching(false);
                setLoadingDossier(false);
                setDossier(null);
                setError(null);
              }}
            >
              ×
            </button>
          )}
          <button className="search-submit" data-testid="location-search-submit" type="submit">
            {searching ? "検索中" : "調べる"}
          </button>
          {candidates.length > 0 && (
            <div className="suggestions" id="location-suggestions" role="listbox">
              {candidates.map((candidate, index) => (
                <button
                  key={`${candidate.lat}-${candidate.lng}`}
                  id={"location-suggestion-" + index}
                  type="button"
                  role="option"
                  aria-selected={index === activeCandidateIndex}
                  onClick={() => selectCandidate(candidate)}
                  onMouseEnter={() => setActiveCandidateIndex(index)}
                >
                  <span>{candidate.label}</span>
                  <small>この地点の全情報を見る</small>
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
              {entry.shortLabel}
            </button>
          ))}
        </nav>
      </header>

      <section className="map-stage" aria-label="土地判定地図">
        <div ref={nodeRef} className="map-canvas" data-testid="land-map" />
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
                <p className="eyebrow">参照レイヤー</p>
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
                <p className="eyebrow">地図の凡例</p>
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
                <strong>従来地形仮説の分類</strong>
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
            {mode !== "theory" && (
              <div className="classification-legend">
                <strong>資料不足の表示</strong>
                <span>
                  <i style={{ background: REVIEW_CELL_COLOR }} />
                  資料不足・要確認（安全扱いしない）
                </span>
              </div>
            )}
            <p className="panel-note">
              {mode === "theory"
                ? "この色分けは、標高データから作った従来の地形仮説を見比べるための参考レイヤーです。凍結済みのV10正本そのものではありません。正本V10と現行V15.3は地点詳細で確認します。"
                : "未取得データは安全とみなさず暫定表示します。"}
            </p>
          </aside>
        )}
      </section>

      {(loadingDossier || dossier || error) && (
        <aside
          ref={dossierSheetRef}
          className="result-sheet dossier-sheet"
          aria-label="選択した地点の土地カルテ"
          data-sheet-level={sheetLevel}
          aria-live="polite"
          aria-busy={loadingDossier}
          data-testid="dossier-sheet"
          tabIndex={-1}
        >
          <div className="sheet-grabber" />
          <div className="sheet-view-switcher" aria-label="土地カルテの表示量">
            <button
              type="button"
              className={sheetLevel === "peek" ? "active" : ""}
              aria-pressed={sheetLevel === "peek"}
              onClick={() => setSheetLevel("peek")}
            >
              地図中心
            </button>
            <button
              type="button"
              className={sheetLevel === "half" ? "active" : ""}
              aria-pressed={sheetLevel === "half"}
              onClick={() => setSheetLevel("half")}
            >
              要点
            </button>
            <button
              type="button"
              className={sheetLevel === "full" ? "active" : ""}
              aria-pressed={sheetLevel === "full"}
              onClick={() => setSheetLevel("full")}
            >
              全情報
            </button>
            <button
              type="button"
              className="sheet-view-close"
              aria-label="土地カルテを閉じる"
              onClick={closeDossier}
            >
              ×
            </button>
          </div>
          {loadingDossier && (
            <div className="loading-result" data-testid="dossier-loading">
              <span className="spinner" />
              <div>
                <strong>この地点の情報を一枚にまとめています</strong>
                <p>
                  回避条件、イヤシロジ、龍脈、地形、水、地盤、歴史、周辺施設を照合中です。
                </p>
              </div>
            </div>
          )}
          {!loadingDossier && error && (
            <div className="error-result" data-testid="dossier-error">
              <div>
                <p className="dossier-kicker">確認が必要です</p>
                <strong>この地点の土地情報をまとめられませんでした</strong>
                <p>{error}</p>
              </div>
              <button type="button" onClick={closeDossier}>
                閉じる
              </button>
            </div>
          )}
          {!loadingDossier && dossier && (
            <LandDossierPanel
              dossier={dossier}
              onClose={closeDossier}
              onOpenDetails={() => setSheetLevel("full")}
            />
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
                <p className="eyebrow">この地図について</p>
                <h2 id="info-title">判定方法と使い方</h2>
              </div>
              <button type="button" aria-label="説明を閉じる" onClick={() => setInfoOpen(false)}>
                ×
              </button>
            </div>
            <nav className="info-tool-links" aria-label="関連画面">
              <a href="/integrated">
                <strong>統合コパイロット</strong>
                <span>住所や物件URLからAIと全情報を見る</span>
              </a>
              <a href="/nexus">
                <strong>NEXUS 物件判定</strong>
                <span>物件条件と土地を分けて確認する</span>
              </a>
              <a href="/profile">
                <strong>従来の土地カルテ</strong>
                <span>100m区画の研究レイヤーを見る</span>
              </a>
            </nav>
            <div className="info-content">
              <article>
                <span>01</span>
                <div>
                  <h3>土地そのものは二本柱で見る</h3>
                  <p>
                    一本目は「イヤシロジ＝テライン仮説」です。地点詳細では、現在版の V15.3 と凍結済みの V10 正本を並べます。二本目は「龍脈」です。この二つを別の軸として並べ、どちらがどう評価されているかを確認できます。
                  </p>
                </div>
              </article>
              <article>
                <span>02</span>
                <div>
                  <h3>最初に、絶対に避けたい条件を確認</h3>
                  <p>
                    寺院・墓地・死亡を扱う病院などとの距離や、歴史上の大規模な死亡・収容に関わる場所を先に確認します。500mを基準にし、資料がない場合は「問題なし」にせず「情報不足」と表示します。
                  </p>
                </div>
              </article>
              <article>
                <span>03</span>
                <div>
                  <h3>根拠を五つに分けて全部表示</h3>
                  <p>
                    地形、水、地盤、歴史、周辺施設の順に、分かっていること、該当しなかったこと、まだ分からないことを日本語で説明します。地名の由来と、次に集めるべき不足情報も同じ画面で確認できます。
                  </p>
                </div>
              </article>
              <article>
                <span>AI</span>
                <div>
                  <h3>AIからも同じ全情報を取得</h3>
                  <p>
                    地図クリックも住所検索も、最終的には
                    <code>/api/v3/dossier?q=住所</code> または{" "}
                    <code>/api/v3/dossier?lat=緯度&amp;lng=経度</code>
                    から同じ形式のJSONを取得します。{" "}
                    <a href="/openapi-v3.json" target="_blank" rel="noreferrer">
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
