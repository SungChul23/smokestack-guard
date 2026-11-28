// 에이전트 창의 위치·크기 계산(순수 로직). DOM·저장소를 쓰지 않는다.
// 옛 웹의 agent-frame-geometry.js를 옮기고, 옛 웹에는 없던 상하 크기 조절과 모서리 조절을 더했다(결정 2026-11-20, D: 자유 이동·자유 크기).
// 창은 뷰포트 안에 머물고, 크기는 최소~최대 안에서만 바뀐다.

export const MIN_W = 320; // 창 최소 폭(px)
export const MIN_H = 240; // 창 최소 높이(px)
export const MARGIN = 16; // 기본 가장자리 여백(px). 기본 위치·최대 폭 계산에 쓴다
export const DEFAULT_W = 430; // 기본(사이드) 폭

export interface Rect { x: number; y: number; w: number; h: number }
export interface Viewport { w: number; h: number }
/** 크기 조절 손잡이: 위(n)·아래(s)·오른쪽(e)·왼쪽(w)과 네 모서리 */
export type Edge = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";
export const EDGES: readonly Edge[] = ["n", "s", "e", "w", "ne", "nw", "se", "sw"];

const clamp = (v: number, lo: number, hi: number) => (v < lo ? lo : v > hi ? hi : v);
const num = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

export function maxWidth(vp: Viewport): number {
  return Math.max(MIN_W, vp.w - 2 * MARGIN);
}
export function maxHeight(vp: Viewport): number {
  return Math.max(MIN_H, vp.h);
}

/** 이전과 같은 기본 위치: 오른쪽 위 16px 여백, 폭 430px(좁으면 뷰포트-32px), 높이는 위아래 16px 여백 */
export function defaultRect(vp: Viewport): Rect {
  const w = Math.min(DEFAULT_W, maxWidth(vp));
  return { x: vp.w - MARGIN - w, y: MARGIN, w, h: Math.max(MIN_H, vp.h - 2 * MARGIN) };
}

/** 어떤 값이 와도 뷰포트 안의 올바른 사각형으로 만든다 */
export function clampRect(r: Partial<Record<keyof Rect, unknown>>, vp: Viewport): Rect {
  const w = clamp(num(r.w) ? r.w : DEFAULT_W, MIN_W, maxWidth(vp));
  const h = clamp(num(r.h) ? r.h : vp.h - 2 * MARGIN, MIN_H, maxHeight(vp));
  const x = clamp(num(r.x) ? r.x : vp.w - MARGIN - w, 0, Math.max(0, vp.w - w));
  const y = clamp(num(r.y) ? r.y : MARGIN, 0, Math.max(0, vp.h - h));
  return { x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) };
}

/** 저장된 값 검사: 형식이 틀리면 null(기본 위치로 되돌린다) */
export function normalize(saved: unknown, vp: Viewport): Rect | null {
  if (!saved || typeof saved !== "object") return null;
  const s = saved as Record<string, unknown>;
  if (!num(s.x) || !num(s.y) || !num(s.w) || !num(s.h)) return null;
  return clampRect(s, vp);
}

/** 손잡이로 끌어 옮긴다(시작 사각형 + 이동량) */
export function moveRect(start: Rect, dx: number, dy: number, vp: Viewport): Rect {
  return clampRect({ x: start.x + dx, y: start.y + dy, w: start.w, h: start.h }, vp);
}

/**
 * 가장자리·모서리를 끌어 크기를 바꾼다(dx, dy는 포인터가 시작점에서 움직인 양).
 * 끄는 쪽의 반대 가장자리는 그대로 둔다. 최소 크기 아래로, 뷰포트 밖으로 나가지 않는다.
 */
export function resizeRect(start: Rect, edge: Edge, dx: number, dy: number, vp: Viewport): Rect {
  let { x, y, w, h } = start;
  const right = start.x + start.w;
  const bottom = start.y + start.h;
  if (edge.includes("w")) {
    w = clamp(start.w - dx, MIN_W, Math.min(maxWidth(vp), right)); // 왼쪽 끝(0)을 넘지 않게
    x = right - w;
  } else if (edge.includes("e")) {
    w = clamp(start.w + dx, MIN_W, Math.min(maxWidth(vp), vp.w - start.x)); // 오른쪽 끝(뷰포트)을 넘지 않게
  }
  if (edge.includes("n")) {
    h = clamp(start.h - dy, MIN_H, Math.min(maxHeight(vp), bottom)); // 위쪽 끝(0)을 넘지 않게
    y = bottom - h;
  } else if (edge.includes("s")) {
    h = clamp(start.h + dy, MIN_H, Math.min(maxHeight(vp), vp.h - start.y)); // 아래쪽 끝(뷰포트)을 넘지 않게
  }
  return clampRect({ x, y, w, h }, vp);
}

/** 키보드로 조금씩 옮긴다(방향키) */
export function nudge(rect: Rect, key: string, step: number, vp: Viewport): Rect {
  const d: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
  const m = d[key];
  return m ? moveRect(rect, m[0], m[1], vp) : rect;
}

/** 크기 조절 손잡이에서 방향키를 누르면: 그 손잡이가 담당하는 방향의 키만 크기를 바꾼다(나머지는 무시) */
export function resizeByKey(rect: Rect, edge: Edge, key: string, step: number, vp: Viewport): Rect {
  const horizontal = key === "ArrowLeft" || key === "ArrowRight";
  const vertical = key === "ArrowUp" || key === "ArrowDown";
  const handlesH = edge.includes("e") || edge.includes("w");
  const handlesV = edge.includes("n") || edge.includes("s");
  if (!((horizontal && handlesH) || (vertical && handlesV))) return rect;
  const dx = key === "ArrowLeft" ? -step : key === "ArrowRight" ? step : 0;
  const dy = key === "ArrowUp" ? -step : key === "ArrowDown" ? step : 0;
  return resizeRect(rect, edge, dx, dy, vp);
}

/**
 * 손잡이를 두 번 누르면 그 방향의 크기만 기본값으로 되돌린다. 반대쪽 가장자리는 그대로 두고,
 * 기본 크기가 그 방향에 남은 공간보다 크면 남은 공간까지만 키운다(창이 밀려 올라가거나 밀려 나가지 않게).
 */
export function resetEdge(rect: Rect, edge: Edge, vp: Viewport): Rect {
  const d = defaultRect(vp);
  let { x, y, w, h } = rect;
  const right = x + w, bottom = y + h;
  if (edge.includes("e")) w = Math.min(d.w, vp.w - x);
  if (edge.includes("w")) { w = Math.min(d.w, right); x = right - w; }
  if (edge.includes("s")) h = Math.min(d.h, vp.h - y);
  if (edge.includes("n")) { h = Math.min(d.h, bottom); y = bottom - h; }
  return clampRect({ x, y, w, h }, vp);
}

/** 손잡이 이름(화면 읽기용) */
export const EDGE_LABEL: Record<Edge, string> = {
  n: "위쪽 가장자리", s: "아래쪽 가장자리", e: "오른쪽 가장자리", w: "왼쪽 가장자리",
  ne: "오른쪽 위 모서리", nw: "왼쪽 위 모서리", se: "오른쪽 아래 모서리", sw: "왼쪽 아래 모서리",
};
