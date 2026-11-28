import { beforeEach, describe, expect, it } from "vitest";
import { changedCount, CHART_STYLE_KEY, COLOR_KEYS, DEFAULT_CHART_STYLE, DEFAULT_CHART_STYLE_DARK, defaultsFor, getStyle, parseStyles, RANGES, sanitizeChartStyle, useChartStyle } from "./chartStyle";

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme"); // 다크가 기본
  useChartStyle.setState({ styles: { dark: defaultsFor("dark"), light: defaultsFor("light") } });
});

describe("그래프 스타일 값 검사", () => {
  it("라이트 기본값은 D가 라이트에서 고른 값이다", () => {
    expect(DEFAULT_CHART_STYLE).toMatchObject({
      lineWidth: 1, smooth: true, lineGlow: 2, areaOpacity: 0.4, gapLineWidth: 1.5, gapLineOpacity: 0.5, gapFillOpacity: 0.1,
      gridOn: false, gridOpacity: 0.75, levelLineOpacity: 0.25, zoneOpacity: 0.07, innerRadius: 10, innerOpacity: 0.35,
      dotR: 4, dotGlow: 2, zoneLabelSize: 16, zoneLabelGlow: 0, levelLabelSize: 23, levelLabelGlow: 1, axisSize: 19, axisGlow: 1,
      labelsActiveOnly: true, pulseOn: true, pulseScale: 1.38, pulseSpeed: 1.55, pulseGlow: 2, pulseFast: true,
      gapLineColor: "#84b3a6", zoneColor: "#ff0a0a", zoneLabelColor: "#ababab", textColor: "#599765", crosshairColor: "#000000", dotStrokeColor: "#dbf6ff",
    });
    expect(DEFAULT_CHART_STYLE.noxColor).toBeNull(); // 물질 색은 테마 기본색
  });
  it("다크 기본값은 D가 다크에서 고른 값이다(빛이 더 강하고, 글자는 흰색, 초과 영역은 테마색)", () => {
    expect(DEFAULT_CHART_STYLE_DARK).toMatchObject({
      zoneLabelGlow: 2, levelLabelGlow: 2, axisGlow: 2, pulseGlow: 6, levelLabelSize: 23, axisSize: 19, labelsActiveOnly: true, pulseScale: 1.38, pulseSpeed: 1.55,
      zoneColor: null, zoneLabelColor: "#ffffff", textColor: "#ffffff", crosshairColor: "#ffffff", gapLineColor: "#84b3a6", dotStrokeColor: "#dbf6ff",
    });
    expect(defaultsFor("dark")).toEqual(DEFAULT_CHART_STYLE_DARK);
    expect(defaultsFor("light")).toEqual(DEFAULT_CHART_STYLE);
  });
  it("기본값은 모든 항목이 검사를 그대로 통과한다(범위 안)", () => {
    expect(sanitizeChartStyle(DEFAULT_CHART_STYLE)).toEqual(DEFAULT_CHART_STYLE);
  });
  it("빈 값·이상한 값은 기본값이 된다", () => {
    for (const bad of [null, undefined, 3, "x", [], {}]) expect(sanitizeChartStyle(bad)).toEqual(DEFAULT_CHART_STYLE);
  });
  it("숫자는 범위 안으로 맞추고, 숫자가 아니거나 무한이면 기본값을 쓴다", () => {
    const s = sanitizeChartStyle({ lineWidth: 99, areaOpacity: -5, dotR: 6.5, lineGlow: Number.NaN, gridOpacity: "0.5", gapLineWidth: Infinity });
    expect(s.lineWidth).toBe(RANGES.lineWidth[1]);
    expect(s.areaOpacity).toBe(RANGES.areaOpacity[0]);
    expect(s.dotR).toBe(6.5);
    expect(s.lineGlow).toBe(DEFAULT_CHART_STYLE.lineGlow);
    expect(s.gridOpacity).toBe(DEFAULT_CHART_STYLE.gridOpacity);
    expect(s.gapLineWidth).toBe(DEFAULT_CHART_STYLE.gapLineWidth);
  });
  it("켬/끔은 참·거짓만, 색은 #rrggbb(또는 null)만 받는다", () => {
    const s = sanitizeChartStyle({ smooth: "yes", areaOn: false, noxColor: "#FFAA00", soxColor: "red" });
    expect(s.smooth).toBe(DEFAULT_CHART_STYLE.smooth); // 참·거짓이 아닌 값은 버리고 기본값
    expect(s.areaOn).toBe(false);
    expect(s.noxColor).toBe("#ffaa00");
    expect(s.soxColor).toBeNull();
    expect(sanitizeChartStyle({ noxColor: null }).noxColor).toBeNull();
  });
  it("모르는 항목은 버린다", () => {
    expect(sanitizeChartStyle({ evil: 1, lineWidth: 3 })).toEqual({ ...DEFAULT_CHART_STYLE, lineWidth: 3 });
  });
});

