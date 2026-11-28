// 마스코트 이동 엔진(순수 로직). DOM·타이머·전역 상태를 쓰지 않는다. 옛 웹의 mascot-engine.js를 그대로 옮겼다.
// 좌표·표면·상태·속도·충돌만으로 움직인다. 물리 엔진은 쓰지 않는다.
// 위치는 상자의 왼쪽 위 좌표(x, y)이고, 표면에 닿는 변이 화면 가장자리에 붙는다.

export const CONFIG = {
  speed: 70, // 바닥·천장 이동 속도(px/s)
  climbSpeed: 60, // 벽 이동 속도(px/s)
  gravity: 2400, // 낙하 가속도(px/s²)
  rotSpeed: 540, // 표면이 바뀔 때 몸이 돌아가는 속도(도/s)
  idleMin: 0.8,
  idleMax: 2.6,
  moveMin: 2.5,
  moveMax: 7,
  landTime: 0.22,
  turnChance: 0.3, // 모서리에 닿았을 때 돌아서 되돌아갈 확률
  throwScale: 0.6, // 놓는 순간 마우스 속도를 낙하 속도로 옮기는 비율
  maxThrow: 1800,
  bounce: 0.25, // 낙하 중 벽·천장에 부딪힐 때 남는 속도 비율
  maxDt: 0.1, // 한 번에 계산하는 최대 시간(탭 복귀 때 튀지 않게)
} as const;

export type Surface = "FLOOR" | "LEFT_WALL" | "CEILING" | "RIGHT_WALL";
export type Mode = "IDLE" | "WALK" | "CLIMB" | "HANG" | "DRAG" | "FALL" | "LAND";
export type Rng = () => number;
export interface Env { w: number; h: number; size: number }
export interface Point { x: number; y: number }

export interface PressInfo {
  surface: Surface; s: number; dir: number; mode: Mode; timer: number;
  dx: number; dy: number; px: number; py: number;
}
export interface DragInfo { vx: number; vy: number; t: number; x: number; y: number; moved: boolean }

export interface MascotState {
  surface: Surface;
  s: number; // 표면을 따라 간 거리
  dir: number; // 표면 위 진행 방향(+1/-1)
  mode: Mode;
  timer: number;
  x: number; y: number; vx: number; vy: number;
  rot: number; // 몸이 돌아간 각도(도)
  drag: DragInfo | null;
  press: PressInfo | null;
}

export const ROT: Record<Surface, number> = { FLOOR: 0, LEFT_WALL: 90, CEILING: 180, RIGHT_WALL: -90 };
/** 표면 위에서 "앞"(몸의 +x)이 가리키는 화면 방향과 s 증가 방향의 부호 */
export const FACE: Record<Surface, number> = { FLOOR: 1, LEFT_WALL: 1, CEILING: -1, RIGHT_WALL: -1 };
export const MODE_OF: Record<Surface, Mode> = { FLOOR: "WALK", LEFT_WALL: "CLIMB", CEILING: "HANG", RIGHT_WALL: "CLIMB" };

const clamp = (v: number, lo: number, hi: number) => (v < lo ? lo : v > hi ? hi : v);
const between = (rng: Rng, lo: number, hi: number) => lo + (hi - lo) * rng();
const norm = (deg: number) => ((((deg + 180) % 360) + 360) % 360) - 180;

export function maxS(surface: Surface, env: Env): number {
  const len = surface === "FLOOR" || surface === "CEILING" ? env.w - env.size : env.h - env.size;
  return Math.max(0, len);
}

function place(state: MascotState, env: Env): void {
  const s = clamp(state.s, 0, maxS(state.surface, env));
  state.s = s;
  if (state.surface === "FLOOR") { state.x = s; state.y = Math.max(0, env.h - env.size); }
  else if (state.surface === "CEILING") { state.x = s; state.y = 0; }
  else if (state.surface === "LEFT_WALL") { state.x = 0; state.y = s; }
  else { state.x = Math.max(0, env.w - env.size); state.y = s; }
}

export function create(env: Env, rng: Rng, options: { surface?: Surface; s?: number; dir?: number } = {}): MascotState {
  const state: MascotState = {
    surface: options.surface || "FLOOR",
    s: 0, dir: rng() < 0.5 ? -1 : 1,
    mode: "IDLE", timer: 0,
    x: 0, y: 0, vx: 0, vy: 0,
    rot: 0, drag: null, press: null,
  };
  state.s = options.s !== undefined ? options.s : rng() * maxS(state.surface, env);
  if (options.dir) state.dir = options.dir;
  state.rot = ROT[state.surface];
  state.timer = between(rng, CONFIG.idleMin, CONFIG.idleMax);
  place(state, env);
  return state;
}

