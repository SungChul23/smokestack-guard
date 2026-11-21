import { describe, expect, it } from "vitest";
import {
  DEFAULT_W, EDGES, MARGIN, MIN_H, MIN_W, clampRect, defaultRect, maxHeight, maxWidth, moveRect, normalize, nudge,
  resetEdge, resizeByKey, resizeRect, type Rect, type Viewport,
} from "./frameGeometry";

const vp: Viewport = { w: 1200, h: 800 };
const inside = (r: Rect, v: Viewport = vp) => r.x >= 0 && r.y >= 0 && r.x + r.w <= v.w && r.y + r.h <= v.h;

// ── 옛 웹(agent-frame-geometry.test.mjs)에서 옮긴 시험 ─────────────────────────
describe("옛 웹에서 옮긴 규칙", () => {
  it("기본 위치는 이전 고정 모양과 같다(폭 430px, 위·오른쪽·아래 여백 16px)", () => {
    expect(defaultRect(vp)).toEqual({ x: 1200 - 16 - 430, y: 16, w: 430, h: 800 - 32 });
    expect(defaultRect({ w: 500, h: 700 }).w).toBe(430); // 여유가 있으면 430px
    expect(defaultRect({ w: 400, h: 700 }).w).toBe(368); // 좁으면 뷰포트-32px
  });

  it("옮겨도 창 전체가 뷰포트 안에 머문다", () => {
    const start = defaultRect(vp);
    for (const [dx, dy] of [[-5000, -5000], [5000, 5000], [-5000, 5000], [30, -20]]) {
      const r = moveRect(start, dx, dy, vp);
      expect(inside(r)).toBe(true);
      expect(r.w).toBe(start.w);
      expect(r.h).toBe(start.h);
    }
    const short = { x: 700, y: 100, w: 430, h: 400 }; // 높이가 작으면 위아래로도 자유롭게 움직인다
    const free = moveRect(short, -100, 40, vp);
    expect(free.x).toBe(600);
    expect(free.y).toBe(140);
    expect(moveRect(start, 0, 500, vp).y).toBe(vp.h - start.h); // 큰 창은 아래 끝에서 멈춘다
  });

  it("폭 조절: 최소 320, 최대 뷰포트-32, 반대쪽 가장자리는 그대로", () => {
    const start = { x: 400, y: 20, w: 430, h: 700 };
    const right = resizeRect(start, "e", 80, 0, vp);
    expect(right.x).toBe(400);
    expect(right.w).toBe(510);
    const left = resizeRect(start, "w", -80, 0, vp); // 왼쪽 가장자리를 왼쪽으로 80 → 폭 +80
    expect(left.x + left.w).toBe(start.x + start.w); // 오른쪽 끝 고정
    expect(left.w).toBe(510);
    expect(resizeRect(start, "e", -5000, 0, vp).w).toBe(MIN_W);
    expect(resizeRect(start, "w", 5000, 0, vp).w).toBe(MIN_W);
    const big = resizeRect(start, "e", 5000, 0, vp);
    expect(big.x + big.w).toBeLessThanOrEqual(vp.w); // 오른쪽으로 뷰포트를 넘지 않는다
    const bigLeft = resizeRect(start, "w", -5000, 0, vp);
    expect(bigLeft.x).toBeGreaterThanOrEqual(0);
    expect(bigLeft.w).toBeLessThanOrEqual(vp.w - 2 * MARGIN);
  });

  it("clampRect는 범위 밖·빠진·숫자가 아닌 값을 고친다", () => {
    expect(inside(clampRect({ x: -50, y: -50, w: 99999, h: 99999 }, vp))).toBe(true);
    const r = clampRect({ x: 5000, y: 5000, w: 10, h: 10 }, vp);
    expect(inside(r)).toBe(true);
    expect(r.w).toBe(MIN_W);
    expect(r.h).toBe(MIN_H);
    expect(inside(clampRect({}, vp))).toBe(true);
    expect(inside(clampRect({ x: NaN, y: Infinity, w: "a", h: null }, vp))).toBe(true);
  });

  it("저장값 검사: 나쁜 값은 버리고, 뷰포트가 줄어도 좋은 값은 안으로 끌어 넣는다", () => {
    expect(normalize(null, vp)).toBeNull();
    expect(normalize("x", vp)).toBeNull();
    expect(normalize({ x: 1, y: 2, w: "a", h: 4 }, vp)).toBeNull();
    expect(normalize({ x: 1, y: 2, w: 300 }, vp)).toBeNull();
    const small = { w: 700, h: 500 };
    const r = normalize({ x: 800, y: 600, w: 640, h: 700 }, small)!;
    expect(inside(r, small)).toBe(true);
  });

  it("방향키는 정해진 만큼 옮기고 다른 키는 무시한다", () => {
    const start = { x: 300, y: 100, w: 430, h: 600 };
    expect(nudge(start, "ArrowLeft", 16, vp).x).toBe(284);
    expect(nudge(start, "ArrowDown", 16, vp).y).toBe(116);
    expect(nudge(start, "a", 16, vp)).toEqual(start);
    const edge = { x: 0, y: 0, w: 430, h: 600 };
    expect(nudge(edge, "ArrowLeft", 16, vp)).toEqual(edge); // 벽에서 더 안 나간다
  });

  it("아주 작은 뷰포트에서도 NaN이나 음수 크기가 나오지 않는다", () => {
    const tiny = { w: 200, h: 150 };
    const r = clampRect(defaultRect(tiny), tiny);
    for (const v of Object.values(r)) expect(Number.isFinite(v)).toBe(true);
    expect(r.w).toBeGreaterThanOrEqual(MIN_W);
    expect(r.h).toBeGreaterThanOrEqual(MIN_H);
    expect(r.x).toBeGreaterThanOrEqual(0);
    expect(r.y).toBeGreaterThanOrEqual(0);
  });
});

