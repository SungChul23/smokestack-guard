// 지도 계산(순수 함수). 그리기와 분리해 두어 시험한다. 점이 많아도 한 번에 훑는 평평한 배열과 격자만 쓴다.

/** 옛 지도·등고선과 같은 웹 메르카토르 세계 좌표(세계 폭 256). 이 좌표에서 "축척"은 세계 1칸이 몇 px인지다 */
export const WORLD = 256;
/**
 * 확대 한도. 옛 지도는 4096(1px ≈ 29m)이었지만, 산업단지에는 그 확대로도 30px 안에 붙어 있는 사업장이 많아
 * (실측 기준 722쌍) 묶음이 풀리지 않았다. 8배 더 깊이(1px ≈ 3.6m) 들어갈 수 있게 한다.
 */
export const MIN_SCALE = 20;
export const MAX_SCALE = 32768;
/** 지도 단계: 축척 180 미만 전국, 700 이상 사업장, 그 사이 지역 */
export type Stage = "national" | "region" | "site";
export function stageOf(scale: number): Stage {
  return scale < 180 ? "national" : scale >= 700 ? "site" : "region";
}

/**
 * 확대 등급 4단계(0이 가장 넓게 본 상태). 등고선이 얼마나 자세히 나오는지, 묶음 반경이 얼마나 되는지가 이 등급을 따른다.
 *  0 광역(축척 180 미만) · 1 간략(180~450) · 2 상세(450~1400) · 3 최대 상세(1400 이상)
 */
export type ZoomGrade = 0 | 1 | 2 | 3;
export const GRADE_SCALES = [180, 450, 1400] as const;
export function zoomGrade(scale: number): ZoomGrade {
  return scale < GRADE_SCALES[0] ? 0 : scale < GRADE_SCALES[1] ? 1 : scale < GRADE_SCALES[2] ? 2 : 3;
}

/** 묶기 반경(px). 많이 펼쳐 볼수록 작게 묶는다(전국 100px → 최대 상세 60px → 더 깊이 확대하면 26px까지) */
const RADIUS_BY_GRADE = [100, 86, 72] as const;
export const MIN_SEPARATION_PX = 26;
export function clusterRadius(scale: number): number {
  const g = zoomGrade(scale);
  if (g === 3) {
    // 최대 상세(1400 이상)에서 60px에서 시작해, 깊이 들어갈수록 줄여 가까이 붙은 사업장이 풀리게 한다
    return Math.max(MIN_SEPARATION_PX, 60 * Math.sqrt(GRADE_SCALES[2] / scale));
  }
  return RADIUS_BY_GRADE[g];
}

/**
 * 묶음 구성원이 확대 한도까지 들어가면 서로 갈라질 수 있는지. 퍼진 범위(세계 좌표)가 한도 배율에서
 * 최소 간격(px)보다 작으면 아무리 확대해도 안 갈라지므로 목록으로 고르게 해야 한다.
 */
export function canSeparate(b: Bounds, maxScale = MAX_SCALE, minPx = MIN_SEPARATION_PX): boolean {
  return Math.max(b.maxX - b.minX, b.maxY - b.minY) * maxScale >= minPx;
}

export interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}
export interface View {
  scale: number; // 투영 좌표 1 → 화면 px
  ox: number;
  oy: number;
}

export function project(lon: number, lat: number): [number, number] {
  const rad = (lat * Math.PI) / 180;
  return [((lon + 180) / 360) * WORLD, ((1 - Math.asinh(Math.tan(rad)) / Math.PI) / 2) * WORLD];
}

export function boundsOf(points: Array<[number, number]>): Bounds | null {
  if (points.length === 0) return null;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const [x, y] of points) {
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
  }
  return { minX, minY, maxX, maxY };
}

/** 경계 상자가 화면(w×h)에 여백(pad)을 두고 꽉 차는 보기 */
export function fitView(b: Bounds, w: number, h: number, pad = 24, maxScale = MAX_SCALE): View {
  const bw = Math.max(b.maxX - b.minX, 1e-6);
  const bh = Math.max(b.maxY - b.minY, 1e-6);
  const scale = Math.min((w - pad * 2) / bw, (h - pad * 2) / bh, maxScale);
  return {
    scale,
    ox: (w - bw * scale) / 2 - b.minX * scale,
    oy: (h - bh * scale) / 2 - b.minY * scale,
  };
}

