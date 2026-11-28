// 추세 그래프의 모양 설정. 기본값은 D가 설정 패널에서 골라 정한 값이다(2026-11-21).
// 다크·라이트 모드마다 따로 저장한다: 모드를 바꾸면 그 모드의 설정이 적용된다.
// 예전 기본 모양은 시험 도우미(src/test/legacyChartStyle.ts)에 남겨 두었다.
import { create } from "zustand";
import { currentTheme, useThemeName, type ThemeName } from "../theme/useThemeName";

export type { ThemeName };

export interface ChartStyle {
  /** 선 굵기(그림 단위) */
  lineWidth: number;
  /** true면 점을 부드러운 곡선으로 잇는다(값이 튀어 오르내리지 않는 단조 보간) */
  smooth: boolean;
  /** 선의 빛(px). 0이면 없음 */
  lineGlow: number;
  /** 선 아래 영역 채움 */
  areaOn: boolean;
  /** 영역 채움의 위쪽 진하기(0~1). 두 물질을 함께 볼 때는 자동으로 조금 옅다 */
  areaOpacity: number;
  /** 공백 구간을 잇는 점선의 굵기·진하기와 그 아래 칠의 진하기 */
  gapLineWidth: number;
  gapLineOpacity: number;
  gapFillOpacity: number;
  /** 안쪽 가로 눈금선 */
  gridOn: boolean;
  gridOpacity: number;
  /** 주의·경고·위험·초과 기준선 */
  levelLinesOn: boolean;
  levelLineOpacity: number;
  levelLinesDashed: boolean;
  /** 위쪽 20% 기준 초과 영역 칠의 진하기 */
  zoneOpacity: number;
  /** 안쪽 판(그래프 바탕)의 모서리 둥글기와 진하기 */
  innerRadius: number;
  innerOpacity: number;
  /** 선택한 시점의 세로선, 값 점의 크기·빛 */
  crosshairOn: boolean;
  dotR: number;
  dotGlow: number;
  /** 바깥 글자: "기준 초과 영역(압축)" / 오른쪽 단계 글자(초과·위험·경고·주의) / 축 숫자(%·시각)의 크기(px)와 빛(px) */
  zoneLabelSize: number;
  zoneLabelGlow: number;
  levelLabelSize: number;
  levelLabelGlow: number;
  axisSize: number;
  axisGlow: number;
  /** true면 단계 글자 네 개 중 선택한 점의 % 가 속한 단계 하나만 보인다 */
  labelsActiveOnly: boolean;
  /** 박동(두근두근, 로그인 화면의 효과): 선택한 점의 % 가 속한 단계 글자가 커졌다 작아진다 */
  pulseOn: boolean;
  /** 가장 크게 부풀 때의 배율 */
  pulseScale: number;
  /** 한 번 두근거리는 시간(초) */
  pulseSpeed: number;
  /** 부풀 때 번지는 빛(px) */
  pulseGlow: number;
  /** true면 높은 단계일수록 빠르게(초과 0.64배, 위험 0.8배) */
  pulseFast: boolean;
  /** 물질 색(#rrggbb). null이면 테마 기본색 */
  noxColor: string | null;
  soxColor: string | null;
  /** 그 밖의 색(#rrggbb). null이면 테마 기본색(영역·공백 점선은 물질 색을 따른다) */
  areaColor: string | null;
  gapLineColor: string | null;
  gridColor: string | null;
  innerColor: string | null;
  zoneColor: string | null;
  zoneLabelColor: string | null;
  textColor: string | null;
  crosshairColor: string | null;
  dotStrokeColor: string | null;
  levelCautionColor: string | null;
  levelWarnColor: string | null;
  levelRiskColor: string | null;
  levelExceedColor: string | null;
}