// ── 새로 더한 규칙: 자유 상하 크기 조절, 모서리 조절 ─────────────────────────
describe("상하 크기 조절(새 기능)", () => {
  const start: Rect = { x: 400, y: 100, w: 430, h: 400 };

  it("아래쪽을 끌면 높이가 늘고 위쪽 가장자리는 그대로다", () => {
    const r = resizeRect(start, "s", 0, 120, vp);
    expect(r.y).toBe(100);
    expect(r.h).toBe(520);
    expect(r.w).toBe(430);
    expect(r.x).toBe(400);
  });

  it("위쪽을 끌어 올리면 높이가 늘고 아래쪽 가장자리는 그대로다", () => {
    const r = resizeRect(start, "n", 0, -60, vp);
    expect(r.y + r.h).toBe(start.y + start.h); // 아래 끝 고정
    expect(r.h).toBe(460);
    expect(r.y).toBe(40);
  });

  it("최소 높이 아래로 줄지 않고, 반대쪽 끝은 그대로 둔다", () => {
    const s = resizeRect(start, "s", 0, -5000, vp);
    expect(s.h).toBe(MIN_H);
    expect(s.y).toBe(100);
    const n = resizeRect(start, "n", 0, 5000, vp);
    expect(n.h).toBe(MIN_H);
    expect(n.y + n.h).toBe(500);
  });

  it("뷰포트 밖으로 나가지 않는다(아래는 화면 끝, 위는 화면 맨 위)", () => {
    const s = resizeRect(start, "s", 0, 5000, vp);
    expect(s.y + s.h).toBe(vp.h);
    const n = resizeRect(start, "n", 0, -5000, vp);
    expect(n.y).toBe(0);
    expect(n.y + n.h).toBe(start.y + start.h);
  });

  it("높이는 화면 높이 전체까지도 늘릴 수 있다(위아래 여백이 없어도 된다)", () => {
    const full = resizeRect({ x: 400, y: 0, w: 430, h: 300 }, "s", 0, 9999, vp);
    expect(full.h).toBe(vp.h);
  });

  it("작은 창을 위아래 어디로든 옮길 수 있다", () => {
    const small: Rect = { x: 100, y: 100, w: 330, h: 260 };
    expect(moveRect(small, 0, 9999, vp).y).toBe(vp.h - small.h);
    expect(moveRect(small, 0, -9999, vp).y).toBe(0);
  });
});

describe("모서리 조절(새 기능)", () => {
  const start: Rect = { x: 400, y: 100, w: 430, h: 400 };

  it("오른쪽 아래 모서리: 폭과 높이가 함께 늘고 왼쪽 위는 그대로", () => {
    const r = resizeRect(start, "se", 50, 70, vp);
    expect(r).toEqual({ x: 400, y: 100, w: 480, h: 470 });
  });
  it("왼쪽 위 모서리: 오른쪽 아래가 그대로다", () => {
    const r = resizeRect(start, "nw", -50, -70, vp);
    expect(r.x + r.w).toBe(830);
    expect(r.y + r.h).toBe(500);
    expect(r.w).toBe(480);
    expect(r.h).toBe(470);
  });
  it("오른쪽 위 모서리: 왼쪽 아래가 그대로다", () => {
    const r = resizeRect(start, "ne", 50, -70, vp);
    expect(r.x).toBe(400);
    expect(r.y + r.h).toBe(500);
    expect(r.w).toBe(480);
    expect(r.h).toBe(470);
  });
  it("왼쪽 아래 모서리: 오른쪽 위가 그대로다", () => {
    const r = resizeRect(start, "sw", -50, 70, vp);
    expect(r.x + r.w).toBe(830);
    expect(r.y).toBe(100);
    expect(r.w).toBe(480);
    expect(r.h).toBe(470);
  });
  it("가로 손잡이는 세로를, 세로 손잡이는 가로를 바꾸지 않는다", () => {
    expect(resizeRect(start, "e", 40, 999, vp).h).toBe(400);
    expect(resizeRect(start, "s", 999, 40, vp).w).toBe(430);
  });
  it("어떤 손잡이로 얼마나 끌어도 결과가 뷰포트 안이고 최소 크기 이상이다", () => {
    for (const edge of EDGES) {
      for (const [dx, dy] of [[-9999, -9999], [9999, 9999], [-9999, 9999], [9999, -9999], [0, 0], [13, -7]]) {
        const r = resizeRect(start, edge, dx, dy, vp);
        expect(inside(r), `${edge} ${dx},${dy} → ${JSON.stringify(r)}`).toBe(true);
        expect(r.w).toBeGreaterThanOrEqual(MIN_W);
        expect(r.h).toBeGreaterThanOrEqual(MIN_H);
        for (const v of Object.values(r)) expect(Number.isFinite(v)).toBe(true);
      }
    }
  });
  it("아무 데도 안 움직이면 그대로다", () => {
    for (const edge of EDGES) expect(resizeRect(start, edge, 0, 0, vp)).toEqual(start);
  });
  it("화면 구석에 붙은 창도 모든 손잡이에서 깨지지 않는다", () => {
    const corner: Rect = { x: 0, y: 0, w: MIN_W, h: MIN_H };
    for (const edge of EDGES) {
      for (const [dx, dy] of [[-500, -500], [500, 500]]) expect(inside(resizeRect(corner, edge, dx, dy, vp))).toBe(true);
    }
  });
});

