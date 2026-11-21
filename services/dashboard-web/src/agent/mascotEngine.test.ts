// 옛 웹(mascot-engine.test.mjs)의 시험을 그대로 옮겼다. 난수를 고정해 결정적으로 시험한다.
import { describe, expect, it } from "vitest";
import * as E from "./mascotEngine";
import type { Env, MascotState, Rng, Surface } from "./mascotEngine";

const env: Env = { w: 800, h: 600, size: 64 };
const always = (v: number): Rng => () => v;
const noTurn = always(0.99); // turnChance(0.3)보다 커서 모서리에서 돌아서지 않는다
const inside = (s: MascotState, e: Env = env) => s.x >= -1e-9 && s.y >= -1e-9 && s.x <= e.w - e.size + 1e-9 && s.y <= e.h - e.size + 1e-9;
const run = (s: MascotState, seconds: number, e: Env = env, rng: Rng = noTurn, dt = 1 / 60) => {
  for (let t = 0; t < seconds; t += dt) E.step(s, dt, e, rng);
  return s;
};
const walking = (surface: Surface, s: number, dir: number): MascotState => {
  const m = E.create(env, noTurn, { surface, s, dir });
  m.mode = E.MODE_OF[surface];
  m.timer = 1e9;
  return m;
};

describe("마스코트 엔진(옛 웹 시험)", () => {
  it("바닥 걷기: 발이 바닥에 붙고 속도만큼 움직인다", () => {
    const m = walking("FLOOR", 100, 1);
    E.step(m, 0.1, env, noTurn);
    expect(m.surface).toBe("FLOOR");
    expect(m.y).toBe(env.h - env.size);
    expect(Math.abs(m.x - (100 + E.CONFIG.speed * 0.1))).toBeLessThan(1e-9);
  });

  it("바닥 왼쪽 끝에서 위치가 튀지 않고 왼쪽 벽을 타고 오른다", () => {
    const m = walking("FLOOR", 2, -1);
    E.step(m, 0.1, env, noTurn);
    expect(m.surface).toBe("LEFT_WALL");
    expect(m.mode).toBe("CLIMB");
    expect(m.dir).toBe(-1); // 위로
    expect(m.x).toBe(0);
    expect(m.y).toBeLessThan(env.h - env.size);
    expect(m.y).toBeGreaterThan(env.h - env.size - 10); // 모서리 바로 위에서 이어간다
  });

  it("한 바퀴: 바닥 → 왼쪽 벽 → 천장 → 오른쪽 벽 → 바닥 순서로 돈다", () => {
    const m = walking("FLOOR", 300, -1);
    const seen: Surface[] = [m.surface];
    for (let t = 0; t < 120; t += 1 / 60) {
      E.step(m, 1 / 60, env, noTurn);
      m.timer = 1e9;
      if (m.mode === "IDLE") m.mode = E.MODE_OF[m.surface];
      if (seen[seen.length - 1] !== m.surface) seen.push(m.surface);
      expect(inside(m), `left the screen at ${t}: ${m.x},${m.y}`).toBe(true);
      if (seen.length >= 6) break;
    }
    expect(seen.slice(0, 5)).toEqual(["FLOOR", "LEFT_WALL", "CEILING", "RIGHT_WALL", "FLOOR"]);
  });

  it("모든 표면에서 닿는 변이 화면 가장자리에 붙어 있다", () => {
    const edge: Record<Surface, (m: MascotState) => boolean> = {
      FLOOR: (m) => m.y === env.h - env.size, CEILING: (m) => m.y === 0,
      LEFT_WALL: (m) => m.x === 0, RIGHT_WALL: (m) => m.x === env.w - env.size,
    };
    const m = walking("FLOOR", 300, -1);
    for (let t = 0; t < 90; t += 1 / 60) {
      E.step(m, 1 / 60, env, noTurn);
      m.timer = 1e9;
      if (m.mode === "IDLE") m.mode = E.MODE_OF[m.surface];
      expect(edge[m.surface](m), `${m.surface} edge broken at ${m.x},${m.y}`).toBe(true);
    }
  });

  it("주사위가 그렇게 나오면 모서리에서 돌아선다", () => {
    const m = walking("FLOOR", 1, -1);
    E.step(m, 0.1, env, always(0)); // 0 < turnChance
    expect(m.surface).toBe("FLOOR");
    expect(m.dir).toBe(1);
  });

  it("몸은 가까운 쪽으로 돌고 새 표면에서 똑바로 선다", () => {
    const m = walking("CEILING", env.w - env.size - 1, 1);
    let last = m.rot, maxJump = 0;
    for (let i = 0; i < 60; i++) {
      E.step(m, 1 / 60, env, noTurn);
      m.timer = 1e9;
      if (m.mode === "IDLE") m.mode = E.MODE_OF[m.surface];
      const d = Math.abs(((m.rot - last + 540) % 360) - 180);
      maxJump = Math.max(maxJump, d);
      last = m.rot;
    }
    expect(m.surface).toBe("RIGHT_WALL");
    expect(Math.abs(Math.abs(m.rot) - 90)).toBeLessThan(1e-6); // 오른쪽 벽: -90도
    expect(maxJump).toBeLessThanOrEqual(E.CONFIG.rotSpeed / 60 + 1e-6);
  });

  it("앞으로 걷는 모양이 되도록 좌우를 뒤집는다", () => {
    expect(E.facing({ dir: 1, surface: "FLOOR" })).toBe(1);
    expect(E.facing({ dir: 1, surface: "CEILING" })).toBe(-1);
    expect(E.facing({ dir: -1, surface: "RIGHT_WALL" })).toBe(1);
  });

  it("가만히 쉬다가 다시 움직이기 시작한다", () => {
    const m = E.create(env, always(0.5), { surface: "FLOOR", s: 100 });
    expect(m.mode).toBe("IDLE");
    run(m, 5, env, noTurn);
    expect(["WALK", "IDLE"]).toContain(m.mode);
    expect(m.s).not.toBe(100);
  });

  it("움직이지 않고 누르면 이전 걷기를 되살리고 click을 알린다", () => {
    const m = walking("LEFT_WALL", 200, -1);
    const prev = { surface: m.surface, s: m.s, dir: m.dir, mode: m.mode };
    E.press(m, { x: m.x + 10, y: m.y + 10 }, 0);
    E.dragTo(m, { x: m.x + 12, y: m.y + 11 }, 16, env); // 문턱(6px) 안쪽
    expect(E.release(m, 30, env)).toBe("click");
    expect({ surface: m.surface, s: m.s, dir: m.dir, mode: m.mode }).toEqual(prev);
  });

  it("끌면 포인터를 따라가고, 잡은 자리를 유지하며, 화면 안에 머문다", () => {
    const m = walking("FLOOR", 300, 1);
    E.press(m, { x: m.x + 20, y: m.y + 30 }, 0);
    E.dragTo(m, { x: 400, y: 300 }, 16, env);
    expect(m.mode).toBe("DRAG");
    expect(Math.abs(m.x - 380)).toBeLessThan(1e-9);
    expect(Math.abs(m.y - 270)).toBeLessThan(1e-9);
    E.dragTo(m, { x: -500, y: -500 }, 32, env);
    expect(m.x).toBe(0);
    expect(m.y).toBe(0);
    E.dragTo(m, { x: 5000, y: 5000 }, 48, env);
    expect(m.x).toBe(env.w - env.size);
    expect(m.y).toBe(env.h - env.size);
  });

  it("허공에서 놓으면 중력으로 떨어져 바닥에 내려앉는다", () => {
    const m = walking("FLOOR", 300, 1);
    E.press(m, { x: m.x, y: m.y }, 0);
    E.dragTo(m, { x: 400, y: 100 }, 16, env);
    E.dragTo(m, { x: 400, y: 100 }, 400, env); // 멈춘 채로 놓는다
    expect(E.release(m, 500, env)).toBe("drop");
    expect(m.mode).toBe("FALL");
    expect(m.vx).toBe(0);
    const y0 = m.y;
    E.step(m, 0.05, env, noTurn);
    expect(m.y).toBeGreaterThan(y0);
    expect(m.vy).toBeGreaterThan(0);
    run(m, 3, env, noTurn);
    expect(m.y).toBe(env.h - env.size);
    expect(m.surface).toBe("FLOOR");
    expect(["LAND", "IDLE", "WALK"]).toContain(m.mode);
    expect(m.vy).toBe(0);
  });

  it("착지하면 쉬거나 걷는다", () => {
    const m = walking("FLOOR", 300, 1);
    m.mode = "FALL"; m.y = env.h - env.size - 5; m.vy = 500; m.vx = 0; m.x = 300;
    E.step(m, 0.05, env, noTurn);
    expect(m.mode).toBe("LAND");
    run(m, 1, env, noTurn);
    expect(["IDLE", "WALK"]).toContain(m.mode);
  });

  it("던지면 벽에 튕길 수 있지만 화면을 벗어나지 않는다", () => {
    const m = walking("FLOOR", 300, 1);
    E.press(m, { x: m.x, y: m.y }, 0);
    E.dragTo(m, { x: 500, y: 100 }, 16, env);
    E.dragTo(m, { x: 700, y: 120 }, 33, env); // 오른쪽으로 빠르게
    E.release(m, 40, env);
    expect(m.vx).toBeGreaterThan(0);
    for (let t = 0; t < 4; t += 1 / 60) {
      E.step(m, 1 / 60, env, noTurn);
      expect(inside(m), `${m.x},${m.y}`).toBe(true);
    }
    expect(m.y).toBe(env.h - env.size);
  });

  it("아주 큰 시간 간격도 바닥을 뚫고 지나가지 않는다", () => {
    const m = walking("FLOOR", 300, 1);
    m.mode = "FALL"; m.y = 100; m.vy = 3000; m.x = 300;
    E.step(m, 5, env, noTurn); // 탭이 오래 숨었다가 돌아온 경우
    expect(inside(m)).toBe(true); // 한 번에 0.1초까지만 계산해 튀지 않는다
    expect(m.y).toBeLessThan(env.h - env.size);
    run(m, 2, env, noTurn);
    expect(m.y).toBe(env.h - env.size);
  });

  it("창 크기가 바뀌면 안으로 끌어 넣고 표면에 다시 붙는다", () => {
    const m = walking("RIGHT_WALL", 500, 1);
    const small: Env = { w: 400, h: 300, size: 64 };
    E.reflow(m, small);
    expect(m.x).toBe(small.w - small.size);
    expect(inside(m, small)).toBe(true);
    const f = walking("FLOOR", 700, 1);
    E.reflow(f, small);
    expect(f.y).toBe(small.h - small.size);
    expect(inside(f, small)).toBe(true);
    const d = walking("FLOOR", 700, 1);
    E.press(d, { x: d.x, y: d.y }, 0);
    E.dragTo(d, { x: 790, y: 590 }, 16, env);
    E.reflow(d, small);
    expect(inside(d, small)).toBe(true);
  });

  it("아주 작은 창에서도 계산이 깨지지 않는다", () => {
    const tiny: Env = { w: 40, h: 40, size: 64 };
    const m = E.create(tiny, noTurn);
    run(m, 5, tiny, noTurn);
    expect(Number.isFinite(m.x) && Number.isFinite(m.y)).toBe(true);
  });

  it("pointercancel이면 던지지 않고 안전하게 떨어뜨린다", () => {
    const m = walking("FLOOR", 300, 1);
    E.press(m, { x: m.x, y: m.y }, 0);
    E.dragTo(m, { x: 500, y: 200 }, 16, env);
    E.cancel(m);
    expect(m.mode).toBe("FALL");
    expect(m.vx).toBe(0);
    run(m, 3, env, noTurn);
    expect(m.y).toBe(env.h - env.size);
  });

  it("다시 나타나면 런처가 있던 우하단에서 시작한다", () => {
    const m = walking("CEILING", 100, 1);
    E.respawn(m, env);
    expect(m.surface).toBe("FLOOR");
    expect(m.y).toBe(env.h - env.size);
    expect(m.x).toBeGreaterThan(env.w - env.size - 40);
    expect(m.dir).toBe(-1);
  });

  it("오래 돌려도(10분) 화면을 벗어나지 않는다", () => {
    let seed = 7;
    const rng: Rng = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    const m = E.create(env, rng);
    for (let i = 0; i < 60 * 600; i++) {
      E.step(m, 1 / 60, env, rng);
      if (!inside(m)) throw new Error(`step ${i}: ${m.surface} ${m.x},${m.y}`);
    }
  });
});