/** 라이트 모드의 기본값(D가 라이트 모드에서 고른 값, 2026-11-21) */
export const DEFAULT_CHART_STYLE: ChartStyle = {
  lineWidth: 1,
  smooth: true,
  lineGlow: 2,
  areaOn: true,
  areaOpacity: 0.4,
  gapLineWidth: 1.5,
  gapLineOpacity: 0.5,
  gapFillOpacity: 0.1,
  gridOn: false,
  gridOpacity: 0.75,
  levelLinesOn: true,
  levelLineOpacity: 0.25,
  levelLinesDashed: true,
  zoneOpacity: 0.07,
  innerRadius: 10,
  innerOpacity: 0.35,
  crosshairOn: true,
  dotR: 4,
  dotGlow: 2,
  zoneLabelSize: 16,
  zoneLabelGlow: 0,
  levelLabelSize: 23,
  levelLabelGlow: 1,
  axisSize: 19,
  axisGlow: 1,
  labelsActiveOnly: true,
  pulseOn: true,
  pulseScale: 1.38,
  pulseSpeed: 1.55,
  pulseGlow: 2,
  pulseFast: true,
  noxColor: null,
  soxColor: null,
  areaColor: null,
  gapLineColor: "#84b3a6",
  gridColor: null,
  innerColor: null,
  zoneColor: "#ff0a0a",
  zoneLabelColor: "#ababab",
  textColor: "#599765",
  crosshairColor: "#000000",
  dotStrokeColor: "#dbf6ff",
  levelCautionColor: null,
  levelWarnColor: null,
  levelRiskColor: null,
  levelExceedColor: null,
};

/** 다크 모드의 기본값(D가 다크 모드에서 고른 값, 2026-11-21): 라이트와 같은 틀에 글자·빛·색이 다르다 */
export const DEFAULT_CHART_STYLE_DARK: ChartStyle = {
  ...DEFAULT_CHART_STYLE,
  zoneLabelGlow: 2,
  levelLabelGlow: 2,
  axisGlow: 2,
  pulseGlow: 6,
  zoneColor: null,
  zoneLabelColor: "#ffffff",
  textColor: "#ffffff",
  crosshairColor: "#ffffff",
};

export const defaultsFor = (theme: ThemeName): ChartStyle => ({ ...(theme === "dark" ? DEFAULT_CHART_STYLE_DARK : DEFAULT_CHART_STYLE) });

type NumKey = { [K in keyof ChartStyle]: ChartStyle[K] extends number ? K : never }[keyof ChartStyle];
/** 숫자 설정의 [최소, 최대, 간격]. 패널의 슬라이더와 저장값 검사가 같이 쓴다 */
export const RANGES: Record<NumKey, readonly [number, number, number]> = {
  lineWidth: [1, 8, 0.2],
  lineGlow: [0, 16, 1],
  areaOpacity: [0, 0.9, 0.05],
  gapLineWidth: [1, 6, 0.5],
  gapLineOpacity: [0.1, 1, 0.05],
  gapFillOpacity: [0, 0.6, 0.05],
  gridOpacity: [0, 1, 0.05],
  levelLineOpacity: [0, 1, 0.05],
  zoneOpacity: [0, 0.4, 0.01],
  innerRadius: [0, 24, 1],
  innerOpacity: [0, 1, 0.05],
  dotR: [3, 12, 1],
  dotGlow: [0, 14, 1],
  zoneLabelSize: [16, 28, 1],
  zoneLabelGlow: [0, 14, 1],
  levelLabelSize: [16, 28, 1],
  levelLabelGlow: [0, 14, 1],
  axisSize: [16, 28, 1],
  axisGlow: [0, 14, 1],
  pulseScale: [1.02, 1.6, 0.01],
  pulseSpeed: [0.4, 3, 0.05],
  pulseGlow: [0, 20, 1],
};

const NUM_KEYS = Object.keys(RANGES) as NumKey[];
const BOOL_KEYS = ["smooth", "areaOn", "gridOn", "levelLinesOn", "levelLinesDashed", "crosshairOn", "labelsActiveOnly", "pulseOn", "pulseFast"] as const;
export const COLOR_KEYS = [
  "noxColor", "soxColor", "areaColor", "gapLineColor", "gridColor", "innerColor", "zoneColor", "zoneLabelColor", "textColor",
  "crosshairColor", "dotStrokeColor", "levelCautionColor", "levelWarnColor", "levelRiskColor", "levelExceedColor",
] as const;
export type ColorKey = (typeof COLOR_KEYS)[number];
const HEX = /^#[0-9a-fA-F]{6}$/;

