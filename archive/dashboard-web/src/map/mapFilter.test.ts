import { describe, expect, it } from "vitest";
import type { SiteState } from "../data/model";
import type { LevelKey } from "../logic/status";
import { MAP_SHOW_ORDER } from "../state/selection";
import { showKeyOf, visibleIndices } from "./mapFilter";

const st = (id: string, level: LevelKey | null): SiteState => ({
  site: { id, name: id, sido: "서울", sigungu: "중구", address: "", lon: 127, lat: 37, stacks: [] },
  ratio: level ? 80 : null,
  level,
  worstStack: "1",
});
const states = [st("a", "ok"), st("b", "caution"), st("c", "warn"), st("d", "risk"), st("e", "exceed"), st("f", null)];

describe("지도에 표시할 상태", () => {
  it("측정값이 없으면(단계 없음) 공백으로 본다", () => {
    expect(showKeyOf(st("x", null))).toBe("gap");
    expect(showKeyOf(st("x", "ok"))).toBe("ok");
  });
  it("모두 켜면 전부 보인다", () => {
    expect(visibleIndices(states, MAP_SHOW_ORDER)).toEqual([0, 1, 2, 3, 4, 5]);
  });
  it("정상을 끄면 정상만 빠진다(예전에는 정상·공백이 안 꺼졌다)", () => {
    expect(visibleIndices(states, ["caution", "warn", "risk", "exceed", "gap"])).toEqual([1, 2, 3, 4, 5]);
  });
  it("공백을 끄면 공백만 빠진다", () => {
    expect(visibleIndices(states, ["ok", "caution", "warn", "risk", "exceed"])).toEqual([0, 1, 2, 3, 4]);
  });
  it("경고 단계만 남길 수도 있다", () => {
    expect(visibleIndices(states, ["risk", "exceed"])).toEqual([3, 4]);
    expect(visibleIndices(states, ["caution"])).toEqual([1]);
  });
  it("모두 끄면 아무것도 보이지 않는다", () => {
    expect(visibleIndices(states, [])).toEqual([]);
  });
  it("원래 배열의 인덱스를 그대로, 순서대로 돌려준다", () => {
    const r = visibleIndices(states, ["exceed", "ok", "gap"]);
    expect(r).toEqual([0, 4, 5]);
  });
});

describe("즐겨찾기만 표시", () => {
  const st = (id: string, level: SiteState["level"]): SiteState => ({
    site: { id, name: id, sido: "서울", sigungu: "", address: "", lon: 127, lat: 37, stacks: [] },
    ratio: null, level, worstStack: null,
  });
  const states = [st("A", "risk"), st("B", "ok"), st("C", null)];
  it("onlyIds를 주면 그 사업장만, 상태 칩도 함께 적용된다", () => {
    expect(visibleIndices(states, ["ok", "risk", "gap"], new Set(["B", "C"]))).toEqual([1, 2]);
    expect(visibleIndices(states, ["risk"], new Set(["B", "C"]))).toEqual([]);
    expect(visibleIndices(states, ["ok", "risk", "gap"], null)).toEqual([0, 1, 2]);
  });
});
