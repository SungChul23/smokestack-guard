// 에이전트 창·마스코트의 개인 설정 저장(이 브라우저에만). 저장소를 못 써도(막힘·시크릿 창) 동작은 계속된다.
// 키 이름은 옛 웹과 같아서 이미 저장해 둔 값이 그대로 이어진다.
import { normalize, type Rect, type Viewport } from "./frameGeometry";

export const KEYS = {
  rect: "tms-agent-frame-rect", // 창 위치·크기
  mode: "tms-agent-frame-mode", // "side" | "full"
  mascot: "tms-mascot", // "on"이면 마스코트가 화면을 돌아다닌다(기본 꺼짐)
} as const;

export type FrameMode = "side" | "full";

function get(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}
function set(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* 저장소를 못 써도 동작한다 */
  }
}

/** 저장된 창 위치·크기. 형식이 틀리면 null(기본 위치), 뷰포트가 줄었으면 안으로 끌어 넣는다 */
export function readRect(vp: Viewport): Rect | null {
  const raw = get(KEYS.rect);
  if (!raw) return null;
  try {
    return normalize(JSON.parse(raw), vp);
  } catch {
    return null;
  }
}
export function writeRect(rect: Rect | null): void {
  set(KEYS.rect, rect ? JSON.stringify(rect) : null);
}

export function readMode(): FrameMode {
  return get(KEYS.mode) === "full" ? "full" : "side";
}
export function writeMode(mode: FrameMode): void {
  set(KEYS.mode, mode);
}

/** ?mascot=off가 가장 우선, ?mascot=on이면 켬, 아니면 저장된 설정(기본 꺼짐) */
export function mascotWanted(search: string = typeof window === "undefined" ? "" : window.location.search): boolean {
  let param: string | null = null;
  try {
    param = new URLSearchParams(search).get("mascot");
  } catch {
    param = null;
  }
  if (param === "off") return false;
  if (param === "on") return true;
  return get(KEYS.mascot) === "on";
}
export function writeMascot(on: boolean): void {
  set(KEYS.mascot, on ? "on" : null);
}
