import { describe, expect, it } from "vitest";
import { contourPlan, contourStyle, groupByElevation, isBold, rampColor, RAMP, RAMP_LIGHT, type ContourLine } from "./contours";

const rgb = (c: string) => c.match(/\d+/g)!.map(Number);

describe("고도 색상표", () => {
  it("색상표의 각 고도에서 정확히 그 색이 나온다", () => {
    for (const [e, hex] of RAMP) {
      const want = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
      expect(rgb(rampColor(e))).toEqual(want);
    }
  });
  it("낮은 곳은 녹색 기운, 중간은 올리브·모래빛, 높은 곳은 흙빛·적갈색, 가장 높은 곳은 옅은 회백색이다", () => {
    const [lr, lg] = rgb(rampColor(200)); // 녹색 기운: g가 r보다 크다
    expect(lg).toBeGreaterThan(lr);
    const [mr, mg, mb] = rgb(rampColor(600)); // 모래빛: r·g가 b보다 한참 높다
    expect(mr).toBeGreaterThan(mb + 15);
    expect(mg).toBeGreaterThan(mb + 15);
    const [hr, hg, hb] = rgb(rampColor(1400)); // 적갈색: r이 g·b보다 높다
    expect(hr).toBeGreaterThan(hg + 20);
    expect(hr).toBeGreaterThan(hb + 15);
    expect(Math.min(...rgb(rampColor(1800)))).toBeGreaterThan(180); // 옅은 회백색
  });
  it("모든 색이 차분하다(채도가 낮다)", () => {
    for (const [, hex] of RAMP) {
      const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
      const sat = (Math.max(r, g, b) - Math.min(r, g, b)) / Math.max(r, g, b);
      expect(sat).toBeLessThan(0.3);
    }
  });
  it("색상표 사이의 고도는 보간되고 범위 밖은 양 끝 색이다", () => {
    const mid = rgb(rampColor(500)); // 400(#b4c95a)과 600(#ecd24f)의 중간
    expect(mid[0]).toBeGreaterThan(rgb(rampColor(400))[0]);
    expect(mid[0]).toBeLessThan(rgb(rampColor(600))[0]);
    expect(rampColor(-100)).toBe(rampColor(0));
    expect(rampColor(9000)).toBe(rampColor(1800));
  });
});

describe("등고선 선 모양", () => {
  it("굵은 선은 400m의 배수, 나머지는 얇은 선", () => {
    expect([200, 400, 600, 800, 1200, 1600].map(isBold)).toEqual([false, true, false, true, true, true]);
  });
  it("너무 쨍하지 않다(가장 진한 선도 농도 0.75 이하)", () => {
    expect(contourStyle(1600).alpha).toBeLessThanOrEqual(0.5); // 가장 진한 선도 반투명
    expect(contourStyle(600).alpha).toBeLessThanOrEqual(0.4); // 중간 고도(노란 기운)는 더 연하다
    expect(contourStyle(1600, 1, 0.55).alpha).toBeLessThan(contourStyle(1600).alpha); // 광역에서는 더 은은하게
  });
  it("높을수록 진하고 굵다(같은 종류끼리)", () => {
    const bold = [400, 800, 1200, 1600].map((e) => contourStyle(e));
    for (let i = 1; i < bold.length; i++) {
      expect(bold[i].alpha).toBeGreaterThan(bold[i - 1].alpha);
      expect(bold[i].width).toBeGreaterThan(bold[i - 1].width);
    }
  });
  it("얇은 선은 같은 고도대의 굵은 선보다 흐리고 가늘며, 배율을 낮추면 더 흐려진다", () => {
    const thick = contourStyle(800);
    const thin = contourStyle(1000, 0.9);
    expect(thin.alpha).toBeLessThan(contourStyle(1200).alpha);
    expect(thin.width).toBeLessThan(contourStyle(1200).width);
    expect(contourStyle(1000, 0.5).alpha).toBeLessThan(thin.alpha);
    expect(thick.bold).toBe(true);
    expect(thin.bold).toBe(false);
  });
});

describe("확대 등급별 계획(초기 로딩을 줄인다)", () => {
  it("광역은 가장 성긴 선만 아주 은은하게, 큰 지역 파일은 읽지 않는다(음영은 쓰지 않는다)", () => {
    expect(contourPlan(0)).toMatchObject({ source: "overview", thin: 0 });
    expect(contourPlan(0).bold).toBeLessThan(contourPlan(1).bold);
    expect("shade" in contourPlan(0)).toBe(false);
  });
  it("간략은 굵은 선만(개요 파일), 얇은 선은 없다", () => {
    expect(contourPlan(1)).toMatchObject({ source: "overview", bold: 1, thin: 0 });
  });
  it("지역 파일(200m 간격, 큰 파일)은 상세 이상에서만 읽는다", () => {
    expect(contourPlan(0).source).toBe("overview");
    expect(contourPlan(1).source).toBe("overview");
    expect(contourPlan(2).source).toBe("regions");
    expect(contourPlan(3).source).toBe("regions");
  });
  it("확대할수록 얇은 선이 뚜렷해진다", () => {
    expect(contourPlan(2).thin).toBeGreaterThan(contourPlan(1).thin);
    expect(contourPlan(3).thin).toBeGreaterThan(contourPlan(2).thin);
  });
});

describe("고도별 묶기", () => {
  const line = (e: number): ContourLine => ({ e, b: [0, 0, 1, 1], path: null });
  it("낮은 고도부터 정렬되어 높은 선이 위에 그려진다", () => {
    const g = groupByElevation([line(800), line(200), line(800), line(400)]);
    expect(g.map(([e]) => e)).toEqual([200, 400, 800]);
    expect(g[2][1]).toHaveLength(2);
  });
});

describe("라이트 테마 등고선", () => {
  it("색상표는 같은 고도 단계를 가지고, 밝은 땅(거의 흰색) 위에서 보이도록 모두 충분히 어둡다", () => {
    expect(RAMP_LIGHT.map(([e]) => e)).toEqual(RAMP.map(([e]) => e));
    const lum = (c: string) => { const m = c.match(/\d+/g)!.map(Number); return 0.299 * m[0] + 0.587 * m[1] + 0.114 * m[2]; };
    for (const e of [0, 200, 400, 600, 800, 1000, 1400, 1800]) expect(lum(rampColor(e, true))).toBeLessThan(150);
  });
  it("라이트에서는 선이 조금 더 진하다(같은 고도·같은 굵기)", () => {
    const d = contourStyle(800), l = contourStyle(800, 1, 1, true);
    expect(l.alpha).toBeGreaterThan(d.alpha);
    expect(l.width).toBe(d.width);
    expect(l.color).toBe(rampColor(800, true));
  });
  it("기본(다크)은 그대로다", () => {
    expect(contourStyle(600).color).toBe(rampColor(600, false));
  });
});

