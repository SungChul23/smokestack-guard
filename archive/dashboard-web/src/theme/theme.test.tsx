import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { readTheme, THEME_KEY, ThemeProvider, useTheme } from "./theme";

function Probe() {
  const { theme, toggle } = useTheme();
  return (
    <button onClick={toggle} aria-label="테마">
      {theme}
    </button>
  );
}

describe("테마", () => {
  it("저장된 값이 없으면 다크가 기본이다", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByRole("button")).toHaveTextContent("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("저장된 라이트를 읽는다", () => {
    window.localStorage.setItem(THEME_KEY, "light");
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByRole("button")).toHaveTextContent("light");
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("엉뚱한 저장값은 다크로 읽는다", () => {
    window.localStorage.setItem(THEME_KEY, "purple");
    expect(readTheme()).toBe("dark");
  });

  it("전환하면 <html>과 저장소가 같이 바뀐다", async () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    await userEvent.click(screen.getByRole("button"));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem(THEME_KEY)).toBe("light");
    await userEvent.click(screen.getByRole("button"));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem(THEME_KEY)).toBe("dark");
  });

  it("저장소를 못 써도 이번 화면에서는 바뀐다", async () => {
    const getItem = vi.spyOn(window.localStorage, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const setItem = vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByRole("button")).toHaveTextContent("dark");
    await userEvent.click(screen.getByRole("button"));
    expect(document.documentElement.dataset.theme).toBe("light");
    getItem.mockRestore();
    setItem.mockRestore();
  });

  it("다른 탭에서 바꾸면 따라간다", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    act(() => {
      window.localStorage.setItem(THEME_KEY, "light");
      window.dispatchEvent(new StorageEvent("storage", { key: THEME_KEY, newValue: "light" }));
    });
    expect(screen.getByRole("button")).toHaveTextContent("light");
  });

  it("공급자 밖에서 쓰면 알려 준다", () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Probe />)).toThrow("ThemeProvider");
    error.mockRestore();
  });
});
