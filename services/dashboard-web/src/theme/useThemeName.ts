// 지금 화면의 테마 이름("dark" | "light")을 <html data-theme>에서 읽는다. ThemeProvider 밖(시험·미리보기)에서도 동작하고,
// 테마가 바뀌면 다시 그려지게 속성 변화를 지켜본다.
import { useSyncExternalStore } from "react";

export type ThemeName = "dark" | "light";

export function currentTheme(): ThemeName {
  if (typeof document === "undefined") return "dark";
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
}

function subscribe(onChange: () => void) {
  if (typeof document === "undefined" || typeof MutationObserver === "undefined") return () => {};
  const ob = new MutationObserver(onChange);
  ob.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => ob.disconnect();
}

export function useThemeName(): ThemeName {
  return useSyncExternalStore(subscribe, currentTheme, () => "dark");
}