/** 저장값·가져온 값을 안전한 값으로 만든다: 모르는 항목은 버리고, 숫자는 범위에 맞추고, 빠진 것은 base(기본값) */
export function sanitizeChartStyle(raw: unknown, base: ChartStyle = DEFAULT_CHART_STYLE): ChartStyle {
  const out: ChartStyle = { ...base };
  if (!raw || typeof raw !== "object") return out;
  const src = raw as Record<string, unknown>;
  for (const k of NUM_KEYS) {
    const v = src[k];
    if (typeof v === "number" && Number.isFinite(v)) {
      const [min, max] = RANGES[k];
      out[k] = Math.min(max, Math.max(min, v));
    }
  }
  for (const k of BOOL_KEYS) if (typeof src[k] === "boolean") out[k] = src[k] as boolean;
  for (const k of COLOR_KEYS) {
    const v = src[k];
    if (v === null) out[k] = null;
    else if (typeof v === "string" && HEX.test(v)) out[k] = v.toLowerCase();
  }
  return out;
}

export const CHART_STYLE_KEY = "tms-chart-style";
type Styles = Record<ThemeName, ChartStyle>;

const freshStyles = (): Styles => ({ dark: defaultsFor("dark"), light: defaultsFor("light") });

/** 저장값 읽기. 예전(모드 구분 없는 한 벌) 저장값은 두 모드 모두에 넣는다 */
export function parseStyles(text: string | null): Styles {
  if (!text) return freshStyles();
  try {
    const raw = JSON.parse(text) as Record<string, unknown> | null;
    if (!raw || typeof raw !== "object") return freshStyles();
    if ("dark" in raw || "light" in raw) {
      return { dark: sanitizeChartStyle(raw.dark, defaultsFor("dark")), light: sanitizeChartStyle(raw.light, defaultsFor("light")) };
    }
    return { dark: sanitizeChartStyle(raw, defaultsFor("dark")), light: sanitizeChartStyle(raw, defaultsFor("light")) };
  } catch {
    return freshStyles();
  }
}

function read(): Styles {
  try {
    return parseStyles(window.localStorage.getItem(CHART_STYLE_KEY));
  } catch {
    return freshStyles(); // 저장소를 못 읽어도 기본 모양으로 쓴다
  }
}
function write(styles: Styles) {
  try {
    window.localStorage.setItem(CHART_STYLE_KEY, JSON.stringify(styles));
  } catch {
    /* 저장하지 못해도 이번 화면에서는 바뀐다 */
  }
}

interface ChartStyleStore {
  /** 모드별 설정 */
  styles: Styles;
  /** 일부만 바꾼다. 모드를 주지 않으면 지금 화면의 모드 */
  set: (patch: Partial<ChartStyle>, theme?: ThemeName) => void;
  /** 통째로 바꾼다(가져오기) */
  replace: (raw: unknown, theme?: ThemeName) => void;
  /** 그 모드의 모든 설정을 그 모드의 기본값으로 */
  reset: (theme?: ThemeName) => void;
  /** 다른 모드의 설정을 이 모드로 복사한다 */
  copyFrom: (from: ThemeName, to?: ThemeName) => void;
}

export const useChartStyle = create<ChartStyleStore>()((set, get) => {
  const commit = (theme: ThemeName, style: ChartStyle) => {
    const styles = { ...get().styles, [theme]: style };
    write(styles);
    set({ styles });
  };
  return {
    styles: read(),
    set: (patch, theme = currentTheme()) => commit(theme, sanitizeChartStyle({ ...get().styles[theme], ...patch }, defaultsFor(theme))),
    replace: (raw, theme = currentTheme()) => commit(theme, sanitizeChartStyle(raw, defaultsFor(theme))),
    reset: (theme = currentTheme()) => commit(theme, defaultsFor(theme)),
    copyFrom: (from, theme = currentTheme()) => commit(theme, { ...get().styles[from] }),
  };
});

/** 지금 모드(또는 지정한 모드)의 설정 */
export function getStyle(theme: ThemeName = currentTheme()): ChartStyle {
  return useChartStyle.getState().styles[theme];
}

/** 화면에서 쓰는 훅: 지금 모드와 그 모드의 설정. 모드를 바꾸면 따라 바뀐다 */
export function useActiveStyle(): { style: ChartStyle; theme: ThemeName } {
  const theme = useThemeName();
  const style = useChartStyle((s) => s.styles[theme]);
  return { style, theme };
}

/** 그 모드의 기본값과 다른 항목 수(패널에 "N개 바꿈"으로 보여 준다) */
export function changedCount(style: ChartStyle, theme: ThemeName = currentTheme()): number {
  const base = defaultsFor(theme);
  return (Object.keys(base) as (keyof ChartStyle)[]).filter((k) => style[k] !== base[k]).length;
}