describe("키보드 크기 조절(새 기능)", () => {
  const start: Rect = { x: 400, y: 100, w: 430, h: 400 };
  it("가로 손잡이는 좌우 방향키만, 세로 손잡이는 상하 방향키만 받는다", () => {
    expect(resizeByKey(start, "e", "ArrowRight", 16, vp).w).toBe(446);
    expect(resizeByKey(start, "e", "ArrowDown", 16, vp)).toEqual(start);
    expect(resizeByKey(start, "s", "ArrowDown", 16, vp).h).toBe(416);
    expect(resizeByKey(start, "s", "ArrowRight", 16, vp)).toEqual(start);
  });
  it("위·왼쪽 손잡이는 바깥으로 밀면 커진다(반대쪽 끝 고정)", () => {
    const up = resizeByKey(start, "n", "ArrowUp", 16, vp);
    expect(up.h).toBe(416);
    expect(up.y + up.h).toBe(500);
    const left = resizeByKey(start, "w", "ArrowLeft", 16, vp);
    expect(left.w).toBe(446);
    expect(left.x + left.w).toBe(830);
  });
  it("모서리 손잡이는 가로·세로 방향키를 모두 받는다", () => {
    expect(resizeByKey(start, "se", "ArrowRight", 16, vp).w).toBe(446);
    expect(resizeByKey(start, "se", "ArrowDown", 16, vp).h).toBe(416);
  });
  it("다른 키는 무시한다", () => {
    expect(resizeByKey(start, "se", "a", 16, vp)).toEqual(start);
  });
});

describe("크기 한도", () => {
  it("폭은 뷰포트-32, 높이는 뷰포트 전체가 최대다(좁아도 최소 크기는 지킨다)", () => {
    expect(maxWidth(vp)).toBe(1200 - 32);
    expect(maxHeight(vp)).toBe(800);
    expect(maxWidth({ w: 300, h: 300 })).toBe(MIN_W);
    expect(maxHeight({ w: 300, h: 100 })).toBe(MIN_H);
    expect(DEFAULT_W).toBe(430);
  });
});

describe("두 번 눌러 기본 크기로(새 기능)", () => {
  const big: Rect = { x: 300, y: 50, w: 700, h: 600 }; // 기본(430×736)과 다른 크기
  const d = defaultRect(vp);
  it("오른쪽·아래쪽 손잡이는 폭·높이만 기본으로 되돌리고 위치는 그대로", () => {
    const e = resetEdge(big, "e", vp);
    expect(e).toEqual({ x: 300, y: 50, w: d.w, h: 600 });
    const s = resetEdge(big, "s", vp);
    expect(s).toEqual({ x: 300, y: 50, w: 700, h: Math.min(d.h, vp.h - 50) });
  });
  it("왼쪽·위쪽 손잡이는 반대쪽 가장자리를 그대로 둔다", () => {
    const w = resetEdge(big, "w", vp);
    expect(w.x + w.w).toBe(1000);
    expect(w.w).toBe(d.w);
    const n = resetEdge(big, "n", vp);
    expect(n.y + n.h).toBe(650);
    expect(n.h).toBe(d.h > 650 ? 650 : d.h);
  });
  it("모서리는 두 방향을 함께 되돌린다", () => {
    const se = resetEdge(big, "se", vp);
    expect(se.w).toBe(d.w);
    expect(se.x).toBe(300);
    expect(se.h).toBeLessThanOrEqual(d.h);
  });
  it("결과는 늘 뷰포트 안이다", () => {
    for (const edge of EDGES) expect(inside(resetEdge({ x: 900, y: 700, w: 300, h: 240 }, edge, vp))).toBe(true);
  });
});

