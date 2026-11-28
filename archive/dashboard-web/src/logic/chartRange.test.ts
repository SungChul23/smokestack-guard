import { describe, expect, it } from "vitest";
import {
  SLOT_MS, clampRange, defaultRange, durationText, extentOf, formatKstInput, indicesIn, isDefaultRange, panRange,
  parseKstInput, periodChoices, shiftRange, validateRange,
} from "./chartRange";

// 한국 시각 11-10 00:00 부터 30분 간격 48칸(하루)
const start = Date.UTC(2026, 10, 9, 15, 0);
const day = Array.from({ length: 48 }, (_, i) => start + i * SLOT_MS);
// 3일치(144칸)
const three = Array.from({ length: 144 }, (_, i) => start + i * SLOT_MS);

describe("자료 범위와 기본 범위", () => {
  it("자료의 첫·마지막 시점이 범위다", () => {
    expect(extentOf(day)).toEqual({ start: day[0], end: day[47] });
    expect(extentOf([])).toBeNull();
  });
  it("기본 범위는 마지막에서 거슬러 올라간 N시간(30분 칸 2N개)이다", () => {
    const r = defaultRange(day, 6)!;
    expect(r.end).toBe(day[47]);
    expect(indicesIn(day, r)).toEqual([36, 47]); // 12칸
  });
  it("자료가 모자라면 있는 만큼만(24시간 요청에 하루치)", () => {
    expect(defaultRange(day, 24)).toEqual({ start: day[0], end: day[47] });
    expect(defaultRange(day, 72)).toEqual({ start: day[0], end: day[47] });
  });
  it("자료가 없으면 null", () => {
    expect(defaultRange([], 6)).toBeNull();
  });
});

describe("범위 안의 시점", () => {
  it("경계를 포함해 처음·마지막 인덱스를 돌려준다", () => {
    expect(indicesIn(day, { start: day[10], end: day[20] })).toEqual([10, 20]);
  });
  it("시점 사이에 낀 범위(30분 칸 사이)는 하나도 없으면 null", () => {
    expect(indicesIn(day, { start: day[10] + 1000, end: day[11] - 1000 })).toBeNull();
  });
  it("범위가 자료 밖이면 null", () => {
    expect(indicesIn(day, { start: day[47] + SLOT_MS, end: day[47] + 3 * SLOT_MS })).toBeNull();
  });
});

describe("옮기기", () => {
  const ext = extentOf(three)!;
  const w = { start: three[48], end: three[71] }; // 가운데 하루의 앞쪽 12시간
  it("이전·다음 구간은 칸 수만큼 넘긴다: 한 점이 두 구간에 겹치지 않는다", () => {
    const next = shiftRange(w, 1, ext);
    expect(next.start).toBe(w.end + SLOT_MS); // 끝 다음 칸에서 시작
    expect(next.end - next.start).toBe(w.end - w.start); // 길이는 그대로
    const prev = shiftRange(w, -1, ext);
    expect(prev.end).toBe(w.start - SLOT_MS); // 시작 바로 앞 칸에서 끝
    // 이어서 넘기면 같은 자리로 돌아온다
    expect(shiftRange(next, -1, ext)).toEqual(w);
  });
  it("넘긴 구간끼리 칸이 겹치거나 빠지지 않는다(24칸 창으로 144칸을 훑으면 정확히 6쪽)", () => {
    let r = { start: three[0], end: three[23] };
    const seen: number[] = [];
    for (let k = 0; k < 6; k++) {
      const [a, b] = indicesIn(three, r)!;
      for (let i = a; i <= b; i++) seen.push(i);
      r = shiftRange(r, 1, ext);
    }
    expect(seen).toEqual(Array.from({ length: 144 }, (_, i) => i));
  });
  it("자료 끝에서는 더 가지 않고 길이를 유지한다", () => {
    const last = { start: three[120], end: three[143] };
    const r = shiftRange(last, 1, ext);
    expect(r).toEqual(last);
    const first = { start: three[0], end: three[23] };
    expect(shiftRange(first, -1, ext)).toEqual(first);
  });
  it("끌어서 30분 단위로 민다(양수는 미래 쪽)", () => {
    expect(panRange(w, 3, ext)).toEqual({ start: w.start + 3 * SLOT_MS, end: w.end + 3 * SLOT_MS });
    expect(panRange(w, -2, ext).start).toBe(w.start - 2 * SLOT_MS);
  });
  it("끌어도 자료 밖으로 나가지 않는다", () => {
    expect(panRange(w, 9999, ext).end).toBe(ext.end);
    expect(panRange(w, -9999, ext).start).toBe(ext.start);
  });
  it("자료보다 긴 범위는 자료 전체로 줄인다", () => {
    expect(clampRange({ start: ext.start - 1e9, end: ext.end + 1e9 }, ext)).toEqual(ext);
  });
  it("길이를 유지한 채 밀어 넣는다(범위를 찌그러뜨리지 않는다)", () => {
    const len = 10 * SLOT_MS;
    const r = clampRange({ start: ext.end - 3 * SLOT_MS, end: ext.end - 3 * SLOT_MS + len }, ext);
    expect(r.end).toBe(ext.end);
    expect(r.end - r.start).toBe(len);
  });
});

