// 지도 패널: Canvas 2D 한 장. 점·선을 DOM/React 요소로 만들지 않는다(spec 318 지도 성능 원칙).
// - 경계·등고선은 월드 좌표로 Path2D를 한 번만 만들고, 그릴 때는 변환 행렬만 바꾼다.
// - 점은 줌에 따라 반경이 다른 화면 거리 묶기(전국 100px, 그 밖 86px)로 묶고 묶음 단위로 그린다.
// - 다시 그리기는 바뀔 때만 rAF 한 번. 보기(확대·이동)는 ref에 두어 마우스 움직임이 React를 다시 그리지 않는다.
// - 움직이는 동안은 등고선을 건너뛰고 멈춘 뒤 그린다(옛 지도와 같음).
// - 휠은 지도 안에서만 쓰이고 페이지 스크롤로 새지 않는다.
import { useEffect, useMemo, useRef, useState } from "react";
import { formatSlot, type GeoRegion, type SiteState } from "../data/model";
import LevelMark from "../dashboard/LevelMark";
import { LEVELS, type LevelKey } from "../logic/status";
import { useSelection, type MapShowKey } from "../state/selection";
import { useTheme } from "../theme/theme";
import {
  beamHeight, boundsOf, canSeparate, carryClusters, clusterRadius, clusterRadiusMerge, fitView, pinHit, project, rankOf,
  toScreen, zoomAt, zoomGrade, clampView, minScaleFor, centeredOn, easeOutCubic, interpolateView, needsFocus, stepZoomView, flightDuration, FOCUS_SCALE, MAX_SCALE, MIN_SCALE,
  type Bounds, type Cluster, type View,
} from "./geometry";
import { ContourStore, contourPlan, contourStyle, filesFor, groupByElevation, loadIndex, visibleLines, type ContourIndex } from "./contours";
import { freshAlerts, ranksOf, type RankMap } from "./freshAlerts";
import Compass from "./Compass";
import MapClock from "./MapClock";
import MapKindSelect from "./naver/MapKindSelect";
import { loadNaverSdk, naverKeyId, onNaverAuthFailure, NAVER_NOTES } from "./naver/loader";
import { readMapMode, writeMapMode, type MapMode } from "./naver/mode";
import { createNaverMap, type NaverCallbacks, type NaverController } from "./naver/NaverController";
import { NAVER_ZOOM, focusTarget, needsNaverFocus, targetOfView } from "./naver/viewMath";
import naverStyles from "./naver/NaverMap.module.css";
import { visibleIndices } from "./mapFilter";
import { regionAtCenter } from "./regionAtCenter";
import styles from "./MapPanel.module.css";

interface Props {
  states: SiteState[];
  geo: GeoRegion[];
  times: number[];
  slot: number;
  onSlot: (slot: number) => void;
}

type Ring = Array<[number, number]>;
interface Region {
  name: string;
  polys: Ring[][]; // 다각형마다 [바깥 고리, 구멍…] (월드 좌표)
  path: Path2D | null;
  bounds: Bounds;
}

const RANK_LEVEL: Array<LevelKey> = ["ok", "caution", "warn", "risk", "exceed"];
const cssVar = (el: Element, name: string) => getComputedStyle(el).getPropertyValue(name).trim();

function buildRegions(geo: GeoRegion[]): Region[] {
  return geo.map((g) => {
    const polygons = (g.type === "Polygon" ? [g.coordinates] : g.coordinates) as number[][][][];
    const polys = polygons.map((poly) => poly.map((ring) => ring.map(([lon, lat]) => project(lon, lat))));
    const all = polys.flat(2);
    let path: Path2D | null = null;
    if (typeof Path2D !== "undefined") {
      path = new Path2D();
      for (const poly of polys) for (const ring of poly) {
        ring.forEach(([x, y], i) => (i === 0 ? path!.moveTo(x, y) : path!.lineTo(x, y)));
        path.closePath();
      }
    }
    return { name: g.name, polys, path, bounds: boundsOf(all)! };
  });
}

/** 선택 표시: 사업장의 실제 위치(x, y)를 꼭짓점으로 가리키는 노란 아래 화살표(어두운 테두리로 어느 배경에서도 보인다) */
function drawSelectArrow(ctx: CanvasRenderingContext2D, x: number, y: number, color: string) {
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(x + 9, y - 11);
  ctx.lineTo(x + 3.5, y - 11);
  ctx.lineTo(x + 3.5, y - 24);
  ctx.lineTo(x - 3.5, y - 24);
  ctx.lineTo(x - 3.5, y - 11);
  ctx.lineTo(x - 9, y - 11);
  ctx.closePath();
  ctx.lineJoin = "round";
  ctx.lineWidth = 2;
  ctx.strokeStyle = "rgba(10, 17, 15, 0.9)";
  ctx.stroke();
  ctx.fillStyle = color;
  ctx.fill();
}


/**
 * 옛 지도의 굴뚝 표시: 땅 위의 타원 후광 + 위로 솟는 빛기둥(아래가 진하고 위로 갈수록 투명) + 바닥 받침 + 개수 배지.
 * (x, y)가 받침, 곧 사업장의 실제 위치다.
 */
function drawPin(
  ctx: CanvasRenderingContext2D, x: number, y: number,
  o: { color: string; level: LevelKey | null; count: number; hot: boolean; ink: string; bg: string; accent: string },
) {
  const strong = o.level !== null && o.level !== "ok";
  if (o.hot) { ctx.shadowColor = o.color; ctx.shadowBlur = 18; } // 마우스를 올리면 조명이 켜진다
  // 후광(타원)
  ctx.beginPath();
  ctx.ellipse(x, y, strong ? 22 : 13, strong ? 7 : 4, 0, 0, Math.PI * 2);
  ctx.globalAlpha = strong ? 0.16 : 0.1;
  ctx.fillStyle = o.color;
  ctx.fill();
  ctx.globalAlpha = o.hot ? 1 : 0.65;
  ctx.lineWidth = o.hot ? 2 : 1;
  ctx.strokeStyle = o.hot ? o.accent : o.color;
  ctx.stroke();
  ctx.globalAlpha = 1;
  // 빛기둥
  // 단계별 빛기둥 높이(geometry와 같은 표를 쓴다: 클릭 범위와 그림이 어긋나지 않게). 정상·공백은 기둥 없이 받침만
  const bh = beamHeight(rankOf(o.level));
  if (bh) {
    const g = ctx.createLinearGradient(0, y - bh, 0, y);
    g.addColorStop(0, "transparent");
    g.addColorStop(1, o.color);
    ctx.beginPath();
    ctx.moveTo(x - 1.6, y - bh); ctx.lineTo(x + 1.6, y - bh); ctx.lineTo(x + 5, y); ctx.lineTo(x - 5, y);
    ctx.closePath();
    ctx.fillStyle = g;
    ctx.fill();
  }
  // 받침
  ctx.beginPath();
  ctx.ellipse(x, y, 5, 3, 0, 0, Math.PI * 2);
  ctx.fillStyle = o.color;
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.shadowColor = "transparent";
  // 개수 배지(묶음일 때만): 기둥 옆
  if (o.count > 1) {
    const text = String(o.count);
    const w = Math.max(36, ctx.measureText(text).width + 20), h = 28; // 글자를 크게(16px) 하므로 배지도 키운다
    const bx = x + 7, by = y - Math.max(bh, 24) - 4;
    ctx.beginPath();
    ctx.roundRect(bx, by, w, h, 3);
    ctx.fillStyle = o.bg;
    ctx.fill();
    ctx.lineWidth = 1;
    ctx.strokeStyle = o.color;
    ctx.stroke();
    ctx.fillStyle = o.ink;
    ctx.fillText(text, bx + w / 2, by + h / 2 + 0.5);
  }
}

