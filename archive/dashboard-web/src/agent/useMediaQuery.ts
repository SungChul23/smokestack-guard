// 화면 조건(폭·모션 줄이기 설정)을 따라가는 작은 훅. matchMedia가 없는 환경(시험 등)에서는 false다.
import { useEffect, useState } from "react";

export const WIDE_QUERY = "(min-width: 641px)"; // 창 이동·크기 조절이 켜지는 폭
export const NARROW_QUERY = "(max-width: 540px)"; // 이 폭 이하에서는 마스코트 대신 고정 버튼
export const REDUCED_QUERY = "(prefers-reduced-motion: reduce)";

const read = (query: string) => typeof window !== "undefined" && !!window.matchMedia?.(query).matches;

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => read(query));
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const m = window.matchMedia(query);
    const on = () => setMatches(m.matches);
    on();
    m.addEventListener?.("change", on);
    return () => m.removeEventListener?.("change", on);
  }, [query]);
  return matches;
}