/** 모서리: 같은 점에서 이어지는 다음 표면으로 옮긴다(좌표는 끊기지 않는다) */
function corner(state: MascotState, end: "min" | "max", env: Env, rng: Rng): void {
  if (rng() < CONFIG.turnChance) {
    state.dir = -state.dir;
    state.s = end === "min" ? 0 : maxS(state.surface, env);
    return;
  }
  const sf = state.surface;
  if (sf === "FLOOR") {
    state.surface = end === "min" ? "LEFT_WALL" : "RIGHT_WALL";
    state.s = maxS(state.surface, env); state.dir = -1;
  } else if (sf === "LEFT_WALL") {
    if (end === "min") { state.surface = "CEILING"; state.s = 0; state.dir = 1; }
    else { state.surface = "FLOOR"; state.s = 0; state.dir = 1; }
  } else if (sf === "CEILING") {
    state.surface = end === "min" ? "LEFT_WALL" : "RIGHT_WALL";
    state.s = 0; state.dir = 1;
  } else if (end === "min") { state.surface = "CEILING"; state.s = maxS("CEILING", env); state.dir = -1; }
  else { state.surface = "FLOOR"; state.s = maxS("FLOOR", env); state.dir = -1; }
  state.mode = MODE_OF[state.surface];
}

function easeRotation(state: MascotState, dt: number): void {
  const upright = state.mode === "DRAG" || state.mode === "FALL";
  const target = upright ? 0 : ROT[state.surface];
  const delta = norm(target - state.rot);
  const maxStep = CONFIG.rotSpeed * dt;
  state.rot = norm(state.rot + clamp(delta, -maxStep, maxStep));
}

function fall(state: MascotState, dt: number, env: Env): void {
  const xmax = Math.max(0, env.w - env.size), ymax = Math.max(0, env.h - env.size);
  state.vy += CONFIG.gravity * dt;
  state.x += state.vx * dt;
  state.y += state.vy * dt;
  if (state.x < 0) { state.x = 0; state.vx = Math.abs(state.vx) * CONFIG.bounce; }
  if (state.x > xmax) { state.x = xmax; state.vx = -Math.abs(state.vx) * CONFIG.bounce; }
  if (state.y < 0) { state.y = 0; state.vy = Math.abs(state.vy) * CONFIG.bounce; }
  if (state.y >= ymax) {
    state.y = ymax; state.vx = 0; state.vy = 0;
    state.surface = "FLOOR"; state.s = state.x;
    state.mode = "LAND"; state.timer = CONFIG.landTime;
  }
}

function move(state: MascotState, dt: number, env: Env, rng: Rng): void {
  const speed = state.surface === "FLOOR" || state.surface === "CEILING" ? CONFIG.speed : CONFIG.climbSpeed;
  const len = maxS(state.surface, env);
  const s = state.s + state.dir * speed * dt;
  if (s <= 0 || s >= len) {
    const end = s <= 0 ? "min" : "max";
    const over = end === "min" ? -s : s - len; // 모서리를 넘은 거리는 다음 표면에서 이어서 간다
    state.s = end === "min" ? 0 : len;
    corner(state, end, env, rng);
    const speed2 = state.surface === "FLOOR" || state.surface === "CEILING" ? CONFIG.speed : CONFIG.climbSpeed;
    state.s = clamp(state.s + state.dir * Math.min(over, speed2 * dt), 0, maxS(state.surface, env));
  } else {
    state.s = s;
  }
  state.timer -= dt;
  if (state.timer <= 0) {
    state.mode = "IDLE";
    state.timer = between(rng, CONFIG.idleMin, CONFIG.idleMax);
    if (rng() < 0.4) state.dir = -state.dir;
  }
  place(state, env);
}

export function step(state: MascotState, dtIn: number, env: Env, rng: Rng): MascotState {
  const dt = clamp(dtIn, 0, CONFIG.maxDt);
  if (state.mode === "DRAG") { easeRotation(state, dt); return state; }
  if (state.mode === "FALL") { fall(state, dt, env); easeRotation(state, dt); return state; }
  if (state.mode === "LAND") {
    state.timer -= dt;
    if (state.timer <= 0) {
      if (rng() < 0.5) { state.mode = "WALK"; state.timer = between(rng, CONFIG.moveMin, CONFIG.moveMax); }
      else { state.mode = "IDLE"; state.timer = between(rng, CONFIG.idleMin, CONFIG.idleMax); }
    }
    place(state, env);
  } else if (state.mode === "IDLE") {
    state.timer -= dt;
    if (state.timer <= 0) {
      state.mode = MODE_OF[state.surface];
      state.timer = between(rng, CONFIG.moveMin, CONFIG.moveMax);
    }
    place(state, env);
  } else {
    move(state, dt, env, rng);
  }
  easeRotation(state, dt);
  return state;
}

