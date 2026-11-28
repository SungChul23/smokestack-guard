import { describe, expect, it } from "vitest";
import { DEFAULT_TOP_RATIO, FIXED_FRACTION, fractionOf, gapLinks, makeScale, topRatioFor } from "./chartScale";

describe("위쪽 영역의 한계", () => {
  it("기본은 120%이고 120%까지는 변하지 않는다", () => {
    expect(DEFAULT_TOP_RATIO).toBe(120);
    expect(topRatioFor(0)).toBe(120);
    expect(topRatioFor(85)).toBe(120);
    expect(topRatioFor(120)).toBe(120); // 딱 120%여도 늘리지 않는다
  });
  it("120%를 넘을 때만 10% 단위로 올려 늘어난다", () => {
    expect(topRatioFor(121)).toBe(130); // 127.05 → 130
    expect(topRatioFor(300)).toBe(320); // 315 → 320
    expect(topRatioFor(1000)).toBe(1050);
  });
  it("숫자가 아니면 기본값", () => {
    expect(topRatioFor(NaN)).toBe(120);
    expect(topRatioFor(Infinity)).toBe(120);
  });
});

describe("높이 비율", () => {
  it("기준값 이하는 높이의 80%에 선형으로 고정된다", () => {
    expect(FIXED_FRACTION).toBe(0.8);
    expect(fractionOf(0, 120)).toBe(0);
    expect(fractionOf(50, 120)).toBeCloseTo(0.4);
    expect(fractionOf(100, 120)).toBeCloseTo(0.8);
    expect(fractionOf(70, 999)).toBeCloseTo(0.56); // 위쪽 한계가 얼마든 아래쪽은 같다
  });
  it("기준 위는 남은 20%에 들어가고 한계에서 꼭대기에 닿는다", () => {
    expect(fractionOf(110, 120)).toBeCloseTo(0.9);
    expect(fractionOf(120, 120)).toBeCloseTo(1);
    expect(fractionOf(500, 120)).toBe(1); // 한계를 넘으면 꼭대기에 붙는다
  });
  it("위쪽 한계가 늘어나도 아래쪽 80%의 모양은 변하지 않는다(날카로워지지 않는다)", () => {
    const a = makeScale([50, 100], 100), b = makeScale([50, 100, 900], 100);
    expect(a.toFraction(50)).toBeCloseTo(b.toFraction(50));
    expect(a.toFraction(100)).toBeCloseTo(b.toFraction(100));
    expect(b.toFraction(900)).toBeLessThanOrEqual(1);
    expect(b.toFraction(900)).toBeGreaterThan(0.8);
  });
  it("음수·NaN은 바닥(0)이다", () => {
    expect(fractionOf(-5, 120)).toBe(0);
    expect(fractionOf(NaN, 120)).toBe(0);
  });
});

describe("눈금 만들기", () => {
  it("기준값이 있으면 기준(100%)이 높이의 80% 자리에 오고, 기본 위쪽은 120%", () => {
    const s = makeScale([10, 90, 105], 100);
    expect(s.topRatio).toBe(120);
    expect(s.topValue).toBe(120);
    expect(s.toFraction(100)).toBeCloseTo(0.8);
    expect(s.toFraction(120)).toBeCloseTo(1);
  });
  it("값이 기준을 크게 넘으면 위쪽 한계가 늘고 최대값이 꼭대기 안에 들어온다", () => {
    const s = makeScale([10, 300], 100);
    expect(s.topRatio).toBe(320);
    expect(s.toFraction(300)).toBeLessThan(1);
    expect(s.toFraction(300)).toBeGreaterThan(0.95);
  });
  it("실측 단위가 달라도 기준 대비로 같은 모양이다(기준 150일 때 150이 80% 자리)", () => {
    expect(makeScale([20], 150).toFraction(150)).toBeCloseTo(0.8);
  });
  it("기준값이 없으면 선형이고 위쪽 영역이 없다", () => {
    const s = makeScale([0, 40], null);
    expect(s.limit).toBeNull();
    expect(s.topRatio).toBeNull();
    expect(s.toFraction(0)).toBe(0);
    expect(s.toFraction(40)).toBeCloseTo(40 / 48);
    expect(makeScale([null, null], null).topValue).toBe(1); // 값이 없어도 0으로 나누지 않는다
  });
  it("기준값이 0 이하이면 없는 것으로 본다", () => {
    expect(makeScale([5], 0).limit).toBeNull();
  });
});

describe("값이 없는 구간을 점선으로 잇기", () => {
  const p = (...v: Array<number | null>) => v.map((value) => ({ value }));
  it("실측 사이의 빈 구간은 양쪽 실측을 잇는다", () => {
    expect(gapLinks(p(10, null, null, 20, 30))).toEqual([{ kind: "bridge", i0: 0, v0: 10, i1: 3, v1: 20 }]);
  });
  it("연속된 실측 사이는 잇지 않는다", () => {
    expect(gapLinks(p(10, 20, 30))).toEqual([]);
  });
  it("여러 빈 구간은 각각 잇는다", () => {
    const links = gapLinks(p(1, null, 3, null, null, 6));
    expect(links.map((l) => [l.i0, l.i1])).toEqual([[0, 2], [2, 5]]);
  });
  it("마지막 실측 뒤가 비면 그 값 높이로 오른쪽 끝까지 안내선을 낸다", () => {
    expect(gapLinks(p(10, 20, null, null))).toEqual([{ kind: "trailing", i0: 1, v0: 20, i1: 3, v1: 20 }]);
  });
  it("처음 실측 앞쪽 빈 구간도 첫 값 높이의 점선으로 채운다(빈 영역이 남지 않게)", () => {
    expect(gapLinks(p(null, null, 5, 6))).toEqual([{ kind: "leading", i0: 0, v0: 5, i1: 2, v1: 5 }]);
  });
  it("앞·가운데·뒤가 모두 비어 있으면 세 가지가 다 생긴다", () => {
    const kinds = gapLinks(p(null, 4, null, 6, null)).map((l) => l.kind);
    expect(kinds).toEqual(["leading", "bridge", "trailing"]);
  });
  it("값이 없는 칸은 모두 어느 선분 아래에 들어간다(칠해지지 않은 빈 칸이 없다)", () => {
    const pts = p(null, null, 3, null, 5, 6, null, null, 9, null);
    const covered = new Set<number>();
    for (const l of gapLinks(pts)) for (let i = l.i0; i <= l.i1; i++) covered.add(i);
    pts.forEach((q, i) => { if (q.value === null) expect(covered.has(i)).toBe(true); });
  });
  it("실측이 하나도 없을 때만 선분이 없다(전체를 옅게 칠하는 쪽에서 처리)", () => {
    expect(gapLinks(p(null, null))).toEqual([]);
  });
  it("실측이 하나도 없으면 아무것도 잇지 않는다", () => {
    expect(gapLinks(p(null, null, null))).toEqual([]);
    expect(gapLinks([])).toEqual([]);
  });
  it("실측이 하나뿐이면 앞뒤 안내선만 낸다", () => {
    expect(gapLinks(p(null, 7, null)).map((l) => l.kind)).toEqual(["leading", "trailing"]);
  });
});
