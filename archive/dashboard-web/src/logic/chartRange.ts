// 차트 조회 범위(순수 함수). 옛 웹의 "조회 범위" 동작을 옮겼다:
// 시작·종료 일시를 달력으로 고르고, 이전·다음 구간으로 옮기고, 그래프를 끌어 30분씩 밀고, 자료 기준으로 되돌린다.
// 범위는 보여 주는 창일 뿐이다. 날짜를 골라도 없는 측정을 만들거나 수집을 일으키지 않는다.
// 시각은 모두 ms(UTC)이고, 사람이 보고 입력하는 값은 한국 시각(KST)이다.

export const SLOT_MS = 30 * 60 * 1000;
const KST_MS = 9 * 3600 * 1000;

export interface ChartRange {
  start: number;
  end: number;
}
/** 보관된 자료가 닿는 범위(첫 시점 ~ 마지막 시점) */
export type Extent = ChartRange;

export function extentOf(times: number[]): Extent | null {
  return times.length ? { start: times[0], end: times[times.length - 1] } : null;
}

/** 자료 기준 기본 범위: 마지막 시점에서 거슬러 올라가 hours시간(30분 칸 hours*2개). 자료가 모자라면 있는 만큼 */
export function defaultRange(times: number[], hours: number): ChartRange | null {
  const ext = extentOf(times);
  if (!ext) return null;
  return { start: Math.max(ext.start, ext.end - (hours * 2 - 1) * SLOT_MS), end: ext.end };
}

/** 범위 안(경계 포함)에 드는 시점의 처음·마지막 인덱스. 하나도 없으면 null */
export function indicesIn(times: number[], r: ChartRange): [number, number] | null {
  let first = -1, last = -1;
  for (let i = 0; i < times.length; i++) {
    if (times[i] >= r.start && times[i] <= r.end) {
      if (first < 0) first = i;
      last = i;
    }
  }
  return first < 0 ? null : [first, last];
}

/** 길이를 유지한 채 자료 범위 안으로 밀어 넣는다. 자료보다 길면 자료 전체 */
export function clampRange(r: ChartRange, ext: Extent): ChartRange {
  const len = r.end - r.start;
  if (len >= ext.end - ext.start) return { ...ext };
  const start = Math.min(Math.max(r.start, ext.start), ext.end - len);
  return { start, end: start + len };
}

/**
 * 이전(-1)·다음(+1) 구간: 지금 창에 든 칸 수만큼 넘긴다(길이 + 한 칸). 한 점이 두 구간에 겹쳐 보이지 않고 한 구간에만 속한다.
 * 자료 끝에서 멈춘다.
 */
export function shiftRange(r: ChartRange, direction: -1 | 1, ext: Extent): ChartRange {
  const step = r.end - r.start + SLOT_MS;
  return clampRange({ start: r.start + direction * step, end: r.end + direction * step }, ext);
}

/** 그래프를 끌어서 옮기기: slots칸(30분 단위, 양수는 뒤로=미래 쪽) */
export function panRange(r: ChartRange, slots: number, ext: Extent): ChartRange {
  return clampRange({ start: r.start + slots * SLOT_MS, end: r.end + slots * SLOT_MS }, ext);
}

export type RangeCheck = { ok: true; range: ChartRange } | { ok: false; error: string };

/**
 * 사용자가 입력한 시작·종료를 확인한다. 종료는 시작보다 뒤여야 하고, 보관된 기간과 겹쳐야 한다.
 * 겹치면 보관된 기간 안으로 줄여서 받아 주되, 그 안에 보관된 시점이 하나도 없으면 거절한다.
 */
export function validateRange(start: number, end: number, ext: Extent, times: number[]): RangeCheck {
  if (!Number.isFinite(start) || !Number.isFinite(end)) return { ok: false, error: "시작·종료 일시를 확인하세요." };
  if (end <= start) return { ok: false, error: "종료는 시작보다 뒤여야 합니다." };
  if (end < ext.start || start > ext.end) {
    return { ok: false, error: `보관된 기간(${formatKstInput(ext.start).replace("T", " ")} ~ ${formatKstInput(ext.end).replace("T", " ")}) 밖입니다.` };
  }
  const range = { start: Math.max(start, ext.start), end: Math.min(end, ext.end) };
  if (!indicesIn(times, range)) return { ok: false, error: "선택한 시각 사이에 보관된 측정이 없습니다." };
  return { ok: true, range };
}

/** "2026-11-10T09:30" (한국 시각) → ms. 형식이 다르면 NaN */
export function parseKstInput(value: string): number {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::\d{2})?$/.exec(value.trim());
  if (!m) return NaN;
  const [, y, mo, d, h, mi] = m.map(Number);
  if (mo < 1 || mo > 12 || d < 1 || d > 31 || h > 23 || mi > 59) return NaN;
  const ms = Date.UTC(y, mo - 1, d, h, mi) - KST_MS;
  // 2월 30일 같은 없는 날짜는 JS가 다음 달로 넘기므로 되돌려 확인한다
  return formatKstInput(ms) === `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}` ? ms : NaN;
}

/** ms → "2026-11-10T09:30" (한국 시각, datetime-local 입력용) */
export function formatKstInput(ms: number): string {
  return new Date(ms + KST_MS).toISOString().slice(0, 16);
}

/** 길이를 "23시간 30분"처럼 */
export function durationText(ms: number): string {
  const minutes = Math.round(ms / 60000);
  const h = Math.floor(minutes / 60), m = minutes % 60;
  return `${h ? `${h}시간` : ""}${h && m ? " " : ""}${m ? `${m}분` : ""}` || "0분";
}

/** 자료 기준 기본 범위와 같은지(같으면 "기본 범위", 아니면 "사용자 지정") */
export function isDefaultRange(r: ChartRange, times: number[], hours: number): boolean {
  const d = defaultRange(times, hours);
  return !!d && d.start === r.start && d.end === r.end;
}

/** 기간 버튼 후보(시간). 자료가 그 길이를 채울 때만 보인다 */
export const PERIOD_CHOICES = [6, 12, 24, 48, 72, 168] as const;
export function periodChoices(times: number[]): number[] {
  const ext = extentOf(times);
  if (!ext) return [];
  const span = ext.end - ext.start;
  return PERIOD_CHOICES.filter((h) => (h * 2 - 1) * SLOT_MS <= span);
}
