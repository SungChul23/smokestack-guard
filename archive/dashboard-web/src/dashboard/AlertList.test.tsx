import { describe, expect, it } from "vitest";
import type { SiteState } from "../data/model";
import { listAlerts, type ListOptions } from "./AlertList";

describe("즐겨찾기만 보기(내 사업장)", () => {
  const mk = (id: string, level: SiteState["level"], ratio: number | null, lon = 127, lat = 37): SiteState => ({
    site: { id, name: `공장${id}`, sido: "서울", sigungu: "중구", address: "", lon, lat, stacks: [] },
    ratio, level, worstStack: "1",
  });
  const base: ListOptions = { statuses: [], search: "", favorites: ["B", "C"], bounds: null, mapLevels: null };
  const states = [mk("A", "risk", 95), mk("B", "ok", 30), mk("C", null, null), mk("D", "warn", 85)];

  it("끄면 주의 이상만, 켜면 즐겨찾기 사업장만 정상·공백까지 전국에서 모은다", () => {
    expect(listAlerts(states, base).map((s) => s.site.id)).toEqual(["A", "D"]);
    expect(listAlerts(states, { ...base, favoritesOnly: true }).map((s) => s.site.id)).toEqual(["B", "C"]);
  });

  it("지도 범위·지도 상태 칩과 상관없이 내 사업장은 모두 나온다", () => {
    const far = { minX: 0, minY: 0, maxX: 1, maxY: 1 };
    const out = listAlerts(states, { ...base, favoritesOnly: true, bounds: far, mapLevels: ["risk"] });
    expect(out.map((s) => s.site.id)).toEqual(["B", "C"]);
  });

  it("검색어가 있으면 즐겨찾기 안에서만 찾는다", () => {
    expect(listAlerts(states, { ...base, favoritesOnly: true, search: "공장" }).map((s) => s.site.id)).toEqual(["B", "C"]);
    expect(listAlerts(states, { ...base, favoritesOnly: true, search: "공장A" })).toEqual([]);
  });
});