export function toScreen(view: View, x: number, y: number): [number, number] {
  return [x * view.scale + view.ox, y * view.scale + view.oy];
}

/** 가장 많이 축소할 수 있는 배율: 전체 범위가 화면에 여백(pad)을 두고 꽉 차는 배율(전국 보기와 같다). 이보다 더 작게 줄이지 않는다 */
export function minScaleFor(b: Bounds, w: number, h: number, pad = 28): number {
  return fitView(b, w, h, pad).scale;
}

/**
 * 보기를 지도 범위 안으로 붙든다: 배율은 minScale 이상으로, 이동은 지도 가장자리가 화면 안쪽 slack(기본 25%)보다 더 들어오지 않게.
 * 지도가 화면보다 작으면(축소 한계 근처) 가운데에 고정하고, 화면보다 커질수록 이동 여유가 slack까지 서서히 늘어난다. 그래서 지도를 화면 밖으로 밀어내거나 점처럼 작게 줄일 수 없다.
 */
export function clampView(view: View, b: Bounds, w: number, h: number, minScale: number, slack = 0.25): View {
  const scale = Math.max(view.scale, minScale);
  const k = scale / view.scale;
  // 배율이 올라갔다면 화면 중앙을 기준으로 맞춘다
  const ox0 = k === 1 ? view.ox : w / 2 - (w / 2 - view.ox) * k;
  const oy0 = k === 1 ? view.oy : h / 2 - (h / 2 - view.oy) * k;
  const axis = (o: number, min: number, max: number, size: number) => {
    // 화면 밖으로 내보낼 수 있는 여유: 지도가 화면보다 클수록(확대할수록) 최대 slack까지 늘어난다. 지도가 화면보다 작으면 0이라 가운데에 고정된다.
    const over = Math.min(size * slack, Math.max(0, (max - min) * scale - size));
    const lo = size - over - max * scale; // 오른쪽(아래) 가장자리가 화면 안쪽 over보다 들어오지 못한다
    const hi = over - min * scale; // 왼쪽(위) 가장자리도 마찬가지
    return lo > hi ? (lo + hi) / 2 : Math.min(hi, Math.max(lo, o));
  };
  return { scale, ox: axis(ox0, b.minX, b.maxX, w), oy: axis(oy0, b.minY, b.maxY, h) };
}

/** 화면 좌표를 중심으로 배율을 바꾼 보기(휠 확대용) */
export function zoomAt(view: View, sx: number, sy: number, factor: number, min: number, max: number): View {
  const scale = Math.min(max, Math.max(min, view.scale * factor));
  const k = scale / view.scale;
  return { scale, ox: sx - (sx - view.ox) * k, oy: sy - (sy - view.oy) * k };
}

export const LEVEL_RANK = { ok: 0, caution: 1, warn: 2, risk: 3, exceed: 4 } as const;
/** 공백(null)은 어느 단계보다 낮다. 묶음의 대표 단계를 고를 때 공백이 단계를 가리지 않게 한다 */
export function rankOf(level: keyof typeof LEVEL_RANK | null): number {
  return level === null ? -1 : LEVEL_RANK[level];
}

export interface Cluster {
  x: number; // 화면 좌표(구성원 평균)
  y: number;
  count: number;
  /** 구성원 중 가장 높은 단계의 순번(공백만 있으면 -1) */
  maxRank: number;
  /** 구성원 인덱스 */
  members: number[];
}

/**
 * 화면 격자로 점을 묶는다. 점마다 한 번만 훑는다(O(n)).
 * xs, ys는 화면 좌표, ranks는 점별 단계 순번. 화면 밖(여백 밖) 점은 건너뛴다.
 */
export function clusterGrid(
  xs: Float32Array,
  ys: Float32Array,
  ranks: Int8Array,
  cell: number,
  width: number,
  height: number,
): Cluster[] {
  const cols = Math.ceil(width / cell) + 2;
  const cells = new Map<number, Cluster>();
  for (let i = 0; i < xs.length; i++) {
    const x = xs[i], y = ys[i];
    if (x < -cell || y < -cell || x > width + cell || y > height + cell) continue;
    const id = (Math.floor(y / cell) + 1) * cols + (Math.floor(x / cell) + 1);
    const c = cells.get(id);
    if (c) {
      c.x = (c.x * c.count + x) / (c.count + 1);
      c.y = (c.y * c.count + y) / (c.count + 1);
      c.count++;
      if (ranks[i] > c.maxRank) c.maxRank = ranks[i];
      c.members.push(i);
    } else {
      cells.set(id, { x, y, count: 1, maxRank: ranks[i], members: [i] });
    }
  }
  return [...cells.values()];
}

