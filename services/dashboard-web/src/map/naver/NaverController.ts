// 네이버 지도 감싸기. 지도 생성·이벤트 연결·이동·정리만 맡고, 핀 그리기·묶기·선택은 MapPanel의 기존 코드가 한다.
// 이동·확대는 네이버가 맡는다. 우리는 네이버가 알려 주는 이벤트로 (1) 움직이는 중, (2) 멈춤, (3) 마우스 위치/클릭을 전달받는다.
import type { View } from "../geometry";
import type { NaverMapEvent, NaverMapInstance, NaverMaps } from "./types";
import { NAVER_BOUNDS, NAVER_INITIAL, NAVER_ZOOM, clampZoom, viewFromProjection, type NaverTarget } from "./viewMath";

export interface NaverCallbacks {
  /** 끌거나 확대하는 중(연속으로 불린다) */
  onFollow(): void;
  /** 멈췄다(idle) */
  onIdle(): void;
  /** 마우스가 지도 위에서 움직였다(지도 영역 기준 화면 좌표) */
  onHover(x: number, y: number): void;
  onLeave(): void;
  onClick(x: number, y: number): void;
  /** 오른쪽 클릭(브라우저 메뉴는 막는다) */
  onContextMenu(): void;
}

export interface NaverController {
  setMapType(type: "normal" | "satellite"): void;
  /** 지금 지도가 보여 주는 범위를 우리 View로 */
  getView(): View;
  getZoom(): number;
  /** 지정한 곳으로 이동·확대한다(animate이면 부드럽게) */
  moveTo(target: NaverTarget, animate: boolean): void;
  setSize(w: number, h: number): void;
  destroy(): void;
}

const MOVE_EVENTS = ["dragstart", "drag", "center_changed", "zoom_changed", "bounds_changed"] as const;

export function createNaverMap(
  N: NaverMaps,
  host: HTMLElement,
  size: { w: number; h: number },
  cb: NaverCallbacks,
): NaverController {
  const map: NaverMapInstance = new N.Map(host, {
    size: new N.Size(size.w, size.h),
    center: new N.LatLng(NAVER_INITIAL.lat, NAVER_INITIAL.lng),
    zoom: NAVER_INITIAL.zoom,
    minZoom: NAVER_ZOOM.min,
    maxZoom: NAVER_ZOOM.max,
    maxBounds: new N.LatLngBounds(
      new N.LatLng(NAVER_BOUNDS.sw.lat, NAVER_BOUNDS.sw.lng),
      new N.LatLng(NAVER_BOUNDS.ne.lat, NAVER_BOUNDS.ne.lng),
    ),
    zoomControl: false,
    mapTypeControl: false,
    scaleControl: true,
    mapDataControl: true,
    logoControl: true, // 네이버 로고·저작권 표기는 끄지 않는다
  });

  /** 이벤트의 화면 좌표(지도 영역 기준). 브라우저 이벤트가 있으면 그것으로, 없으면 SDK가 준 point로 */
  const pointOf = (e?: NaverMapEvent): { x: number; y: number } | null => {
    const pe = e?.pointerEvent;
    if (pe && typeof pe.clientX === "number") {
      const r = host.getBoundingClientRect();
      return { x: pe.clientX - r.left, y: pe.clientY - r.top };
    }
    const p = e?.point ?? e?.offset;
    return p ? { x: p.x, y: p.y } : null;
  };

  const listeners: unknown[] = [];
  const on = (name: string, fn: (e: NaverMapEvent) => void) => { listeners.push(N.Event.addListener(map, name, fn)); };
  for (const name of MOVE_EVENTS) on(name, () => cb.onFollow());
  on("idle", () => cb.onIdle());
  on("mousemove", (e) => { const p = pointOf(e); if (p) cb.onHover(p.x, p.y); });
  on("click", (e) => { const p = pointOf(e); if (p) cb.onClick(p.x, p.y); });

  const onContext = (e: Event) => { e.preventDefault(); cb.onContextMenu(); };
  const onLeave = () => cb.onLeave();
  host.addEventListener("contextmenu", onContext);
  host.addEventListener("mouseleave", onLeave);

  let destroyed = false;
  return {
    setMapType(type) {
      map.setMapTypeId(type === "satellite" ? N.MapTypeId.SATELLITE : N.MapTypeId.NORMAL);
    },
    getView() {
      // fromCoordToOffset은 화면이 아니라 '지도 판(pane)' 기준 위치를 준다. 끌면 판 자체가 움직여 같은 좌표는 늘 같은 값이 나오므로,
      // 지금 중심이 화면 한가운데에 오도록 (중심의 판 위치 → 화면 중앙) 차이를 더해 화면 좌표로 바꾼다.
      const proj = map.getProjection();
      const size = map.getSize();
      const c = proj.fromCoordToOffset(map.getCenter());
      const dx = size.width / 2 - c.x, dy = size.height / 2 - c.y;
      return viewFromProjection((lng, lat) => {
        const o = proj.fromCoordToOffset(new N.LatLng(lat, lng));
        return { x: o.x + dx, y: o.y + dy };
      });
    },
    getZoom: () => map.getZoom(),
    moveTo(target, animate) {
      const coord = new N.LatLng(target.lat, target.lng);
      const zoom = clampZoom(target.zoom);
      if (animate && map.morph) { map.morph(coord, zoom, { duration: 500 }); return; }
      map.setCenter(coord);
      map.setZoom(zoom, false);
    },
    setSize(w, h) {
      const s = map.getSize();
      if (Math.abs(s.width - w) > 0.5 || Math.abs(s.height - h) > 0.5) map.setSize(new N.Size(w, h));
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      for (const l of listeners) N.Event.removeListener(l);
      N.Event.clearInstanceListeners(map);
      host.removeEventListener("contextmenu", onContext);
      host.removeEventListener("mouseleave", onLeave);
      map.destroy?.();
    },
  };
}