describe("그래프 스타일 저장", () => {
  it("바꾸면 저장되고, 일부만 바꿔도 나머지는 그대로다", () => {
    useChartStyle.getState().set({ lineWidth: 4 });
    useChartStyle.getState().set({ lineGlow: 8 });
    expect(getStyle()).toEqual({ ...defaultsFor("dark"), lineWidth: 4, lineGlow: 8 });
    expect(JSON.parse(window.localStorage.getItem(CHART_STYLE_KEY)!).dark).toMatchObject({ lineWidth: 4, lineGlow: 8 });
  });
  it("범위를 벗어난 값은 맞춰서 저장한다", () => {
    useChartStyle.getState().set({ lineWidth: 100 });
    expect(getStyle().lineWidth).toBe(RANGES.lineWidth[1]);
  });
  it("통째로 바꾸기(가져오기)와 기본값으로 되돌리기", () => {
    useChartStyle.getState().replace({ smooth: true, dotR: 9 });
    expect(getStyle()).toMatchObject({ smooth: true, dotR: 9, lineWidth: DEFAULT_CHART_STYLE.lineWidth });
    useChartStyle.getState().reset();
    expect(getStyle()).toEqual(defaultsFor("dark"));
  });
  it("바꾼 항목 수를 센다", () => {
    expect(changedCount(DEFAULT_CHART_STYLE, "light")).toBe(0);
    expect(changedCount(defaultsFor("dark"), "dark")).toBe(0);
    expect(changedCount({ ...DEFAULT_CHART_STYLE, smooth: false, noxColor: "#112233", dotR: 8 }, "light")).toBe(3);
  });
});

describe("그래프 색 항목", () => {
  it("물질 색(NOx·SOx)과 영역·눈금·안쪽 판·기준선 색은 기본이 null(테마 기본색)이다", () => {
    for (const k of ["noxColor", "soxColor", "areaColor", "gridColor", "innerColor", "levelCautionColor", "levelWarnColor", "levelRiskColor", "levelExceedColor"] as const) {
      expect(DEFAULT_CHART_STYLE[k], k).toBeNull();
      expect(DEFAULT_CHART_STYLE_DARK[k], k).toBeNull();
    }
    expect(COLOR_KEYS).toContain("levelExceedColor");
    expect(COLOR_KEYS.length).toBe(15);
  });
  it("모든 색 항목이 #rrggbb(대소문자 무관)만 받고 나머지는 기본(null)으로 둔다", () => {
    const patch: Record<string, string> = {};
    for (const k of COLOR_KEYS) patch[k] = "#A1B2C3";
    const ok = sanitizeChartStyle(patch);
    for (const k of COLOR_KEYS) expect(ok[k], k).toBe("#a1b2c3");
    const bad: Record<string, string> = {};
    for (const k of COLOR_KEYS) bad[k] = "rgb(1,2,3)";
    const none = sanitizeChartStyle(bad);
    for (const k of COLOR_KEYS) expect(none[k], k).toBe(DEFAULT_CHART_STYLE[k]); // 잘못된 색은 버리고 기본값
  });
  it("바꾼 색도 '바꾼 항목 수'에 센다", () => {
    expect(changedCount({ ...DEFAULT_CHART_STYLE, gridColor: "#112233", levelWarnColor: "#445566" }, "light")).toBe(2);
  });
});