describe("입력 확인", () => {
  const ext = extentOf(day)!;
  it("보관된 기간 안의 정상 입력은 그대로 받는다", () => {
    const r = validateRange(day[5], day[20], ext, day);
    expect(r).toEqual({ ok: true, range: { start: day[5], end: day[20] } });
  });
  it("종료가 시작보다 뒤여야 한다", () => {
    expect(validateRange(day[20], day[5], ext, day)).toMatchObject({ ok: false });
    expect(validateRange(day[5], day[5], ext, day)).toMatchObject({ ok: false });
  });
  it("숫자가 아니면 거절한다", () => {
    expect(validateRange(NaN, day[5], ext, day)).toMatchObject({ ok: false });
  });
  it("보관된 기간과 안 겹치면 기간을 알려 주며 거절한다", () => {
    const r = validateRange(day[47] + SLOT_MS, day[47] + 5 * SLOT_MS, ext, day);
    expect(r.ok).toBe(false);
    expect((r as { error: string }).error).toContain("보관된 기간");
    expect((r as { error: string }).error).toContain("2026-11-10 00:00");
  });
  it("걸치면 보관된 기간 안으로 줄여서 받는다", () => {
    const r = validateRange(day[0] - 5 * SLOT_MS, day[3], ext, day);
    expect(r).toEqual({ ok: true, range: { start: day[0], end: day[3] } });
  });
  it("그 안에 보관된 시점이 하나도 없으면 거절한다(30분 칸 사이)", () => {
    const r = validateRange(day[10] + 1000, day[11] - 1000, ext, day);
    expect(r).toMatchObject({ ok: false });
  });
});

describe("한국 시각 입력 형식", () => {
  it("datetime-local 값 ↔ ms", () => {
    expect(formatKstInput(day[0])).toBe("2026-11-10T00:00");
    expect(formatKstInput(day[47])).toBe("2026-11-10T23:30");
    expect(parseKstInput("2026-11-10T00:00")).toBe(day[0]);
    expect(parseKstInput("2026-11-10T23:30:00")).toBe(day[47]); // 초가 붙어도 된다
  });
  it("형식이 틀리거나 없는 날짜·시각이면 NaN", () => {
    for (const bad of ["", "2026-11-10", "2026/11/10 00:00", "2026-13-01T00:00", "2026-02-30T10:00", "2026-11-10T24:00", "2026-11-10T10:60"]) {
      expect(parseKstInput(bad)).toBeNaN();
    }
  });
  it("왕복해도 같다", () => {
    for (const t of [day[0], day[17], day[47]]) expect(parseKstInput(formatKstInput(t))).toBe(t);
  });
});

describe("표기와 기본 범위 판별", () => {
  it("길이 표기", () => {
    expect(durationText(23.5 * 3600000)).toBe("23시간 30분");
    expect(durationText(6 * 3600000)).toBe("6시간");
    expect(durationText(30 * 60000)).toBe("30분");
    expect(durationText(0)).toBe("0분");
  });
  it("기본 범위와 같으면 기본, 다르면 사용자 지정", () => {
    expect(isDefaultRange(defaultRange(day, 12)!, day, 12)).toBe(true);
    expect(isDefaultRange({ start: day[0], end: day[10] }, day, 12)).toBe(false);
  });
  it("기간 버튼은 자료가 채우는 길이만 보인다", () => {
    expect(periodChoices(day)).toEqual([6, 12, 24]);
    expect(periodChoices(three)).toEqual([6, 12, 24, 48, 72]);
    expect(periodChoices([])).toEqual([]);
  });
});