/**
 * 움직이는 동안 묶음을 다시 계산하지 않고, 직전 보기(from)에서 계산한 묶음을 현재 보기(to)로 옮긴다.
 * 월드 좌표가 같게 유지되므로 위치만 변환하고 구성(개수·단계)은 그대로다. 놓으면 새로 묶는다.
 */
export function carryClusters(clusters: Cluster[], from: View, to: View): Cluster[] {
  const k = to.scale / from.scale;
  return clusters.map((c) => ({ ...c, x: (c.x - from.ox) * k + to.ox, y: (c.y - from.oy) * k + to.oy }));
}

/** 단계 순번별 빛기둥 높이(px): 정상 0 · 주의 26 · 경고 33 · 위험 40 · 초과 48. 공백(-1)은 기둥 없음 */
export const BEAM_BY_RANK = [0, 26, 33, 40, 48] as const;
export function beamHeight(rank: number): number {
  return rank >= 0 ? BEAM_BY_RANK[rank] ?? 0 : 0;
}

export interface PinBox { x0: number; y0: number; x1: number; y1: number }
/** 핀(후광·빛기둥·개수 배지)이 차지하는 화면 상자. 받침이 (c.x, c.y)다 */
export function pinBox(c: Cluster): PinBox {
  const strong = c.maxRank >= 1;
  const halfW = strong ? 24 : 14;
  const bh = beamHeight(c.maxRank);
  let x1 = c.x + halfW;
  let y0 = c.y - Math.max(bh, 8);
  if (c.count > 1) {
    const badgeW = Math.max(36, String(c.count).length * 11 + 20); // MapPanel의 배지와 같은 크기
    x1 = Math.max(x1, c.x + 7 + badgeW);
    y0 = c.y - Math.max(bh, 24) - 4; // 배지 윗변
  }
  return { x0: c.x - halfW, y0, x1, y1: c.y + (strong ? 8 : 5) };
}

/**
 * 클릭·올림 판정. 핀이 그려진 상자 전체(후광·기둥·배지)에 여유(pad)를 더한 안이면 맞은 것으로 본다.
 * 여러 개가 걸리면 받침이 가장 가까운 것. 없으면 -1. 점 하나만 정확히 눌러야 하던 불편을 없앤다.
 */
export function pinHit(clusters: Cluster[], px: number, py: number, pad = 8): number {
  let best = -1;
  let bestD = Infinity;
  for (let i = 0; i < clusters.length; i++) {
    const b = pinBox(clusters[i]);
    if (px < b.x0 - pad || px > b.x1 + pad || py < b.y0 - pad || py > b.y1 + pad) continue;
    const dx = clusters[i].x - px, dy = clusters[i].y - py;
    const d = dx * dx + dy * dy;
    if (d < bestD) { bestD = d; best = i; }
  }
  return best;
}

/** 화면 점 (px,py)에서 반경 안에서 가장 가까운 묶음. 없으면 -1 */
export function nearestCluster(clusters: Cluster[], px: number, py: number, radius: number): number {
  let best = -1;
  let bestD = radius * radius;
  for (let i = 0; i < clusters.length; i++) {
    const dx = clusters[i].x - px, dy = clusters[i].y - py;
    const d = dx * dx + dy * dy;
    if (d <= bestD) {
      bestD = d;
      best = i;
    }
  }
  return best;
}

/**
 * 줌에 따라 달라지는 묶기. 1단계는 격자(반경의 절반 칸)로 한 번 훑고, 2단계는 중심끼리 반경보다 가까운 묶음을
 * 합친다(옛 지도와 같은 규칙: 합쳐도 서로 반경보다 멀어질 때까지). 묶음 수가 적어 2단계는 싸다.
 */