describe("다크·라이트 모드별 설정", () => {
  const setTheme = (t: "dark" | "light") => document.documentElement.setAttribute("data-theme", t);

  it("다크·라이트 기본값은 틀은 같고 글자색·빛·초과 영역 색이 다르다", () => {
    const diff = (Object.keys(DEFAULT_CHART_STYLE) as (keyof typeof DEFAULT_CHART_STYLE)[]).filter((k) => DEFAULT_CHART_STYLE[k] !== DEFAULT_CHART_STYLE_DARK[k]);
    expect(diff.sort()).toEqual(["axisGlow", "crosshairColor", "levelLabelGlow", "pulseGlow", "textColor", "zoneColor", "zoneLabelColor", "zoneLabelGlow"].sort());
  });
  it("모드마다 따로 바뀌고 따로 저장된다(한쪽을 바꿔도 다른 쪽은 그대로)", () => {
    setTheme("dark");
    useChartStyle.getState().set({ lineWidth: 5 });
    setTheme("light");
    expect(getStyle().lineWidth).toBe(DEFAULT_CHART_STYLE.lineWidth); // 라이트는 그대로
    useChartStyle.getState().set({ lineWidth: 2 });
    expect(getStyle("dark").lineWidth).toBe(5);
    expect(getStyle("light").lineWidth).toBe(2);
    const saved = JSON.parse(window.localStorage.getItem(CHART_STYLE_KEY)!);
    expect([saved.dark.lineWidth, saved.light.lineWidth]).toEqual([5, 2]);
  });
  it("모드를 직접 지정해 바꾸거나 되돌릴 수 있다(지금 모드와 상관없이)", () => {
    setTheme("dark");
    useChartStyle.getState().set({ dotR: 9 }, "light");
    expect(getStyle("light").dotR).toBe(9);
    expect(getStyle("dark").dotR).toBe(defaultsFor("dark").dotR);
    useChartStyle.getState().reset("light");
    expect(getStyle("light")).toEqual(defaultsFor("light"));
  });
  it("되돌리기는 그 모드만, 다른 모드의 설정은 건드리지 않는다", () => {
    useChartStyle.getState().set({ lineWidth: 6 }, "dark");
    useChartStyle.getState().set({ lineWidth: 7 }, "light");
    useChartStyle.getState().reset("dark");
    expect(getStyle("dark").lineWidth).toBe(DEFAULT_CHART_STYLE.lineWidth);
    expect(getStyle("light").lineWidth).toBe(7);
  });
  it("다른 모드의 설정을 가져올 수 있다", () => {
    useChartStyle.getState().set({ lineWidth: 6, noxColor: "#123456" }, "light");
    useChartStyle.getState().copyFrom("light", "dark");
    expect(getStyle("dark")).toEqual(getStyle("light"));
    expect(getStyle("dark").noxColor).toBe("#123456");
  });
  it("예전 저장값(모드 구분 없는 한 벌)은 두 모드에 모두 넣는다", () => {
    const s = parseStyles(JSON.stringify({ lineWidth: 4, noxColor: "#abcdef" }));
    expect(s.dark.lineWidth).toBe(4);
    expect(s.light.lineWidth).toBe(4);
    expect(s.dark.noxColor).toBe("#abcdef");
    expect(s.dark.textColor).toBe("#ffffff"); // 저장에 없는 항목은 그 모드의 기본값
    expect(s.light.textColor).toBe("#599765");
  });
  it("모드별 저장값을 읽고, 망가진 저장값은 기본값으로 둔다", () => {
    const s = parseStyles(JSON.stringify({ dark: { lineWidth: 3 }, light: { lineWidth: 5 } }));
    expect([s.dark.lineWidth, s.light.lineWidth]).toEqual([3, 5]);
    for (const bad of [null, "", "{", "[]", "3", "null"]) {
      const p = parseStyles(bad);
      expect(p.dark).toEqual(defaultsFor("dark"));
      expect(p.light).toEqual(defaultsFor("light"));
    }
  });
  it("그래프 안 바깥 글자 크기는 16px 아래로 내려가지 않는다(그림이 줄어드는 화면을 감안한 글자 크기 규칙)", () => {
    for (const k of ["zoneLabelSize", "levelLabelSize", "axisSize"] as const) {
      expect(RANGES[k][0]).toBeGreaterThanOrEqual(16);
      expect(sanitizeChartStyle({ [k]: 5 })[k]).toBe(16);
    }
  });
  it("박동 설정은 범위 안으로 맞춘다", () => {
    const s = sanitizeChartStyle({ pulseScale: 9, pulseSpeed: 0, pulseGlow: -3, pulseOn: false });
    expect(s.pulseScale).toBe(RANGES.pulseScale[1]);
    expect(s.pulseSpeed).toBe(RANGES.pulseSpeed[0]);
    expect(s.pulseGlow).toBe(0);
    expect(s.pulseOn).toBe(false);
  });
});

