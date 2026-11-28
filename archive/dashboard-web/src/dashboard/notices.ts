// 공지(롤링 배너·스티커)의 판정·정렬(순수 함수). 옛 웹 notice-banner-core.js를 옮겼다.
// 판정은 지도 시간대 슬라이더가 아니라 **최신 데이터**(마지막 칸)를 현재 상태로 본다.
import { stackRatioAt, type DayData, type Site } from "../data/model";
import { levelOf, type LevelKey } from "../logic/status";

/** 최신 값이 이 칸 수(30분 × 6 = 3시간)보다 오래됐으면 현재 상황으로 알리지 않는다(옛 웹의 3시간 규칙) */
export const STALE_SLOTS = 6;

const ORDER: Record<LevelKey, number> = { ok: 0, caution: 1, warn: 2, risk: 3, exceed: 4 };

export interface Notice {
  /** 같은 사업장·굴뚝·단계면 같은 키. 닫은 공지를 기억하고, 새 키(새 굴뚝·더 나빠진 단계)가 생기면 다시 보이게 한다 */
  key: string;
  siteId: string;
  name: string;
  stackCode: string;
  level: LevelKey;
  ratio: number;
}

export interface NoticeOptions {
  /** 공지로 만들 단계 */
  levels: readonly LevelKey[];
  /** 주면 이 사업장만(즐겨찾기) */
  only?: ReadonlySet<string>;
}

/** 굴뚝의 현재 비율: 마지막 칸에서 거슬러 올라가 값이 있는 첫 칸(최대 STALE_SLOTS칸). 없으면 null */
export function latestRatio(day: DayData, stackKey: string): number | null {
  const s = day.stacks[stackKey];
  if (!s) return null;
  const last = day.times.length - 1;
  for (let i = last; i > last - STALE_SLOTS && i >= 0; i--) {
    const r = stackRatioAt(s, i);
    if (r !== null) return r;
  }
  return null;
}

/** 사업장마다 비율이 가장 높은 굴뚝 하나를 공지로 만든다. 높은 단계 → 높은 비율 → 이름 순 */
export function buildNotices(sites: readonly Site[], day: DayData, opts: NoticeOptions): Notice[] {
  const out: Notice[] = [];
  for (const site of sites) {
    if (opts.only && !opts.only.has(site.id)) continue;
    let best: { ratio: number; code: string } | null = null;
    for (const st of site.stacks) {
      const r = latestRatio(day, st.key);
      if (r !== null && (best === null || r > best.ratio)) best = { ratio: r, code: st.code };
    }
    if (!best) continue;
    const level = levelOf(best.ratio);
    if (!level || !opts.levels.includes(level)) continue;
    out.push({ key: `${site.id}|${best.code}|${level}`, siteId: site.id, name: site.name, stackCode: best.code, level, ratio: best.ratio });
  }
  return out.sort(
    (a, b) => ORDER[b.level] - ORDER[a.level] || b.ratio - a.ratio || a.name.localeCompare(b.name, "ko"),
  );
}

/** 닫은 공지를 빼고 보여 줄 목록. 닫지 않은 새 공지가 하나라도 있으면 전체가 다시 보인다(옛 웹 규칙) */
export function visibleNotices(items: readonly Notice[], dismissed: readonly string[]): Notice[] {
  const d = new Set(dismissed);
  return items.some((i) => !d.has(i.key)) ? [...items] : [];
}

const STORAGE_KEY = "tms-notice-dismissed";
export function readDismissed(): string[] {
  try {
    const v = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}
export function writeDismissed(keys: readonly string[]): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...new Set(keys)]));
  } catch {
    /* 저장하지 못해도 이번 화면에서는 닫힌다 */
  }
}
