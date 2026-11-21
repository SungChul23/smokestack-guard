// 네이버 지도 ↔ 우리 지도의 좌표 변환(순수 함수). 둘 다 웹 메르카토르(세계 폭 256)라 변환이 단순하다.
// 네이버 확대 수준 z에서 세계 1칸은 2^z px이므로 우리 View의 축척(scale)은 2^z다(옛 지도 어댑터 getView와 같은 규칙).
// 그래도 보이는 범위는 줌 수식이 아니라 **네이버 자체 투영에서 보정해** 만든다(viewFromProjection):
// 타일 기준이 다르거나 확대 도중의 소수 줌이어도 핀이 지도 위에서 어긋나지 않게 하려는 것이다.
import { centerOf, project, type View } from "../geometry";

/** 옛 지도 어댑터와 같은 한국 범위·확대 한도 */
/** 확대 한도: 7보다 더 줄이면 한국이 너무 작아지고 주변 바다·외국이 대부분이라 7(처음 전국 맞춤 수준)에서 멈춘다(옛 지도는 6) */
export const NAVER_ZOOM = { min: 7, max: 18, focus: 15 } as const;
export const NAVER_BOUNDS = { sw: { lat: 31.5, lng: 123 }, ne: { lat: 40, lng: 133 } } as const;
export const NAVER_INITIAL = { lat: 36, lng: 127.7, zoom: 7 } as const;

export interface NaverTarget { lng: number; lat: number; zoom: number }

/** 세계 좌표(폭 256) → [경도, 위도]. geometry.project의 거꾸로 */
export function unproject(x: number, y: number): [number, number] {
  const lng = (x / 256) * 360 - 180;
  const lat = (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / 256))) * 180) / Math.PI;
  return [lng, lat];
}

export const clampZoom = (z: number) => Math.min(NAVER_ZOOM.max, Math.max(NAVER_ZOOM.min, z));

/** 우리 축척 → 네이버 확대 수준(정수). 전국 맞춤은 floor(다 보이게), 묶음 확대는 ceil(확실히 더 들어가게) */
export function zoomForScale(scale: number, rounding: "round" | "ceil" | "floor" = "round"): number {
  const z = Math.log2(Math.max(scale, 1e-9));
  return clampZoom(rounding === "ceil" ? Math.ceil(z - 1e-9) : rounding === "floor" ? Math.floor(z + 1e-9) : Math.round(z));
}

/** 우리 보기(View) → 네이버가 이동할 곳(중심 + 확대 수준) */
export function targetOfView(view: View, w: number, h: number, rounding: "round" | "ceil" | "floor" = "round"): NaverTarget {
  const [cx, cy] = centerOf(view, w, h);
  const [lng, lat] = unproject(cx, cy);
  return { lng, lat, zoom: zoomForScale(view.scale, rounding) };
}

/**
 * 네이버 투영으로 우리 View를 만든다. 기준 두 점의 화면 위치를 재서 축척·이동량을 구한다.
 * 화면 좌표는 지도 영역 왼쪽 위가 (0,0)이고 우리 캔버스와 같은 공간이다.
 */
export function viewFromProjection(toScreen: (lng: number, lat: number) => { x: number; y: number }): View {
  const A: [number, number] = [126, 34], B: [number, number] = [130, 38];
  const a = project(A[0], A[1]), b = project(B[0], B[1]);
  const sa = toScreen(A[0], A[1]), sb = toScreen(B[0], B[1]);
  const scale = ((sb.x - sa.x) / (b[0] - a[0]) + (sb.y - sa.y) / (b[1] - a[1])) / 2;
  return { scale, ox: sa.x - a[0] * scale, oy: sa.y - a[1] * scale };
}

/** 사업장을 고르면 이동할 곳: 그 위치, 확대는 지금 수준과 옛 규칙(15) 중 큰 쪽 */
export function focusTarget(lng: number, lat: number, currentZoom: number): NaverTarget {
  return { lng, lat, zoom: clampZoom(Math.max(Math.round(currentZoom), NAVER_ZOOM.focus)) };
}

/** 이미 충분히 확대(15 이상)돼 있고 화면 여백 안이면 움직일 필요가 없다(관제 지도의 needsFocus와 같은 규칙) */
export function needsNaverFocus(zoom: number, sx: number, sy: number, w: number, h: number): boolean {
  if (zoom < NAVER_ZOOM.focus) return true;
  return sx < 50 || sx > w - 50 || sy < 60 || sy > h - 70;
}
