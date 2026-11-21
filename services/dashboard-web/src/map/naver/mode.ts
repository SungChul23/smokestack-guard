// 지도 종류 선택과 이 브라우저에만 저장하는 값. 저장소를 못 써도 동작한다(저장 실패는 무시).
export type MapMode = "control" | "normal" | "satellite";
export const MODE_KEY = "tms-map-mode";
export const MAP_MODES: ReadonlyArray<{ key: MapMode; label: string; aria: string; title: string }> = [
  { key: "control", label: "관제", aria: "관제 지도", title: "관제 지도(기본, 우리 지도)" },
  { key: "normal", label: "일반", aria: "네이버 일반", title: "네이버 일반 지도" },
  { key: "satellite", label: "위성", aria: "네이버 위성", title: "네이버 위성 지도" },
];

export function readMapMode(): MapMode {
  try {
    const v = window.localStorage.getItem(MODE_KEY);
    return v === "normal" || v === "satellite" ? v : "control";
  } catch {
    return "control";
  }
}

export function writeMapMode(mode: MapMode): void {
  try {
    if (mode === "control") window.localStorage.removeItem(MODE_KEY);
    else window.localStorage.setItem(MODE_KEY, mode);
  } catch {
    /* 저장소를 못 써도 동작한다 */
  }
}
