import { describe, expect, it } from "vitest";
import type { DayData, Site } from "../data/model";
import { buildNotices, latestRatio, STALE_SLOTS, visibleNotices } from "./notices";

const N = 12;
const times = Array.from({ length: N }, (_, i) => Date.UTC(2026, 10, 10, 0, 0) + i * 1800000);
const site = (id: string, name: string, codes: string[]): Site => ({
  id, name, sido: "서울", sigungu: "중구", address: "", lon: 127, lat: 37, stacks: codes.map((c) => ({ key: `${id}:${c}`, code: c })),
});
/** 한 굴뚝의 NOx(기준 100)를 칸별로 */
const stack = (nox: (string | null)[]) => ({ nox, sox: nox.map(() => null), noxLimit: "100", soxLimit: null });
const fill = (v: string | null, last?: string | null) => Array.from({ length: N }, (_, i) => (i === N - 1 && last !== undefined ? last : v));

const sites = [site("A", "가공장", ["1", "2"]), site("B", "나공장", ["1"]), site("C", "다공장", ["1"]), site("D", "라공장", ["1"])];
const day: DayData = {
  times,
  stacks: {
    "A:1": stack(fill("120")), // 초과
    "A:2": stack(fill("150")), // 같은 사업장에서 더 높은 굴뚝 → 이 굴뚝이 대표
    "B:1": stack(fill("95")), // 위험
    "C:1": stack(fill("110", "미수신")), // 마지막 칸은 공백이지만 직전 칸 110이 3시간 안이라 초과
    "D:1": stack(fill("보수중")), // 값이 하나도 없다
  },
};

describe("최신 비율(3시간 안의 마지막 값)", () => {
  it("마지막 칸이 공백이면 거슬러 올라가 값이 있는 칸을 쓴다", () => {
    expect(latestRatio(day, "C:1")).toBeCloseTo(110);
  });
  it("3시간(6칸)을 넘게 오래된 값은 현재 상황으로 알리지 않는다", () => {
    const old = Array.from({ length: N }, (_, i) => (i <= N - 1 - STALE_SLOTS ? "130" : "미수신"));
    expect(latestRatio({ times, stacks: { X: stack(old) } }, "X")).toBeNull();
    const recent = Array.from({ length: N }, (_, i) => (i === N - STALE_SLOTS ? "130" : "미수신")); // 6칸 안
    expect(latestRatio({ times, stacks: { X: stack(recent) } }, "X")).toBeCloseTo(130);
  });
  it("값이 없거나 모르는 굴뚝은 null", () => {
    expect(latestRatio(day, "D:1")).toBeNull();
    expect(latestRatio(day, "없음")).toBeNull();
  });
});

describe("공지 만들기", () => {
  it("롤링 배너: 초과만, 사업장마다 가장 높은 굴뚝 하나, 비율 높은 순", () => {
    const items = buildNotices(sites, day, { levels: ["exceed"] });
    expect(items.map((i) => [i.name, i.stackCode, Math.round(i.ratio)])).toEqual([["가공장", "2", 150], ["다공장", "1", 110]]);
    expect(items[0].key).toBe("A|2|exceed");
  });
  it("스티커: 즐겨찾기만, 경고 이상(위험 포함), 높은 단계가 먼저", () => {
    const items = buildNotices(sites, day, { levels: ["warn", "risk", "exceed"], only: new Set(["B", "A", "D"]) });
    expect(items.map((i) => [i.name, i.level])).toEqual([["가공장", "exceed"], ["나공장", "risk"]]);
  });
  it("즐겨찾기가 비어 있으면 아무것도 없다", () => {
    expect(buildNotices(sites, day, { levels: ["exceed"], only: new Set() })).toEqual([]);
  });
  it("판정은 지도 시간대가 아니라 마지막 칸 기준이다(앞 칸이 초과여도 지금 정상이면 공지하지 않는다)", () => {
    const calm: DayData = { times, stacks: { "A:1": stack(Array.from({ length: N }, (_, i) => (i < 3 ? "200" : "10"))) } };
    expect(buildNotices([sites[0]], calm, { levels: ["exceed"] })).toEqual([]);
  });
});

describe("닫은 공지 기억", () => {
  const items = buildNotices(sites, day, { levels: ["exceed"] });
  it("모두 닫았으면 안 보이고, 닫지 않은 새 공지가 하나라도 생기면 다시 보인다", () => {
    expect(visibleNotices(items, items.map((i) => i.key))).toEqual([]);
    expect(visibleNotices(items, [items[0].key])).toHaveLength(2); // 하나가 새로 남아 있으면 전체
    expect(visibleNotices([], [])).toEqual([]);
  });
});