// ── 마우스로 잡기 ──────────────────────────────────────────────
// 누르는 순간 멈추고(press), 일정 거리 이상 움직이면 드래그, 그대로 떼면 클릭이다.
export function press(state: MascotState, point: Point, t: number): MascotState {
  state.press = {
    surface: state.surface, s: state.s, dir: state.dir, mode: state.mode, timer: state.timer,
    dx: point.x - state.x, dy: point.y - state.y, px: point.x, py: point.y,
  };
  state.mode = "DRAG";
  state.drag = { vx: 0, vy: 0, t, x: state.x, y: state.y, moved: false };
  state.vx = 0; state.vy = 0;
  return state;
}

export function dragTo(state: MascotState, point: Point, t: number, env: Env, threshold = 6): MascotState {
  if (!state.drag || !state.press) return state;
  const dist = Math.hypot(point.x - state.press.px, point.y - state.press.py);
  if (!state.drag.moved && dist < threshold) return state; // 아직 클릭 범위
  state.drag.moved = true;
  const nx = clamp(point.x - state.press.dx, 0, Math.max(0, env.w - env.size));
  const ny = clamp(point.y - state.press.dy, 0, Math.max(0, env.h - env.size));
  const dt = (t - state.drag.t) / 1000;
  if (dt > 0) {
    state.drag.vx = 0.6 * state.drag.vx + 0.4 * ((nx - state.x) / dt);
    state.drag.vy = 0.6 * state.drag.vy + 0.4 * ((ny - state.y) / dt);
  }
  state.drag.t = t;
  state.x = nx; state.y = ny;
  return state;
}

/** 손을 뗀다. 돌려주는 값: 'click'(거의 안 움직임) | 'drop'(놓음 → 낙하) */
export function release(state: MascotState, t: number, env: Env): "click" | "drop" {
  const d = state.drag, p = state.press;
  if (!d || !p) return "drop";
  if (!d.moved) { // 클릭: 누르기 전 상태로 되돌린다
    state.surface = p.surface; state.s = p.s; state.dir = p.dir; state.mode = p.mode; state.timer = p.timer;
    state.drag = null; state.press = null;
    place(state, env);
    return "click";
  }
  const stale = t - d.t > 80; // 멈췄다가 놓으면 던지지 않는다
  state.vx = stale ? 0 : clamp(d.vx * CONFIG.throwScale, -CONFIG.maxThrow, CONFIG.maxThrow);
  state.vy = stale ? 0 : clamp(d.vy * CONFIG.throwScale, -CONFIG.maxThrow, CONFIG.maxThrow);
  state.mode = "FALL";
  state.drag = null; state.press = null;
  return "drop";
}

/** 포인터가 취소되면(pointercancel) 던지지 않고 안전하게 떨어뜨린다 */
export function cancel(state: MascotState): void {
  if (state.press && state.drag && !state.drag.moved) {
    const p = state.press;
    state.surface = p.surface; state.s = p.s; state.dir = p.dir; state.mode = p.mode; state.timer = p.timer;
  } else {
    state.mode = "FALL"; state.vx = 0; state.vy = 0;
  }
  state.drag = null; state.press = null;
}

/** 창 크기가 바뀌면 경계를 다시 계산한다 */
export function reflow(state: MascotState, env: Env): MascotState {
  if (state.mode === "DRAG" || state.mode === "FALL") {
    state.x = clamp(state.x, 0, Math.max(0, env.w - env.size));
    state.y = clamp(state.y, 0, Math.max(0, env.h - env.size));
  } else {
    place(state, env);
  }
  return state;
}

/** 다시 나타날 때(에이전트 창을 닫았을 때): 우하단 런처 자리에서 시작한다 */
export function respawn(state: MascotState, env: Env, margin = 22): MascotState {
  state.surface = "FLOOR"; state.mode = "IDLE"; state.dir = -1;
  state.s = Math.max(0, env.w - env.size - margin);
  state.timer = CONFIG.idleMin; state.vx = 0; state.vy = 0;
  state.drag = null; state.press = null; state.rot = 0;
  place(state, env);
  return state;
}

/** 몸을 좌우로 뒤집을 방향(+1/-1): 늘 앞으로 걸어가는 모양이 되게 한다 */
export function facing(state: Pick<MascotState, "dir" | "surface">): number {
  return state.dir * FACE[state.surface];
}