const RIPPLE_MS = 1800; // 마우스를 올렸을 때 수면 파형 한 번의 길이(옛 지도와 같음)
const FLARE_MS = 700; // 새로 경고가 된 굴뚝이 번쩍이는 시간

/** 수면 파형: 후광 타원이 퍼져 나가며 사라지는 고리 두 겹 */
function drawRipples(ctx: CanvasRenderingContext2D, x: number, y: number, color: string, now: number, still: boolean) {
  ctx.strokeStyle = color;
  ctx.lineWidth = 2.2;
  for (const offset of [0, 0.5]) {
    const phase = still ? 0.35 + offset * 0.4 : ((now / RIPPLE_MS) + offset) % 1;
    ctx.globalAlpha = 0.65 * (1 - phase);
    const k = 1 + 0.9 * phase;
    ctx.beginPath();
    ctx.ellipse(x, y, 23 * k, 7 * k, 0, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
}

/** 새로 경고가 된 굴뚝: 한 번 번쩍이며 퍼지는 고리(옛 지도의 pin-alert-flare). 끝나면 true */
function drawFlare(ctx: CanvasRenderingContext2D, x: number, y: number, color: string, t: number): boolean {
  if (t >= 1) return true;
  const a = t < 0.18 ? (t / 0.18) * 0.95 : 0.95 * (1 - (t - 0.18) / 0.82);
  const k = 0.65 + 1.2 * t;
  ctx.globalAlpha = Math.max(0, a);
  ctx.shadowColor = color;
  ctx.shadowBlur = 12;
  ctx.lineWidth = 2;
  ctx.strokeStyle = color;
  ctx.beginPath();
  ctx.ellipse(x, y, 23 * k, 7 * k, 0, 0, Math.PI * 2);
  ctx.stroke();
  ctx.fillStyle = color;
  ctx.globalAlpha = Math.max(0, a * 0.16);
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.shadowColor = "transparent";
  ctx.globalAlpha = 1;
  return false;
}

const reducedMotion = () =>
  typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** 지도에 표시할 상태 칩: 정상·주의·경고·위험·초과 + 공백(측정값 없음: 미수신·점검·가동중지 등) */
const SHOW_CHIPS: Array<{ key: MapShowKey; label: string; hint: string }> = [
  ...LEVELS.map((l) => ({ key: l.key as MapShowKey, label: l.label, hint: `${l.label} 굴뚝 표시` })),
  { key: "gap", label: "공백", hint: "측정값이 없는 굴뚝 표시(미수신·점검·가동중지 등)" },
];

const SPEEDS = [
  { label: "0.5×", ms: 3200 },
  { label: "1×", ms: 1600 },
  { label: "2×", ms: 800 },
  { label: "4×", ms: 400 },
] as const;

const MIN_SPAN = 0.06; // 보기를 맞출 때 최소 범위(세계 좌표). 점이 한곳에 모여 있어도 너무 확대되지 않게

function spanBounds(b: Bounds): Bounds {
  const cx = (b.minX + b.maxX) / 2, cy = (b.minY + b.maxY) / 2;
  const hx = Math.max((b.maxX - b.minX) / 2, MIN_SPAN), hy = Math.max((b.maxY - b.minY) / 2, MIN_SPAN);
  return { minX: cx - hx, maxX: cx + hx, minY: cy - hy, maxY: cy + hy };
}

export default function MapPanel({ states, geo, times, slot, onSlot }: Props) {
  const { theme } = useTheme();
  const selectedSiteId = useSelection((s) => s.selectedSiteId);
  const mapPath = useSelection((s) => s.mapPath);
  const selectSite = useSelection((s) => s.selectSite);
  const setMapPath = useSelection((s) => s.setMapPath);
  const setMapBounds = useSelection((s) => s.setMapBounds);
  const mapLevels = useSelection((s) => s.mapLevels);
  const toggleMapLevel = useSelection((s) => s.toggleMapLevel);
  const clearSelection = useSelection((s) => s.clearSelection);

  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const viewRef = useRef<View>({ scale: 1, ox: 0, oy: 0 });
  const sizeRef = useRef({ w: 0, h: 0, dpr: 1 });
  const clustersRef = useRef<Cluster[]>([]);
  const clusterView = useRef<{ view: View; clusters: Cluster[] } | null>(null);
  const visibleRef = useRef<number[]>([]);
  const rafRef = useRef(0);
  const hoverRef = useRef(-1);
  const movingRef = useRef(false);
  const animRef = useRef<{ from: View; to: View; start: number; dur: number } | null>(null);
  const settleTimer = useRef(0);
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);
  // 확대해도 안 갈라지는 묶음(좌표가 사실상 같은 사업장들)을 눌렀을 때 뜨는 고르기 목록
  const [picker, setPicker] = useState<{ x: number; y: number; items: SiteState[] } | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speedIdx, setSpeedIdx] = useState(1);
  const stepMs = SPEEDS[speedIdx].ms;
  const slotRef = useRef(slot);
  slotRef.current = slot;
  const last = Math.max(times.length - 1, 0);
  const effects = useRef(new Map<string, { start: number; color: string }>());
  const baseCache = useRef<{ key: string; view: View; rough: boolean; mw: number; mh: number; canvas: HTMLCanvasElement } | null>(null);
  const contourVersion = useRef(0);
  const requested = useRef(new Set<string>());
  // 기본은 꺼짐: 등고선 자료는 저장소에 올리지 않아(나중에 추적 여부를 정한다) 운영 빌드에 없을 수 있다. 켤 때만 읽는다.
  const [contourOn, setContourOn] = useState(false);
  const contourOnRef = useRef(false);
  contourOnRef.current = contourOn;

  const contourIndex = useRef<ContourIndex | null>(null);
  const contourStore = useRef(new ContourStore());

  // ── 지도 종류: 관제 지도(Canvas, 기본) / 네이버 일반 / 네이버 위성 ──────────
  // 네이버 모드에서는 이동·확대를 네이버가 맡고, 우리는 그 위에 투명한 캔버스로 핀·묶음·선택 표시만 겹쳐 그린다.
  // 핀 그리기·묶기·선택·클릭 판정은 관제 지도와 같은 코드를 쓴다(보기는 네이버 투영에서 읽어 온다).
  const [mode, setMode] = useState<MapMode>("control");
  const modeRef = useRef<MapMode>("control");
  const [naverBusy, setNaverBusy] = useState(false);
  const [naverNote, setNaverNote] = useState("");
  const hostRef = useRef<HTMLDivElement>(null);
  const naverRef = useRef<NaverController | null>(null);
  const modeToken = useRef(0);
  const naverOn = mode !== "control";

  const regions = useMemo(() => buildRegions(geo), [geo]);
  const landPath = useMemo(() => {
    if (typeof Path2D === "undefined") return null;
    const p = new Path2D();
    for (const r of regions) if (r.path) p.addPath(r.path);
    return p;
  }, [regions]);
  // 사업장 위치는 시각이 바뀌어도 그대로다. 재생 중 칸마다 새로 만들지 않도록 사업장 목록이 바뀔 때만 계산한다.
  const siteKey = `${states.length}:${states[0]?.site.id ?? ""}:${states[states.length - 1]?.site.id ?? ""}`;
  const projected = useMemo(() => {
    // 깊이 확대(1px ≈ 3.6m)에서도 위치가 흔들리지 않게 64비트로 둔다(32비트는 약 1px 흔들린다)
    const xs = new Float64Array(states.length), ys = new Float64Array(states.length);
    states.forEach((st, i) => { const [x, y] = project(st.site.lon, st.site.lat); xs[i] = x; ys[i] = y; });
    return { xs, ys };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteKey]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const indexById = useMemo(() => new Map(states.map((st, i) => [st.site.id, i])), [siteKey]);
  // 지도에 그릴 사업장: 지역을 골라도 숨기지 않는다(자유 이동). 다만 사용자가 끈 경고 단계(주의~초과)는 그리지 않는다
  const favorites = useSelection((s) => s.favorites);
  const favoritesOnly = useSelection((s) => s.favoritesOnly);
  const setFavoritesOnly = useSelection((s) => s.setFavoritesOnly);
  const visibleIdx = useMemo(
    () => visibleIndices(states, mapLevels, favoritesOnly ? new Set(favorites) : null),
    [states, mapLevels, favoritesOnly, favorites],
  );
  visibleRef.current = visibleIdx;

  // ── 보기: 처음(전국)에 맞추기, 부드러운 이동 ──────────────────────
  // 지역은 눌러서 가는 것이 아니라 확대·이동한 뒤 화면 중앙을 보고 판단한다(아래 syncPath).
  /** 지도 전체 범위(세계 좌표): 지역 경계가 있으면 그 범위, 못 읽었으면 한국 전체 범위 */
  const nationBounds = useMemo<Bounds>(() => {
    if (!regions.length) {
      const [x0, y0] = project(124.6, 38.7), [x1, y1] = project(131.9, 33.0);
      return { minX: x0, minY: y0, maxX: x1, maxY: y1 };
    }
    return {
      minX: Math.min(...regions.map((r) => r.bounds.minX)), minY: Math.min(...regions.map((r) => r.bounds.minY)),
      maxX: Math.max(...regions.map((r) => r.bounds.maxX)), maxY: Math.max(...regions.map((r) => r.bounds.maxY)),
    };
  }, [regions]);
  const nationView = (): View | null => {
    const { w, h } = sizeRef.current;
    if (!w || !h) return null;
    return fitView(nationBounds, w, h, 28);
  };
  /**
   * 관제 지도의 확대·이동 한계: 전국이 화면에 꽉 차는 배율보다 더 줄일 수 없고, 지도를 화면 밖으로 밀어낼 수 없다.
   * (네이버 지도는 자체 한도가 있다: 확대 6~18, 한국 범위)
   */
  const limitMinScale = () => { const { w, h } = sizeRef.current; return w && h ? minScaleFor(nationBounds, w, h) : MIN_SCALE; };
  const constrain = (v: View): View => {
    const { w, h } = sizeRef.current;
    if (modeRef.current !== "control" || !w || !h) return v;
    return clampView(v, nationBounds, w, h, limitMinScale());
  };
  // 휠·크기 변경처럼 한 번만 걸어 두는 효과에서도 늘 최신 한계를 쓰도록 ref로 건다
  const constrainRef = useRef(constrain);
  constrainRef.current = constrain;
  const minScaleRef = useRef(limitMinScale);
  minScaleRef.current = limitMinScale;
  /** 처음·크기가 처음 정해질 때 바로 맞춘다 */
  const fit = () => { const v = nationView(); if (v) viewRef.current = v; };
  /** 보기를 부드럽게 옮긴다(알아서 넘어가는 이동). 모션 감소 설정이거나 크기를 아직 모르면 바로 옮긴다 */
  const flyTo = (to: View, rounding: "round" | "floor" = "round") => {
    to = constrain(to); // 도착점은(바로 옮기는 경우도) 지도 범위 안으로. 네이버 모드는 그대로
    const { w, h } = sizeRef.current;
    const nv = naverRef.current;
    if (nv && w && h) { if (!reducedMotion()) hidePinsRef.current(); nv.moveTo(targetOfView(to, w, h, rounding), !reducedMotion()); return; } // 네이버 모드: 이동은 네이버가 한다
    if (!w || !h || reducedMotion()) { animRef.current = null; viewRef.current = to; scheduleRef.current(); syncRef.current(); return; }
    const from = { ...viewRef.current };
    animRef.current = { from, to, start: performance.now(), dur: flightDuration(from.scale, to.scale) };
    movingRef.current = true; // 날아가는 동안은 묶음·등고선을 새로 계산하지 않고 따라 옮겨 그린다
    window.clearTimeout(settleTimer.current);
    scheduleRef.current();
  };
  /** 멈춘 뒤 화면 중앙을 보고 지금 어느 지역인지 판단한다(경고 목록을 거르고 위치 표시를 채운다). 지도는 움직이지 않는다 */
  const syncPath = () => {
    const { w, h } = sizeRef.current;
    if (!w || !h) return;
    // 지금 보여 주는 범위를 알린다: 경고 목록이 "지도에 보이는 사업장"만 보여 주는 데 쓴다
    const v = viewRef.current;
    setMapBounds({ minX: -v.ox / v.scale, minY: -v.oy / v.scale, maxX: (w - v.ox) / v.scale, maxY: (h - v.oy) / v.scale });
    const sites = states.map((st, i) => ({ sido: st.site.sido, sigungu: st.site.sigungu, x: projected.xs[i], y: projected.ys[i] }));
    setMapPath(regionAtCenter(viewRef.current, w, h, regions, sites));
  };
  /** 사용자가 직접 끌거나 휠을 돌리면 자동 이동을 멈춘다 */
  const cancelFlight = () => {
    if (!animRef.current) return;
    animRef.current = null;
    movingRef.current = false;
  };

  // ── 등고선: 필요한 파일을 읽고, 다 읽히면 바닥 레이어를 새로 그린다 ──────
  const ensureContours = (viewport: Bounds, source: "overview" | "regions") => {
    const idx = contourIndex.current;
    if (!idx) return;
    for (const f of filesFor(idx, source, viewport)) {
      if (contourStore.current.get(f) || requested.current.has(f)) continue;
      requested.current.add(f);
      contourStore.current.load(f).then(
        () => { contourVersion.current++; scheduleRef.current(); },
        () => { requested.current.delete(f); }, // 실패하면 다음에 다시 시도
      );
    }
  };

  /** 바닥 레이어(땅·등고선·경계): 보기·테마·경로가 바뀔 때만 다시 그리고, 애니메이션 프레임에서는 그림만 복사한다 */
  const drawBase = (ctx: CanvasRenderingContext2D, css: (n: string) => string, view: View, w: number, h: number, dpr: number, withContours: boolean) => {
    const viewport: Bounds = { minX: -view.ox / view.scale, minY: -view.oy / view.scale, maxX: (w - view.ox) / view.scale, maxY: (h - view.oy) / view.scale };
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.save();
    ctx.setTransform(dpr * view.scale, 0, 0, dpr * view.scale, dpr * view.ox, dpr * view.oy);
    ctx.lineJoin = "round";
    for (const r of regions) {
      if (!r.path) continue;
      ctx.globalAlpha = 1; // 고른 지역 말고도 모두 같은 밝기(지도를 지역에 가두지 않는다)
      ctx.fillStyle = css("--map-land");
      ctx.fill(r.path, "evenodd");
    }
    ctx.globalAlpha = 1;

    if (contourOnRef.current && withContours && landPath && contourIndex.current) {
      // 확대 등급에 따라 읽을 파일과 그릴 선이 달라진다: 넓게 볼 때는 큰 파일을 읽지 않는다(처음 로딩을 줄인다)
      const plan = contourPlan(zoomGrade(view.scale));
      const files = filesFor(contourIndex.current, plan.source, viewport);
      const sets = files.map((f) => contourStore.current.get(f)).filter((x): x is NonNullable<typeof x> => !!x);
      if (files.length) ensureContours(viewport, plan.source);
      if (sets.length) {
        ctx.save();
        ctx.clip(landPath, "evenodd"); // 땅 안쪽만
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        const groups = groupByElevation(visibleLines(sets, viewport));
        // 낮은 곳부터 그려 높은 곳이 위에 온다. 색은 고도 색상표(차분한 색조)
        for (const [elevation, group] of groups) {
          const st = contourStyle(elevation, plan.thin, plan.bold, theme === "light");
          if (st.alpha <= 0) continue; // 굵은 선만 보이는 등급에서는 얇은 선을 건너뛴다
          ctx.strokeStyle = st.color;
          ctx.globalAlpha = st.alpha;
          ctx.lineWidth = st.width / view.scale; // 확대해도 화면 기준 굵기를 유지
          for (const l of group) if (l.path) ctx.stroke(l.path);
        }
        ctx.restore();
      }
    }

    for (const r of regions) {
      if (!r.path) continue;
      const active = mapPath.sido === r.name; // 고른 지역만 경계선을 살짝 강조
      ctx.lineWidth = (active ? 1.8 : 1.1) / view.scale;
      ctx.strokeStyle = active ? css("--accent") : css("--map-line");
      ctx.globalAlpha = active ? 0.7 : 1;
      ctx.stroke(r.path);
    }
    ctx.restore();
  };

  // ── 그리기 ────────────────────────────────────────────────────
  const draw = () => {
    rafRef.current = 0;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const { w, h, dpr } = sizeRef.current;
    const now = performance.now();
    const still = reducedMotion();
    const flight = animRef.current;
    if (flight) { // 알아서 넘어가는 이동: 한 걸음씩 보기를 옮긴다
      const t = (now - flight.start) / flight.dur;
      if (t >= 1) { viewRef.current = flight.to; animRef.current = null; movingRef.current = false; syncRef.current(); }
      else viewRef.current = interpolateView(flight.from, flight.to, easeOutCubic(t), w, h);
    }
    const view = viewRef.current;
    const css = (n: string) => cssVar(canvas, n);

    // 바닥 레이어: 키가 같으면 이미 그려 둔 그림을 그대로 쓴다. 네이버 모드는 땅·등고선·경계를 그리지 않는다(네이버가 그린다)
    const onNaver = modeRef.current !== "control";
    if (!onNaver) {
      // 화면보다 사방 50% 큰 그림을 한 장 그려 두고, 움직이는 동안에는 새로 그리지 않고 옮기고 늘려서 쓴다(등고선도 같이 움직인다).
      // 멈추면 새 보기로 선명하게 다시 그린다. 그림이 화면을 다 덮지 못하거나 배율이 너무 달라지면 그때만 지금 보기로 다시 그린다(등고선 없이).
      const staticKey = [w, h, dpr, mapPath.sido, theme, contourOnRef.current, contourVersion.current, regions.length].join("|");
      const c = baseCache.current;
      const moving = movingRef.current;
      let fresh = !c || c.key !== staticKey;
      if (c && !fresh) {
        const same = Math.abs(c.view.scale - view.scale) < 1e-9 && Math.abs(c.view.ox - view.ox) < 0.01 && Math.abs(c.view.oy - view.oy) < 0.01;
        if (!moving) fresh = !same || c.rough; // 멈췄으면 지금 보기로 선명한 그림이어야 한다
        else {
          const k = view.scale / c.view.scale;
          const tx = view.ox - k * c.view.ox, ty = view.oy - k * c.view.oy;
          // 지금 화면 네 모서리가 옛 그림(여유 포함) 안에 드는지
          const covered = (-tx) / k >= -c.mw && (w - tx) / k <= w + c.mw && (-ty) / k >= -c.mh && (h - ty) / k <= h + c.mh;
          fresh = !covered || k < 0.55 || k > 2;
        }
      }
      if (fresh) {
        const mw = Math.round(w * 0.5), mh = Math.round(h * 0.5);
        const off = c?.canvas ?? document.createElement("canvas");
        off.width = Math.round((w + 2 * mw) * dpr);
        off.height = Math.round((h + 2 * mh) * dpr);
        const octx = off.getContext("2d");
        const rough = moving;
        if (octx) drawBase(octx, css, { scale: view.scale, ox: view.ox + mw, oy: view.oy + mh }, w + 2 * mw, h + 2 * mh, dpr, !rough);
        baseCache.current = { key: staticKey, view: { ...view }, rough, mw, mh, canvas: off };
      }
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!onNaver && baseCache.current) {
      const c = baseCache.current;
      const k = view.scale / c.view.scale;
      ctx.setTransform(dpr * k, 0, 0, dpr * k, dpr * (view.ox - k * c.view.ox), dpr * (view.oy - k * c.view.oy));
      ctx.drawImage(c.canvas, -c.mw, -c.mh, c.canvas.width / dpr, c.canvas.height / dpr);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    if (zoomHide.current && onNaver) return; // 확대 중에는 핀을 그리지 않는다(지워진 채로 둔다)
    // 점: 멈춰 있을 때만 화면 좌표로 바꿔 묶는다. 움직이는 동안은 직전 묶음을 그대로 따라 옮겨 그린다(놓으면 갱신)
    const vis = visibleRef.current;
    let clusters: Cluster[];
    const cached = clusterView.current;
    if (movingRef.current && cached) {
      clusters = carryClusters(cached.clusters, cached.view, view);
    } else {
      const xs = new Float32Array(vis.length), ys = new Float32Array(vis.length), ranks = new Int8Array(vis.length);
      for (let k = 0; k < vis.length; k++) {
        const i = vis[k];
        const [sx, sy] = toScreen(view, projected.xs[i], projected.ys[i]);
        xs[k] = sx; ys[k] = sy; ranks[k] = rankOf(states[i].level);
      }
      clusters = clusterRadiusMerge(xs, ys, ranks, clusterRadius(view.scale), w, h);
      clustersRef.current = clusters;
      clusterView.current = { view: { ...view }, clusters };
    }
    const colorOf = (rank: number) => (rank < 0 ? css("--gap-from") : css(`--lv-${RANK_LEVEL[rank]}`));
    const ink = css("--map-ink"), bg = css("--stage-bg"), accent = css("--accent");
    // 높은 단계를 나중에 그려 위에 오게 한다(같은 단계는 위쪽(먼 쪽)부터)
    const order = clusters.map((_, i) => i).sort((a, b) => clusters[a].maxRank - clusters[b].maxRank || clusters[a].y - clusters[b].y);
    ctx.font = "700 17px ui-monospace, Consolas, monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const hovered = movingRef.current ? -1 : hoverRef.current;
    for (const ci of order) {
      const c = clusters[ci];
      if (c.x < -60 || c.y < -90 || c.x > w + 60 || c.y > h + 40) continue;
      const color = colorOf(c.maxRank);
      if (ci === hovered) drawRipples(ctx, c.x, c.y, color, now, still); // 수면 파형
      drawPin(ctx, c.x, c.y, {
        color, level: c.maxRank < 0 ? null : RANK_LEVEL[c.maxRank], count: c.count,
        hot: ci === hovered, ink, bg, accent,
      });
    }
    // 어느 묶음에 들어 있는지(사업장 번호 → 묶음 번호). 번쩍임은 묶음 기준이다:
    // 넓게 보면 묶음 하나가, 확대해서 풀리면 그 굴뚝 하나가 번쩍인다.
    const clusterOf = new Map<number, number>();
    clusters.forEach((c, ci) => { for (const m of c.members) clusterOf.set(vis[m], ci); });

    // 새로 경고가 된 굴뚝이 속한 묶음: 묶음당 한 번만 번쩍인다
    let animating = (hovered >= 0 && !still) || animRef.current !== null;
    const flared = new Set<number>();
    for (const [id, f] of effects.current) {
      const idx = indexById.get(id);
      const t = (now - f.start) / FLARE_MS;
      if (idx === undefined || t >= 1) { effects.current.delete(id); continue; }
      animating = true;
      const ci = clusterOf.get(idx);
      if (ci === undefined || flared.has(ci)) continue;
      flared.add(ci);
      const c = clusters[ci];
      if (c.x > -40 && c.y > -40 && c.x < w + 40 && c.y < h + 40) {
        drawFlare(ctx, c.x, c.y, c.maxRank < 0 ? f.color : colorOf(c.maxRank), t);
      }
    }
    // 선택 표시: 묶음과 상관없이 선택한 사업장의 실제 좌표를 꼭짓점으로 가리키는 노란 아래 화살표
    if (selectedSiteId) {
      const idx = indexById.get(selectedSiteId);
      if (idx !== undefined) {
        const [sx, sy] = toScreen(view, projected.xs[idx], projected.ys[idx]);
        if (sx > -30 && sy > -10 && sx < w + 30 && sy < h + 30) drawSelectArrow(ctx, sx, sy, css("--map-select"));
      }
    }
    // 애니메이션이 남아 있을 때만 다음 프레임을 부른다(가만히 있으면 아무 일도 하지 않는다)
    if (animating) scheduleRef.current();
  };

  // 효과·이벤트에서 늘 최신 draw/fit을 쓰도록 ref로 건다(낡은 상태를 그리지 않게)
  const drawRef = useRef(draw);
  drawRef.current = draw;
  const fitRef = useRef(fit);
  fitRef.current = fit;
  const scheduleRef = useRef(() => {});
  scheduleRef.current = () => {
    if (!rafRef.current) rafRef.current = requestAnimationFrame(() => drawRef.current());
  };
  const syncRef = useRef(() => {});
  syncRef.current = syncPath;
  const schedule = () => scheduleRef.current();

  /** 움직이는 중임을 알리고, 멈추면 등고선까지 다시 그린다 */
  const markMoving = () => {
    movingRef.current = true;
    window.clearTimeout(settleTimer.current);
    settleTimer.current = window.setTimeout(() => { movingRef.current = false; scheduleRef.current(); syncRef.current(); }, 160);
  };

  // 등고선 목록은 처음 한 번 읽는다(없으면 등고선 없이 동작)
  // 처음 로딩을 줄이기 위해 첫 화면(지도·사업장)이 그려진 뒤, 브라우저가 한가할 때 읽는다.
  useEffect(() => {
    if (!contourOn || contourIndex.current) return; // 꺼져 있으면 읽지 않는다(이미 읽었으면 다시 읽지 않는다)
    let alive = true;
    const load = () => loadIndex().then((idx) => { if (alive) { contourIndex.current = idx; scheduleRef.current(); } }, () => {});
    const w = window as Window & { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number; cancelIdleCallback?: (id: number) => void };
    if (w.requestIdleCallback) {
      const id = w.requestIdleCallback(load, { timeout: 1500 });
      return () => { alive = false; w.cancelIdleCallback?.(id); };
    }
    const t = window.setTimeout(load, 600);
    return () => { alive = false; window.clearTimeout(t); };
  }, [contourOn]);

  // 크기: 컨테이너를 따라가고 DPR을 반영한다
  useEffect(() => {
    const wrap = wrapRef.current, canvas = canvasRef.current;
    if (!wrap || !canvas) return;
    const apply = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = wrap.clientWidth, h = wrap.clientHeight;
      const prev = sizeRef.current;
      sizeRef.current = { w, h, dpr };
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      const nv = naverRef.current;
      if (nv) { nv.setSize(w, h); viewRef.current = nv.getView(); } // 네이버 모드: 지도 크기를 맞추고 보기는 지도에서 다시 읽는다
      else if (!prev.w) fitRef.current(); // 처음에만 맞춘다
      else { // 크기가 바뀌어도 보던 곳을 그대로 보게 중심을 유지한다(사용자의 확대·위치를 되돌리지 않는다)
        const v = viewRef.current;
        viewRef.current = constrainRef.current({ ...v, ox: v.ox + (w - prev.w) / 2, oy: v.oy + (h - prev.h) / 2 });
      }
      scheduleRef.current();
      syncRef.current(); // 크기가 바뀌면 보이는 범위도 바뀐다
    };
    apply();
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(apply) : null;
    ro?.observe(wrap);
    return () => { ro?.disconnect(); cancelAnimationFrame(rafRef.current); rafRef.current = 0; window.clearTimeout(settleTimer.current); };
  }, []);

  // 지도가 처음 준비되면 전국에 맞춘다(한 번만). 그 뒤로는 사용자가 확대·이동한 대로 둔다.
  // 시각이 바뀔 때(재생 중 칸마다)는 보기를 건드리지 않는다. 예전에는 시각마다 새로 만든 목록에 이 효과가 걸려 있어서
  // 칸이 넘어갈 때마다 전체 화면으로 되돌아갔다.
  const initDone = useRef(false);
  useEffect(() => {
    if (initDone.current) return;
    if (naverRef.current) { initDone.current = true; return; } // 네이버 모드로 먼저 복원됐으면 그 보기를 둔다
    const v = nationView();
    if (!v) return;
    initDone.current = true;
    viewRef.current = v;
    scheduleRef.current();
    syncRef.current(); // 처음 보이는 범위(전국)를 목록에 알린다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [regions]);

  // 사업장을 고르면(목록이든 지도든) 그 사업장으로 부드럽게 확대해 들어간다(이미 충분히 확대돼 있고 화면 안이면 가만히 둔다)
  useEffect(() => {
    if (!selectedSiteId) return;
    const idx = indexById.get(selectedSiteId);
    const { w, h } = sizeRef.current;
    if (idx === undefined || !w || !h) return;
    const view = viewRef.current;
    const [sx, sy] = toScreen(view, projected.xs[idx], projected.ys[idx]);
    const nv = naverRef.current;
    if (nv) { // 네이버 모드: 옛 규칙대로 확대 15까지 부드럽게 들어간다(이미 15 이상이고 화면 안이면 가만히 둔다)
      const z = nv.getZoom();
      if (needsNaverFocus(z, sx, sy, w, h)) { if (!reducedMotion()) hidePinsRef.current(); nv.moveTo(focusTarget(states[idx].site.lon, states[idx].site.lat, z), !reducedMotion()); }
      return;
    }
    if (!needsFocus(view, sx, sy, w, h)) return;
    flyTo(centeredOn(projected.xs[idx], projected.ys[idx], Math.max(view.scale, FOCUS_SCALE), w, h)); // 최대 상세까지 쭉 확대
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSiteId]);
  useEffect(() => { schedule(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [states, selectedSiteId, theme, contourOn, mapLevels, favoritesOnly, favorites]);
  // 표시 단계를 바꾸면 올려 둔 핀이 사라질 수 있으니 강조를 거둔다
  useEffect(() => { hoverRef.current = -1; setTip(null); setPicker(null); }, [mapLevels, selectedSiteId, favoritesOnly]);

  // 시각이 한두 칸 바뀌면서 새로 경고(주의 이상)가 되었거나 단계가 오른 굴뚝을 한 번 번쩍이게 한다.
  // React가 사업장 상태를 이전 값과 비교해 알려 주므로 따로 추적하지 않는다. 크게 뛰거나 너무 많으면 어지러워서 생략한다.
  const prevRanks = useRef<{ slot: number; ranks: RankMap } | null>(null);
  useEffect(() => {
    const prev = prevRanks.current;
    prevRanks.current = { slot, ranks: ranksOf(states) };
    if (!prev || reducedMotion()) return;
    const fresh = freshAlerts(prev.ranks, states, slot - prev.slot);
    if (fresh.length === 0) return;
    const start = performance.now();
    const get = (n: string) => (canvasRef.current ? cssVar(canvasRef.current, n) : "");
    for (const f of fresh) effects.current.set(f.site.id, { start, color: get(`--lv-${f.level}`) || "#e04b35" });
    scheduleRef.current();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [states, slot]);

  // 재생: 한 칸씩 앞으로. 끝에 닿는 순간 멈춘다. 시계도 이 간격(stepMs)에 맞춰 돈다
  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      const next = slotRef.current + 1;
      if (next > last) return setPlaying(false);
      slotRef.current = next;
      onSlot(next);
      if (next >= last) setPlaying(false);
    }, stepMs);
    return () => window.clearInterval(id);
  }, [playing, stepMs, last, onSlot]);


  // 휠: 지도 안에서만 확대하고 페이지 스크롤로 새지 않게 한다(수동 리스너여야 preventDefault가 먹는다)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const r = canvas.getBoundingClientRect();
      setPicker(null);
      cancelFlight();
      markMoving();
      viewRef.current = constrainRef.current(zoomAt(viewRef.current, e.clientX - r.left, e.clientY - r.top, e.deltaY < 0 ? 1.25 : 0.8, minScaleRef.current(), MAX_SCALE));
      scheduleRef.current();
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, []);

  // ── 마우스: 이동·올림·클릭 ─────────────────────────────────────
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const local = (e: React.MouseEvent) => {
    const r = canvasRef.current!.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top] as const;
  };
  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return; // 오른쪽 버튼은 끌기가 아니다(선택 해제에 쓴다)
    setPicker(null);
    cancelFlight();
    const [x, y] = local(e);
    drag.current = { x, y, moved: false };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const [x, y] = local(e);
    const d = drag.current;
    if (d) {
      const dx = x - d.x, dy = y - d.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true;
      if (d.moved) {
        const v = viewRef.current;
        markMoving();
        viewRef.current = constrain({ ...v, ox: v.ox + dx, oy: v.oy + dy });
        d.x = x; d.y = y;
        schedule();
        return;
      }
    }
    hoverAt(x, y);
  };
  /** 마우스를 올린 자리의 핀을 강조하고 말풍선을 띄운다(관제 지도는 캔버스 이벤트로, 네이버 모드는 지도 이벤트로 부른다) */
  const hoverAt = (x: number, y: number) => {
    const ci = movingRef.current ? -1 : pinHit(clustersRef.current, x, y);
    if (ci !== hoverRef.current) {
      hoverRef.current = ci;
      schedule(); // 올려 둔 동안은 draw가 스스로 다음 프레임을 이어 부른다(파형)
      if (ci < 0) setTip(null);
      else {
        const c = clustersRef.current[ci];
        const sts = c.members.map((m) => states[visibleRef.current[m]]);
        const top = sts.reduce((a, b) => (rankOf(b.level) > rankOf(a.level) ? b : a));
        const text = c.count === 1
          ? `${top.site.name}${top.ratio === null ? " · 측정 공백" : ` · ${top.ratio.toFixed(0)}%`}`
          : `${c.count}곳 · 최고 ${top.level ? LEVELS.find((l) => l.key === top.level)!.label : "공백"} · ${splittable(c) ? "눌러서 확대" : "눌러서 고르기"}`;
        setTip({ x: c.x, y: c.y - 30, text });
      }
    }
  };
  const onPointerUp = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    const d = drag.current;
    drag.current = null;
    if (d?.moved) { // 놓으면 바로 묶음·등고선을 새로 계산한다
      window.clearTimeout(settleTimer.current);
      movingRef.current = false;
      schedule();
      syncRef.current(); // 놓은 자리의 중앙을 보고 지역을 판단한다
      return;
    }
    const [x, y] = local(e);
    clickAt(x, y);
  };
  const clickAt = (x: number, y: number) => {
    const ci = pinHit(clustersRef.current, x, y);
    if (ci >= 0) clickCluster(clustersRef.current[ci]);
    // 빈 땅을 눌러도 아무 일도 일어나지 않는다. 지역은 눌러서 가는 것이 아니라 중앙을 보고 판단한다.
  };
  const leaveHover = () => { if (hoverRef.current !== -1) { hoverRef.current = -1; setTip(null); schedule(); } };
  /** 확대 한도: 관제 지도는 MAX_SCALE, 네이버는 확대 18(2^18) */
  const maxScale = () => (modeRef.current === "control" ? MAX_SCALE : 2 ** NAVER_ZOOM.max);
  /** 오른쪽 버튼: 선택 해제(메뉴는 띄우지 않는다) */
  const lastPin = useRef<{ id: string; t: number } | null>(null);
  const onContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    setPicker(null);
    clearSelection();
  };
  /** 이 묶음은 확대하면 갈라지는지(아니면 목록으로 고른다) */
  const splittable = (c: Cluster) => {
    const b = boundsOf(c.members.map((m) => { const i = visibleRef.current[m]; return [projected.xs[i], projected.ys[i]] as [number, number]; }));
    return !!b && canSeparate(b) && viewRef.current.scale < maxScale() * 0.98;
  };
  const clickCluster = (c: Cluster) => {
    const sts = c.members.map((m) => states[visibleRef.current[m]]);
    if (c.count === 1) { // 선택한 사업장을 다시 누르면 해제(더블클릭의 두 번째 클릭은 건너뛴다)
      const t = performance.now();
      const lp = lastPin.current;
      lastPin.current = { id: sts[0].site.id, t };
      if (lp && lp.id === sts[0].site.id && t - lp.t < 350) return;
      if (sts[0].site.id === selectedSiteId) clearSelection();
      else selectSite(sts[0].site.id, sts[0].worstStack);
      return;
    }
    // 묶음을 누르면 구성원 쪽으로 쭉 확대해 들어간다: 한 번에 최소 2.4배, 구성원이 다 보이면 그 범위까지.
    // 눌러 들어갈수록 묶음이 풀려 결국 사업장 하나가 된다.
    const b = boundsOf(c.members.map((m) => { const i = visibleRef.current[m]; return [projected.xs[i], projected.ys[i]] as [number, number]; }));
    if (!b) return;
    // 확대 한도까지 들어가도 갈라지지 않는 묶음(좌표가 사실상 같음)이거나 이미 한도면 목록으로 고르게 한다
    if (!canSeparate(b) || viewRef.current.scale >= maxScale() * 0.98) { openPicker(c, sts); return; }
    const { w, h } = sizeRef.current;
    flyTo(stepZoomView(b, viewRef.current, w, h), "floor"); // 네이버는 정수 확대라 내림(구성원이 잘리지 않게, 한 단계 이상은 늘 들어간다)
  };
  /** 안 갈라지는 묶음의 사업장 목록을 그 자리에 띄운다(단계 높은 순) */
  const openPicker = (c: Cluster, sts: SiteState[]) => {
    const { w, h } = sizeRef.current;
    const items = [...sts].sort((a, b) => rankOf(b.level) - rankOf(a.level) || (b.ratio ?? -1) - (a.ratio ?? -1));
    setPicker({ x: Math.min(Math.max(c.x + 12, 8), Math.max(8, w - 236)), y: Math.min(Math.max(c.y - 110, 8), Math.max(8, h - 236)), items });
    setTip(null);
  };

  // ── 네이버 지도 연결 ───────────────────────────────────────────
  /** 네이버 지도를 떠난다(지도를 없애고 마지막 보기를 관제 지도가 이어받는다) */
  const leaveNaver = () => {
    naverRef.current?.destroy();
    naverRef.current = null;
    hostRef.current?.replaceChildren();
    modeRef.current = "control";
    setMode("control");
    hoverRef.current = -1; setTip(null); setPicker(null);
    clusterView.current = null;
    window.clearTimeout(settleTimer.current);
    movingRef.current = false;
    scheduleRef.current();
    syncRef.current();
  };
  /** 지도 종류를 바꾼다. 네이버 SDK는 처음 고를 때 한 번만 읽고, 실패하면 안내하고 관제 지도를 그대로 쓴다 */
  const chooseMode = (next: MapMode) => {
    if (next === modeRef.current && !naverBusy) return;
    const token = ++modeToken.current;
    setPicker(null); setTip(null); hoverRef.current = -1;
    if (next === "control") { leaveNaver(); setNaverNote(""); setNaverBusy(false); writeMapMode("control"); return; }
    const live = naverRef.current;
    if (live) { live.setMapType(next); modeRef.current = next; setMode(next); setNaverNote(""); writeMapMode(next); return; }
    setNaverBusy(true);
    setNaverNote(NAVER_NOTES.loading);
    loadNaverSdk(naverKeyId()).then((N) => {
      const host = hostRef.current;
      if (token !== modeToken.current || !host) return; // 그 사이 다른 선택을 했거나 화면이 사라졌다
      const { w, h } = sizeRef.current;
      const ctl = createNaverMap(N, host, { w: w || 300, h: h || 300 }, {
        onFollow: () => nvh.current.onFollow(), onIdle: () => nvh.current.onIdle(),
        onHover: (x, y) => nvh.current.onHover(x, y), onLeave: () => nvh.current.onLeave(),
        onClick: (x, y) => nvh.current.onClick(x, y), onContextMenu: () => nvh.current.onContextMenu(),
      });
      ctl.setMapType(next);
      if (w && h) ctl.moveTo(targetOfView(viewRef.current, w, h, "floor"), false); // 보던 곳(전국 맞춤이면 한국 전체)에서 시작
      naverRef.current = ctl;
      modeRef.current = next;
      animRef.current = null;
      clusterView.current = null;
      movingRef.current = false;
      viewRef.current = ctl.getView();
      setMode(next); setNaverBusy(false); setNaverNote(""); writeMapMode(next);
      scheduleRef.current();
      syncRef.current();
    }).catch((e: unknown) => {
      if (token !== modeToken.current) return;
      setNaverBusy(false);
      setNaverNote(e instanceof Error && e.message ? e.message : NAVER_NOTES.noMap);
    });
  };
  /** 네이버 지도 이벤트가 부르는 함수들: 늘 최신 상태를 쓰도록 ref로 건다 */
  const nvh = useRef<NaverCallbacks>({ onFollow() {}, onIdle() {}, onHover() {}, onLeave() {}, onClick() {}, onContextMenu() {} });
  // 네이버는 확대 애니메이션 중에 이벤트를 드문드문 보낸다. 움직임이 시작되면 멈출 때까지 매 프레임 지도의 현재 보기를 읽어 핀을 붙여 둔다.
  const followLoop = useRef(0);
  const followStable = useRef(0);
  const startFollow = () => {
    followStable.current = 0;
    if (followLoop.current) return;
    let last = "";
    const step = () => {
      followLoop.current = 0;
      const nv = naverRef.current;
      if (!nv) return;
      const v = nv.getView();
      const sig = `${v.scale.toFixed(4)}|${v.ox.toFixed(1)}|${v.oy.toFixed(1)}`;
      if (sig !== last) { last = sig; followStable.current = 0; viewRef.current = v; markMoving(); scheduleRef.current(); }
      else followStable.current++;
      if (followStable.current < 30) followLoop.current = requestAnimationFrame(step); // 약 0.5초 변화가 없으면 쉰다(idle이 마무리한다)
    };
    followLoop.current = requestAnimationFrame(step);
  };
  const startFollowRef = useRef(startFollow);
  startFollowRef.current = startFollow;
  // 휠·더블클릭 확대 중에는 핀을 따라가지 않고 잠깐 숨긴다(이전 네이버 지도와 같음). 멈추면(idle) 다시 그린다.
  const zoomHide = useRef(false);
  const zoomHideTimer = useRef(0);
  const lastZoomInput = useRef(0);
  /** 확대·이동이 시작되면 핀을 지운다. 멈추면(idle) 그리고, idle이 안 와도 0.8초 뒤에는 다시 그린다 */
  const hidePins = (guardIdle = false) => {
    if (!naverRef.current) return;
    zoomHide.current = true;
    lastZoomInput.current = guardIdle ? performance.now() : 0; // 사람이 휠로 확대할 때만 확대 도중의 중간 idle을 무시한다
    scheduleRef.current();
    window.clearTimeout(zoomHideTimer.current);
    zoomHideTimer.current = window.setTimeout(() => {
      if (!zoomHide.current) return;
      zoomHide.current = false;
      const nv = naverRef.current;
      if (nv) viewRef.current = nv.getView();
      movingRef.current = false;
      scheduleRef.current();
      syncRef.current();
    }, 800);
  };
  const hidePinsRef = useRef(hidePins);
  hidePinsRef.current = hidePins;
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const drag = () => startFollowRef.current(); // 끄는 동안은 따라온다
    const zoom = () => hidePinsRef.current(true);
    host.addEventListener("wheel", zoom, { passive: true, capture: true });
    host.addEventListener("dblclick", zoom, { passive: true, capture: true });
    host.addEventListener("pointerdown", drag, { passive: true, capture: true });
    return () => {
      host.removeEventListener("wheel", zoom, true);
      host.removeEventListener("dblclick", zoom, true);
      host.removeEventListener("pointerdown", drag, true);
      cancelAnimationFrame(followLoop.current);
      followLoop.current = 0;
      window.clearTimeout(zoomHideTimer.current);
    };
  }, []);
  nvh.current = {
    onFollow: () => { const nv = naverRef.current; if (!nv) return; viewRef.current = nv.getView(); markMoving(); scheduleRef.current(); },
    onIdle: () => {
      const nv = naverRef.current;
      if (!nv) return;
      if (zoomHide.current && performance.now() - lastZoomInput.current < 250) {
        // 확대 도중에 오는 중간 idle은 무시한다. 입력이 멈춘 뒤 다시 그린다.
        window.clearTimeout(zoomHideTimer.current);
        zoomHideTimer.current = window.setTimeout(() => nvh.current.onIdle(), 300);
        return;
      }
      viewRef.current = nv.getView();
      zoomHide.current = false;
      window.clearTimeout(zoomHideTimer.current);
      window.clearTimeout(settleTimer.current);
      movingRef.current = false;
      scheduleRef.current();
      syncRef.current(); // 멈춘 범위를 알린다(경고 목록이 지도에 보이는 사업장만 보여 주는 데 쓴다)
    },
    onHover: hoverAt, onLeave: leaveHover, onClick: clickAt,
    onContextMenu: () => { setPicker(null); clearSelection(); },
  };
  const chooseRef = useRef(chooseMode);
  chooseRef.current = chooseMode;
  const leaveRef = useRef(leaveNaver);
  leaveRef.current = leaveNaver;

  // 저장해 둔 지도 종류를 처음에 복원한다(관제 지도가 기본)
  useEffect(() => {
    const saved = readMapMode();
    if (saved !== "control") chooseRef.current(saved);
  }, []);
  // 인증이 나중에 실패해도(도메인 미등록 등) 관제 지도로 돌아가고 이유를 알린다
  useEffect(() => onNaverAuthFailure(() => {
    modeToken.current++;
    if (naverRef.current) leaveRef.current();
    setNaverBusy(false);
    setNaverNote(NAVER_NOTES.auth);
  }), []);
  // 화면이 사라지면 네이버 지도와 이벤트 연결을 정리한다
  useEffect(() => () => { modeToken.current++; naverRef.current?.destroy(); naverRef.current = null; }, []);

  return (
    <div className={styles.panel}>
      <div className={styles.bar}>
        <strong className={styles.title}>지도</strong>
        <nav className={styles.crumbs} aria-label="지도 중앙 위치">
          <span className={styles.crumbHint}>지도 중앙</span>
          <span className={styles.crumbNow} aria-current="location">{mapPath.sido ?? "전국"}</span>
          {mapPath.sigungu && (<><span aria-hidden="true">›</span><span className={styles.crumbNow}>{mapPath.sigungu}</span></>)}
        </nav>
        {/* 상태 칩과 도구 버튼은 오른쪽(등고선 쪽)으로 모은다 */}
        <div className={styles.right}>
        {!naverOn && (
          <button type="button" className={styles.up} aria-pressed={contourOn} onClick={() => setContourOn((v) => !v)}>
            등고선 {contourOn ? "켬" : "끔"}
          </button>
        )}
        <MapKindSelect mode={mode} busy={naverBusy} onChange={chooseMode} />
        <div className={styles.levels} role="group" aria-label="지도에 표시할 상태">
          {SHOW_CHIPS.map((c) => (
            <button
              key={c.key}
              type="button"
              className={styles.level}
              aria-pressed={mapLevels.includes(c.key)}
              onClick={() => toggleMapLevel(c.key)}
              title={c.hint}
            >
              <LevelMark level={c.key} size={12} /> {c.label}
            </button>
          ))}
        </div>
        <div className={styles.levels} role="group" aria-label="지도 사업장 범위">
          <button
            type="button"
            className={styles.level}
            aria-pressed={favoritesOnly}
            onClick={() => setFavoritesOnly(!favoritesOnly)}
            aria-label="즐겨찾기만 보기"
            title="즐겨찾기한 사업장만 지도와 목록에 표시합니다"
          >
            ★
          </button>
        </div>
        <div className={styles.tools}>
          <button type="button" className={styles.up} onClick={() => { const v = nationView(); if (v) flyTo(v, "floor"); }}>전국 보기</button>
        </div>
        </div>
      </div>
      <div ref={wrapRef} className={styles.canvasWrap}>
        <div ref={hostRef} className={naverOn ? naverStyles.host : `${naverStyles.host} ${naverStyles.hostHidden}`} />
        <canvas
          ref={canvasRef}
          className={naverOn ? `${styles.canvas} ${naverStyles.overlay}` : styles.canvas}
          role="img"
          aria-label={`굴뚝 ${visibleIdx.length}곳을 보여 주는 지도. 같은 내용을 오른쪽 목록에서 키보드로 고를 수 있습니다.`}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onContextMenu={onContextMenu}
          onPointerLeave={() => { drag.current = null; if (hoverRef.current !== -1) { hoverRef.current = -1; setTip(null); schedule(); } }}
        />
        {naverNote && <div className={naverStyles.note} role="status">{naverNote}</div>}
        {tip && <div className={styles.tip} style={{ left: tip.x, top: tip.y }}>{tip.text}</div>}
        {picker && (
          <div
            className={styles.picker}
            style={{ left: picker.x, top: picker.y }}
            role="menu"
            aria-label={`같은 자리의 사업장 ${picker.items.length}곳 중 고르기`}
            onKeyDown={(e) => { if (e.key === "Escape") setPicker(null); }}
          >
            <div className={styles.pickerHead}>같은 자리 {picker.items.length}곳 · 하나를 고르세요</div>
            <div className={styles.pickerList}>
              {picker.items.map((it) => (
                <button
                  key={it.site.id}
                  type="button"
                  role="menuitem"
                  className={styles.pickerItem}
                  onClick={() => { selectSite(it.site.id, it.worstStack); setPicker(null); }}
                >
                  <LevelMark level={it.level ?? "gap"} size={12} />
                  <span className={styles.pickerName}>{it.site.name}</span>
                  <span className={styles.pickerRatio}>{it.ratio === null ? "—" : `${it.ratio.toFixed(0)}%`}</span>
                </button>
              ))}
            </div>
          </div>
        )}
        <MapClock times={times} slot={slot} playing={playing} stepMs={stepMs} />
        <Compass />
        <p className={styles.guide}>드래그 이동 · 휠 확대/축소 · 묶음·굴뚝을 누르면 그쪽으로 확대 · 오른쪽 클릭은 선택 해제</p>
      </div>
      <div className={styles.clock}>
        <button
          type="button"
          className={styles.ctl}
          onClick={() => {
            if (playing) return setPlaying(false);
            if (slot >= last) onSlot(0); // 끝에서 누르면 처음부터
            setPlaying(true);
          }}
          aria-label={playing ? "재생 멈춤" : "하루 흐름 재생"}
          title={playing ? "멈춤" : "하루 흐름 재생"}
        >
          {playing ? "⏸" : "▶"}
        </button>
        <button
          type="button"
          className={styles.ctl}
          onClick={() => setSpeedIdx((i) => (i + 1) % SPEEDS.length)}
          aria-label={`재생 속도 ${SPEEDS[speedIdx].label}, 누르면 바뀜`}
          title="재생 속도"
        >
          {SPEEDS[speedIdx].label}
        </button>
        <input
          type="range"
          min={0}
          max={last}
          value={slot}
          aria-label="지도 시각"
          aria-valuetext={times[slot] !== undefined ? formatSlot(times[slot]) : undefined}
          onChange={(e) => { setPlaying(false); onSlot(Number(e.target.value)); }}
        />
        <span className={styles.slotLabel}>{times[slot] !== undefined ? formatSlot(times[slot]) : "—"}</span>
        <button type="button" className={styles.latest} onClick={() => { setPlaying(false); onSlot(last); }} disabled={slot >= last}>최신</button>
      </div>
    </div>
  );
}
