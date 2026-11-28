import fs from "node:fs";
import { describe, expect, it } from "vitest";

const css = fs.readFileSync("src/theme/tokens.css", "utf8"); // 시험은 프로젝트 폴더에서 실행된다
const block = (sel: string) => css.slice(css.indexOf(sel), css.indexOf("}", css.indexOf(sel)));

describe("테마 토큰: 지도·그래프가 라이트 모드도 지원한다", () => {
  const dark = block(":root {"), light = block(':root[data-theme="light"]');
  it("무대(지도·그래프 바탕)와 지도 색은 두 모드가 각각 정의돼 있다", () => {
    for (const v of ["--stage-bg", "--stage-grid", "--map-land", "--map-line", "--map-ink", "--map-select", "--gap-fill-a", "--gap-fill-b"]) {
      expect(dark, `다크 ${v}`).toContain(`${v}:`);
      expect(light, `라이트 ${v}`).toContain(`${v}:`);
    }
  });
  it("라이트의 무대는 밝고(다크와 다름) A의 시작 화면이 쓰는 --chart-bg 값은 건드리지 않는다", () => {
    const get = (b: string, v: string) => b.match(new RegExp(v + ":\\s*(#[0-9a-fA-F]{6})"))![1].toLowerCase();
    const lum = (hex: string) => parseInt(hex.slice(1, 3), 16) * 0.299 + parseInt(hex.slice(3, 5), 16) * 0.587 + parseInt(hex.slice(5, 7), 16) * 0.114;
    expect(lum(get(light, "--stage-bg"))).toBeGreaterThan(180);
    expect(lum(get(dark, "--stage-bg"))).toBeLessThan(40);
    expect(get(light, "--chart-bg")).toBe("#0f1a17");
  });
});
