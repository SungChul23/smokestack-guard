// 라이트·다크 테마. <html data-theme>에 걸고 localStorage(tms-theme)에 저장한다.
// 저장 키는 A의 첫 화면과 같다(화면 전체에서 같이 쓰려고 이름을 고정했다). 저장이 막혀도 이번 화면에서는 바뀐다.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Theme = "dark" | "light";
export const THEME_KEY = "tms-theme";

export function readTheme(): Theme {
  try {
    return window.localStorage.getItem(THEME_KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

function saveTheme(theme: Theme) {
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    // 저장이 막혀도 이번 화면에서는 바뀐다
  }
}

interface ThemeValue {
  theme: Theme;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(readTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  // 다른 탭에서 바꾸면 따라간다
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === THEME_KEY) setTheme(readTheme());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const toggle = useCallback(() => {
    setTheme((current) => {
      const next: Theme = current === "dark" ? "light" : "dark";
      saveTheme(next);
      return next;
    });
  }, []);

  const value = useMemo(() => ({ theme, toggle }), [theme, toggle]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeValue {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme은 ThemeProvider 안에서만 쓴다");
  return value;
}
