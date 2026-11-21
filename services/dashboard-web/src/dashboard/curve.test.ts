import { describe, expect, it } from "vitest";
import { linePath, smoothPath, straightPath, type XY } from "./curve";

const num = (s: string) => s.match(/-?\d+(?:\.\d+)?/g)!.map(Number);

describe("그래프 선 경로", () => {
  const pts: XY[] = [[0, 100], [10, 40], [20, 60], [30, 10]];
  it("직선: 점마다 L로 잇는다", () => {
    expect(straightPath(pts)).toBe("M0.0 100.0 L10.0 40.0 L20.0 60.0 L30.0 10.0");
    expect(linePath(pts, false)).toBe(straightPath(pts));
  });
  it("점이 둘 이하면 곡선도 직선이다", () => {
    expect(smoothPath([[0, 5], [10, 15]])).toBe("M0.0 5.0 L10.0 15.0");
    expect(smoothPath([[3, 4]])).toBe("M3.0 4.0");
    expect(smoothPath([])).toBe("");
  });
  it("곡선: 모든 점을 그대로 지난다(각 구간의 끝이 원래 점)", () => {
    const d = smoothPath(pts);
    expect(d.startsWith("M0.0 100.0")).toBe(true);
    const segs = d.split("C").slice(1).map((s) => num(s));
    expect(segs).toHaveLength(3);
    segs.forEach((s, i) => expect([s[4], s[5]]).toEqual(pts[i + 1]));
  });
  it("곡선은 점 사이에서 위아래로 튀지 않는다(조절점이 두 끝 값 사이에 있다)", () => {
    const rising: XY[] = [[0, 100], [10, 90], [20, 20], [30, 10], [40, 5]];
    const d = smoothPath(rising);
    d.split("C").slice(1).forEach((s, i) => {
      const [, c1y, , c2y] = num(s);
      const lo = Math.min(rising[i][1], rising[i + 1][1]), hi = Math.max(rising[i][1], rising[i + 1][1]);
      expect(c1y).toBeGreaterThanOrEqual(lo - 0.05);
      expect(c1y).toBeLessThanOrEqual(hi + 0.05);
      expect(c2y).toBeGreaterThanOrEqual(lo - 0.05);
      expect(c2y).toBeLessThanOrEqual(hi + 0.05);
    });
  });
  it("극값(꼭대기·골짜기)에서는 평평하게 지나서 없는 봉우리를 만들지 않는다", () => {
    const peak: XY[] = [[0, 50], [10, 10], [20, 50]]; // 가운데가 가장 높은 값(화면에서는 y가 작다)
    const segs = smoothPath(peak).split("C").slice(1).map((s) => num(s));
    expect(segs[0][3]).toBe(10); // 첫 구간의 두 번째 조절점 높이 = 꼭대기 높이
    expect(segs[1][1]).toBe(10); // 둘째 구간의 첫 조절점 높이 = 꼭대기 높이
  });
});