export function clusterRadiusMerge(
  xs: Float32Array,
  ys: Float32Array,
  ranks: Int8Array,
  radius: number,
  width: number,
  height: number,
): Cluster[] {
  const cs = clusterGrid(xs, ys, ranks, radius / 2, width, height).sort((a, b) => a.x - b.x || a.y - b.y);
  const r2 = radius * radius;
  for (let pass = 0; pass < 8; pass++) {
    let merged = false;
    for (let i = 0; i < cs.length; i++) {
      for (let j = i + 1; j < cs.length; j++) {
        const dx = cs[i].x - cs[j].x, dy = cs[i].y - cs[j].y;
        if (dx * dx + dy * dy >= r2) continue;
        const a = cs[i], b = cs[j], n = a.count + b.count;
        a.x = (a.x * a.count + b.x * b.count) / n;
        a.y = (a.y * a.count + b.y * b.count) / n;
        a.count = n;
        a.maxRank = Math.max(a.maxRank, b.maxRank);
        a.members = a.members.concat(b.members);
        cs.splice(j, 1);
        j--;
        merged = true;
      }
    }
    if (!merged) break;
  }
  return cs;
}

/** 점이 다각형(바깥 고리 + 구멍 고리들) 안에 있는지: 짝홀 규칙 */
export function pointInRings(x: number, y: number, rings: Array<Array<[number, number]>>): boolean {
  let inside = false;
  for (const ring of rings) {
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
    }
  }
  return inside;
}

// ── 부드러운 이동(알아서 넘어가는 카메라) ─────────────────────────────

export const easeOutCubic = (t: number) => 1 - Math.pow(1 - Math.min(1, Math.max(0, t)), 3);

/** 화면 중심이 가리키는 세계 좌표 */
export function centerOf(view: View, w: number, h: number): [number, number] {
  return [(w / 2 - view.ox) / view.scale, (h / 2 - view.oy) / view.scale];
}

/**
 * 두 보기 사이를 t(0~1)만큼 옮긴 보기. 중심은 직선으로, 배율은 비율(로그)로 섞어 확대·축소가 고르게 느껴지게 한다.
 * 크기(w,h)가 같은 화면 안에서의 이동이다.
 */
export function interpolateView(from: View, to: View, t: number, w: number, h: number): View {
  const [fx, fy] = centerOf(from, w, h);
  const [tx, ty] = centerOf(to, w, h);
  const scale = Math.exp(Math.log(from.scale) + (Math.log(to.scale) - Math.log(from.scale)) * t);
  const cx = fx + (tx - fx) * t;
  const cy = fy + (ty - fy) * t;
  return { scale, ox: w / 2 - cx * scale, oy: h / 2 - cy * scale };
}

/** 이 세계 좌표를 화면 가운데에 두고 주어진 배율로 맞춘 보기 */
export function centeredOn(x: number, y: number, scale: number, w: number, h: number): View {
  return { scale, ox: w / 2 - x * scale, oy: h / 2 - y * scale };
}

/** 사업장을 고르면 이 배율(최대 상세 등급)까지 확대한다. 이미 이 이상이고 화면 여백 안이면 움직이지 않는다 */
export const FOCUS_SCALE = 1600;
export function needsFocus(view: View, sx: number, sy: number, w: number, h: number): boolean {
  if (view.scale < FOCUS_SCALE) return true;
  return sx < 50 || sx > w - 50 || sy < 60 || sy > h - 70;
}

/**
 * 묶음을 눌렀을 때 도착할 보기: 묶음 구성원이 다 보이도록 맞추되, 누를 때마다 최소 step배는 확대해 쭉쭉 파고들게 한다.
 * (구성원이 넓게 퍼져 있어도 한 번에 전부 보이는 데서 멈추지 않고 계속 확대된다)
 */
export function stepZoomView(b: Bounds, current: View, w: number, h: number, pad = 60, step = 2): View {
  const fit = fitView(b, w, h, pad);
  const scale = Math.min(MAX_SCALE, Math.max(fit.scale, current.scale * step));
  return centeredOn((b.minX + b.maxX) / 2, (b.minY + b.maxY) / 2, scale, w, h);
}

/** 이동 시간(ms): 배율 차이(2배 단위)가 클수록 조금 길게. 너무 짧거나 길지 않게 */
export function flightDuration(fromScale: number, toScale: number): number {
  const octaves = Math.abs(Math.log2(toScale / fromScale));
  return Math.min(900, Math.max(450, 400 + 70 * octaves));
}
