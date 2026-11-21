import { describe, expect, it } from "vitest";
import {
  allSiteStates,
  countByLevel,
  formatSlot,
  parseNumber,
  ratioOf,
  siteStateAt,
  stackRatioAt,
  type DayData,
  type Site,
} from "./model";

const site = (id: string, codes: string[]): Site => ({
  id, name: id, sido: "서울", sigungu: "중구", address: "", lon: 127, lat: 37,
  stacks: codes.map((c) => ({ key: `${id}:${c}`, code: c })),
});

describe("숫자 읽기", () => {
  it("일반 숫자와 올바른 쉼표 묶음만 숫자다", () => {
    expect(parseNumber("14.00")).toBe(14);
    expect(parseNumber("1,234.5")).toBe(1234.5);
    expect(parseNumber("12,34")).toBeNull();
    expect(parseNumber("1,23,456")).toBeNull();
  });
  it("문구·빈칸·무한대는 숫자가 아니다", () => {
    for (const v of ["기기점검", "", "  ", null, undefined, "NaN", "Infinity"]) {
      expect(parseNumber(v)).toBeNull();
    }
  });
});

describe("비율", () => {
  it("값/기준×100", () => {
    expect(ratioOf("80", "100")).toBe(80);
    expect(ratioOf("0", "100")).toBe(0);
  });
  it("값이 없거나 기준이 0 이하면 null (0이 아니다)", () => {
    expect(ratioOf("보수중", "150")).toBeNull();
    expect(ratioOf(null, "150")).toBeNull();
    expect(ratioOf("10", null)).toBeNull();
    expect(ratioOf("10", "0")).toBeNull();
    expect(ratioOf("10", "-5")).toBeNull();
  });
});

const day: DayData = {
  times: [0, 1800000],
  stacks: {
    "A:1": { nox: ["50", "보수중"], sox: ["10", null], noxLimit: "100", soxLimit: "100" },
    "A:2": { nox: ["95", "95"], sox: [null, null], noxLimit: "100", soxLimit: null },
    "B:1": { nox: ["110", null], sox: [null, null], noxLimit: "100", soxLimit: null },
    "C:1": { nox: ["기기점검", "기기점검"], sox: [null, null], noxLimit: "100", soxLimit: null },
  },
};

describe("굴뚝·사업장 판정", () => {
  it("굴뚝 비율은 NOx·SOx 중 큰 값이다", () => {
    expect(stackRatioAt(day.stacks["A:1"], 0)).toBe(50);
  });
  it("한 물질만 있으면 그 값을, 둘 다 없으면 null을 쓴다", () => {
    expect(stackRatioAt(day.stacks["A:1"], 1)).toBeNull();
    expect(stackRatioAt(day.stacks["A:2"], 0)).toBe(95);
    expect(stackRatioAt(undefined, 0)).toBeNull();
  });
  it("사업장 비율은 굴뚝 중 가장 높은 값이고 그 굴뚝 번호를 알려 준다", () => {
    const s = siteStateAt(site("A", ["1", "2"]), day, 0);
    expect(s.ratio).toBe(95);
    expect(s.level).toBe("risk");
    expect(s.worstStack).toBe("2");
  });
  it("측정이 전혀 없는 사업장은 공백(null)이며 정상이 아니다", () => {
    const s = siteStateAt(site("C", ["1"]), day, 0);
    expect(s.ratio).toBeNull();
    expect(s.level).toBeNull();
  });
  it("단계별 개수는 정상·공백을 세지 않는다", () => {
    const sites = [site("A", ["1", "2"]), site("B", ["1"]), site("C", ["1"])];
    const counts = countByLevel(allSiteStates(sites, day, 0));
    expect(counts).toEqual({ caution: 0, warn: 0, risk: 1, exceed: 1 });
  });
});

describe("시각 표기", () => {
  it("한국 시각으로 월-일 시:분", () => {
    expect(formatSlot(Date.UTC(2026, 10, 10, 14, 30))).toBe("11-10 23:30");
  });
});
