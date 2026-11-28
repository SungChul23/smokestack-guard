// 그래프 선 경로(순수 함수). 직선으로 잇거나, 부드러운 곡선으로 잇는다.
export type XY = readonly [number, number];

const f = (n: number) => n.toFixed(1);

/** 점들을 직선으로 잇는 경로 */
export function straightPath(pts: readonly XY[]): string {
  return pts.map(([x, y], k) => `${k ? "L" : "M"}${f(x)} ${f(y)}`).join(" ");
}

/**
 * 점들을 지나는 부드러운 곡선(단조 3차 보간, Fritsch–Carlson). x는 늘어나는 순서여야 한다.
 * 일반 스플라인과 달리 점 사이에서 값이 위아래로 튀어 오르지 않아서(없는 극값을 만들지 않아서) 측정 그래프에 맞다.
 */
export function smoothPath(pts: readonly XY[]): string {
  const n = pts.length;
  if (n < 3) return straightPath(pts);
  const dx: number[] = [], dy: number[] = [], slope: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    dx.push(pts[i + 1][0] - pts[i][0]);
    dy.push(pts[i + 1][1] - pts[i][1]);
    slope.push(dx[i] === 0 ? 0 : dy[i] / dx[i]);
  }
  const m: number[] = new Array(n).fill(0);
  m[0] = slope[0];
  m[n - 1] = slope[n - 2];
  for (let i = 1; i < n - 1; i++) {
    // 이웃한 두 기울기의 부호가 다르면 극값이므로 평평하게(0), 같으면 조화평균
    m[i] = slope[i - 1] * slope[i] <= 0 ? 0 : (2 * slope[i - 1] * slope[i]) / (slope[i - 1] + slope[i]);
  }
  // 과하게 휘지 않게 기울기를 제한한다
  for (let i = 0; i < n - 1; i++) {
    if (slope[i] === 0) { m[i] = 0; m[i + 1] = 0; continue; }
    const a = m[i] / slope[i], b = m[i + 1] / slope[i];
    const s = a * a + b * b;
    if (s > 9) { const t = 3 / Math.sqrt(s); m[i] = t * a * slope[i]; m[i + 1] = t * b * slope[i]; }
  }
  let d = `M${f(pts[0][0])} ${f(pts[0][1])}`;
  for (let i = 0; i < n - 1; i++) {
    const [x0, y0] = pts[i], [x1, y1] = pts[i + 1];
    const h = dx[i] / 3;
    d += ` C${f(x0 + h)} ${f(y0 + m[i] * h)} ${f(x1 - h)} ${f(y1 - m[i + 1] * h)} ${f(x1)} ${f(y1)}`;
  }
  return d;
}

export const linePath = (pts: readonly XY[], smooth: boolean) => (smooth ? smoothPath(pts) : straightPath(pts));
