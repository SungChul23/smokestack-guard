import { describe, expect, it } from "vitest";
import type { SiteState } from "../data/model";
import type { LevelKey } from "../logic/status";
import { freshAlerts, ranksOf } from "./freshAlerts";

const st = (id: string, level: LevelKey | null): SiteState => ({
  site: { id, name: id, sido: "서울", sigungu: "중구", address: "", lon: 127, lat: 37, stacks: [] },
  ratio: level ? 80 : null,
  level,
  worstStack: "1",
});

describe("새로 경고가 된 굴뚝", () => {
  it("정상·공백에서 주의 이상이 되면 잡는다", () => {
    const prev = ranksOf([st("A", "ok"), st("B", null), st("C", "caution")]);
    const now = [st("A", "caution"), st("B", "exceed"), st("C", "caution")];
    expect(freshAlerts(prev, now, 1).map((s) => s.site.id)).toEqual(["A", "B"]);
  });
  it("이미 경고였던 것이 더 높아져도 잡고, 같거나 낮아지면 잡지 않는다", () => {
    const prev = ranksOf([st("A", "caution"), st("B", "exceed"), st("C", "warn")]);
    const now = [st("A", "risk"), st("B", "warn"), st("C", "warn")];
    expect(freshAlerts(prev, now, 1).map((s) => s.site.id)).toEqual(["A"]);
  });
  it("정상으로 유지되거나 공백이 되는 것은 잡지 않는다", () => {
    const prev = ranksOf([st("A", "ok"), st("B", "warn")]);
    expect(freshAlerts(prev, [st("A", "ok"), st("B", null)], 1)).toEqual([]);
  });
  it("지난 값에 없던 사업장이 경고면 새로 나타난 것으로 본다", () => {
    expect(freshAlerts(ranksOf([]), [st("N", "warn")], 1).map((s) => s.site.id)).toEqual(["N"]);
  });
  it("처음(비교할 이전이 없음)이거나 같은 시각이면 아무것도 잡지 않는다", () => {
    expect(freshAlerts(null, [st("A", "exceed")], 1)).toEqual([]);
    expect(freshAlerts(ranksOf([st("A", "ok")]), [st("A", "exceed")], 0)).toEqual([]);
  });
  it("한두 칸은 앞뒤 모두 잡고, 크게 뛰면(슬라이더 점프) 잡지 않는다", () => {
    const prev = ranksOf([st("A", "ok")]);
    const now = [st("A", "exceed")];
    expect(freshAlerts(prev, now, 1)).toHaveLength(1);
    expect(freshAlerts(prev, now, -2)).toHaveLength(1);
    expect(freshAlerts(prev, now, 3)).toEqual([]);
    expect(freshAlerts(prev, now, -20)).toEqual([]);
  });
  it("한꺼번에 많아도 상한 없이 모두 알려 준다(묶음 단위로 그리는 쪽에서 한 번만 번쩍인다)", () => {
    const ids = Array.from({ length: 300 }, (_, i) => `S${i}`);
    const prev = ranksOf(ids.map((i) => st(i, "ok")));
    expect(freshAlerts(prev, ids.map((i) => st(i, "warn")), 1)).toHaveLength(300);
  });
});
