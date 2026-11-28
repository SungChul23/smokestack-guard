// 화면 데이터 모델과 규칙(순수 함수). 보관된 원문(raw)에서 비율·상태를 계산한다.
// 규칙(옛 console-number.js·map-time-model.js에서 옮김, spec 318 §10):
//  - 숫자는 천 단위 쉼표가 올바르게 묶인 것만 인정한다. 그 밖의 문자열은 숫자가 아니다.
//  - 비율 = 값 / 기준 × 100. 값이 없거나 기준이 0 이하면 비율은 null이다(0으로 채우지 않는다).
//  - 굴뚝 비율 = NOx·SOx 중 큰 값. 사업장 비율 = 굴뚝 비율 중 큰 값.
//  - 값 칸이 문구(가동중지·기기점검 등)이거나 비어 있으면 "공백"이다. 정상이 아니다.
import { levelOf, type LevelKey } from "../logic/status";

export type Pollutant = "nox" | "sox";
/** 보관된 원문. 숫자 문자열, 상태 문구, 또는 null(칸 없음) */
export type Raw = string | null;

export interface StackRef {
  key: string; // "{site_id}:{굴뚝번호}"
  code: string;
}
export interface Site {
  id: string;
  name: string;
  sido: string;
  sigungu: string;
  address: string;
  lon: number;
  lat: number;
  stacks: StackRef[];
}
export interface StackSeries {
  nox: Raw[];
  sox: Raw[];
  noxLimit: Raw;
  soxLimit: Raw;
}
export interface DayData {
  /** 30분 간격 시점(ms, 오래된 것부터) */
  times: number[];
  stacks: Record<string, StackSeries>;
}
export interface GeoRegion {
  name: string;
  type: "Polygon" | "MultiPolygon";
  coordinates: unknown;
}

const PLAIN = /^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$/;
const GROUPED = /^[+-]?[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$/;

export function parseNumber(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string") return null;
  let text = value.trim();
  if (text.includes(",")) {
    if (!GROUPED.test(text)) return null;
    text = text.replace(/,/g, "");
  }
  if (!PLAIN.test(text)) return null;
  const n = Number(text);
  return Number.isFinite(n) ? n : null;
}

export function ratioOf(raw: Raw, limit: Raw): number | null {
  const v = parseNumber(raw);
  const l = parseNumber(limit);
  return v !== null && l !== null && l > 0 ? (v / l) * 100 : null;
}

export function pollutantRaw(s: StackSeries, p: Pollutant): Raw[] {
  return p === "nox" ? s.nox : s.sox;
}
export function pollutantLimit(s: StackSeries, p: Pollutant): Raw {
  return p === "nox" ? s.noxLimit : s.soxLimit;
}

/** 굴뚝의 한 시점 비율: NOx·SOx 중 큰 값, 둘 다 없으면 null */
export function stackRatioAt(s: StackSeries | undefined, slot: number): number | null {
  if (!s) return null;
  const a = ratioOf(s.nox[slot] ?? null, s.noxLimit);
  const b = ratioOf(s.sox[slot] ?? null, s.soxLimit);
  if (a === null) return b;
  if (b === null) return a;
  return Math.max(a, b);
}

export interface SiteState {
  site: Site;
  ratio: number | null;
  level: LevelKey | null;
  /** 가장 높은 비율의 굴뚝 번호 */
  worstStack: string | null;
}

export function siteStateAt(site: Site, day: DayData, slot: number): SiteState {
  let best: number | null = null;
  let worst: string | null = null;
  for (const st of site.stacks) {
    const r = stackRatioAt(day.stacks[st.key], slot);
    if (r !== null && (best === null || r > best)) {
      best = r;
      worst = st.code;
    }
  }
  return { site, ratio: best, level: levelOf(best), worstStack: worst };
}

export function allSiteStates(sites: Site[], day: DayData, slot: number): SiteState[] {
  return sites.map((s) => siteStateAt(s, day, slot));
}

/** 단계별 사업장 수(정상 제외). 공백은 어느 단계에도 세지 않는다. */
export function countByLevel(states: SiteState[]): Record<Exclude<LevelKey, "ok">, number> {
  const out = { caution: 0, warn: 0, risk: 0, exceed: 0 };
  for (const s of states) if (s.level && s.level !== "ok") out[s.level]++;
  return out;
}

/** 시점 ms → "11-10 23:30" (한국 시각) */
export function formatSlot(ms: number): string {
  const d = new Date(ms + 9 * 3600000).toISOString();
  return `${d.slice(5, 10)} ${d.slice(11, 16)}`;
}
