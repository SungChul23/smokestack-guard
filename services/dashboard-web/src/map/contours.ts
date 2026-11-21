// 등고선 불러오기. 전국 개요(800m 간격) 한 개와 시도별(200m 간격) 파일을 필요할 때만 읽는다.
// 좌표는 웹 메르카토르 세계 좌표(폭 256)라서 경계·사업장과 같은 좌표계다. 선마다 Path2D를 한 번만 만들어 둔다.
import type { Bounds } from "./geometry";

export interface ContourEntry {
  file: string;
  bbox: [number, number, number, number];
}
export interface ContourIndex {
  overview: ContourEntry;
  regions: Record<string, ContourEntry>;
}
export interface ContourLine {
  e: number; // 고도(m)
  b: [number, number, number, number]; // 선의 경계 상자
  path: Path2D | null;
}

interface RawLine {
  e: number;
  b: [number, number, number, number];
  p: number[];
}

const BASE = "/map-data"; // public/map-data/ (사업장 정보가 없는 정적 자료, 개발·운영 공통)

export async function loadIndex(): Promise<ContourIndex> {
  const res = await fetch(`${BASE}/contours/index.json`);
  if (!res.ok) throw new Error(`등고선 목록 없음 (${res.status})`);
  return (await res.json()) as ContourIndex;
}

function build(raw: RawLine[]): ContourLine[] {
  return raw.map((l) => {
    let path: Path2D | null = null;
    if (typeof Path2D !== "undefined") {
      path = new Path2D();
      for (let i = 0; i < l.p.length; i += 2) {
        if (i === 0) path.moveTo(l.p[0], l.p[1]);
        else path.lineTo(l.p[i], l.p[i + 1]);
      }
    }
    return { e: l.e, b: l.b, path };
  });
}

/** 읽은 파일을 기억해 두는 저장소. 같은 파일은 한 번만 읽는다 */
export class ContourStore {
  private ready = new Map<string, ContourLine[]>();
  private pending = new Map<string, Promise<ContourLine[]>>();

  get(file: string): ContourLine[] | undefined {
    return this.ready.get(file);
  }

  load(file: string): Promise<ContourLine[]> {
    const hit = this.ready.get(file);
    if (hit) return Promise.resolve(hit);
    let p = this.pending.get(file);
    if (!p) {
      p = fetch(`${BASE}/${file}`)
        .then((res) => {
          if (!res.ok) throw new Error(`${file} 읽기 실패 (${res.status})`);
          return res.json() as Promise<RawLine[]>;
        })
        .then((raw) => {
          const lines = build(raw);
          this.ready.set(file, lines);
          this.pending.delete(file);
          return lines;
        })
        .catch((e) => {
          this.pending.delete(file); // 실패하면 다음에 다시 시도할 수 있게 비운다
          throw e;
        });
      this.pending.set(file, p);
    }
    return p;
  }
}

const intersects = (a: [number, number, number, number], b: Bounds) =>
  a[0] <= b.maxX && a[2] >= b.minX && a[1] <= b.maxY && a[3] >= b.minY;

/** 지금 보기에서 읽어야 할 파일들. 개요면 하나, 지역이면 화면과 겹치는 시도 파일들 */
export function filesFor(index: ContourIndex, source: ContourSource, viewport: Bounds): string[] {
  if (source === "overview") return [index.overview.file];
  return Object.values(index.regions)
    .filter((r) => intersects(r.bbox, viewport))
    .map((r) => r.file);
}

/** 화면 상자와 겹치는 선만 */
export function visibleLines(sets: ContourLine[][], viewport: Bounds): ContourLine[] {
  const out: ContourLine[] = [];
  for (const set of sets) for (const l of set) if (intersects(l.b, viewport)) out.push(l);
  return out;
}

// ── 확대 등급별 계획 ─────────────────────────────────────────────
// 가진 자료는 개요(800m 간격, 0.1MB)와 지역(200m 간격, 17개 5.5MB)뿐이다. 넓게 볼 때는 큰 파일을 읽지 않고,
// 확대해서 볼 때만 지역 파일을 읽어 처음 로딩을 줄인다(필요한 부분만, 화면과 겹치는 시도 파일만).
export type ContourSource = "overview" | "regions";
export interface ContourPlan {
  source: ContourSource;
  /** 굵은 선의 농도 배율(넓게 볼 때는 더 은은하게) */
  bold: number;
  /** 굵은 선이 아닌 선(얇은 선)의 농도 배율. 0이면 굵은 선만 */
  thin: number;
}
const PLANS: Record<0 | 1 | 2 | 3, ContourPlan> = {
  0: { source: "overview", bold: 0.55, thin: 0 }, // 광역: 가장 성긴 큰 능선선만, 아주 은은하게
  1: { source: "overview", bold: 1, thin: 0 }, // 간략: 큰 능선선만
  2: { source: "regions", bold: 1, thin: 0.5 }, // 상세: 굵은 선 + 흐린 얇은 선
  3: { source: "regions", bold: 1, thin: 0.9 }, // 최대 상세: 모든 선이 뚜렷
};
export function contourPlan(grade: 0 | 1 | 2 | 3): ContourPlan {
  return PLANS[grade];
}

/** 굵은 선(계곡선)인지: 400m의 배수. 나머지는 얇은 선 */
export const isBold = (elevationM: number) => elevationM % 400 === 0;

// ── 고도 색상표: 높이와 색이 일대일로 맞되, 어두운 배경에 묻어나는 차분한 색조(채도를 낮춤) ──
// 낮은 곳 회녹색 → 연한 올리브 → 모래빛 → 흙빛 → 적갈색 → 가장 높은 곳 옅은 회백색.
export const ELEV_MAX = 1800;
export const RAMP: ReadonlyArray<readonly [number, string]> = [
  [0, "#587467"],
  [200, "#6f8a6f"],
  [400, "#87937a"],
  [600, "#999682"],
  [800, "#a38f7c"],
  [1000, "#9c7f72"],
  [1400, "#946d68"],
  [1800, "#c9c2bc"],
];

/** 라이트 테마용 색상표: 밝은 땅 위에서 보이도록 같은 순서(회녹 → 올리브 → 모래 → 흙 → 적갈 → 회갈)로 더 진하게 */
export const RAMP_LIGHT: ReadonlyArray<readonly [number, string]> = [
  [0, "#6b8f7e"],
  [200, "#7d9a6d"],
  [400, "#9a9b64"],
  [600, "#a58a55"],
  [800, "#a2704a"],
  [1000, "#955848"],
  [1400, "#80443f"],
  [1800, "#5f5450"],
];

function hex(n: string): [number, number, number] {
  return [parseInt(n.slice(1, 3), 16), parseInt(n.slice(3, 5), 16), parseInt(n.slice(5, 7), 16)];
}

/** 고도(m)에 해당하는 색(색상표 사이는 선형 보간, 범위 밖은 양 끝 색) */
export function rampColor(elevationM: number, light = false): string {
  const ramp = light ? RAMP_LIGHT : RAMP;
  const e = Math.min(ELEV_MAX, Math.max(0, elevationM));
  let i = 1;
  while (i < ramp.length - 1 && e > ramp[i][0]) i++;
  const [e0, c0] = ramp[i - 1], [e1, c1] = ramp[i];
  const t = (e - e0) / (e1 - e0);
  const a = hex(c0), b = hex(c1);
  const m = (k: number) => Math.round(a[k] + (b[k] - a[k]) * t);
  return `rgb(${m(0)}, ${m(1)}, ${m(2)})`;
}

/** 고도에 따른 선 모양. 색은 색상표, 높을수록 진하고 굵다. 굵은 선은 boldK, 얇은 선은 thin 배율만큼 흐리다 */
export function contourStyle(elevationM: number, thin = 1, boldK = 1, light = false): { color: string; alpha: number; width: number; bold: boolean } {
  const t = Math.min(1, Math.max(0, elevationM / ELEV_MAX));
  const bold = isBold(elevationM);
  const k = bold ? boldK : thin;
  return {
    color: rampColor(elevationM, light),
    alpha: (0.18 + 0.32 * t) * k * (light ? 1.35 : 1), // 밝은 땅에서는 같은 투명도로는 흐려 보여 조금 더 진하게
    width: (0.55 + 0.6 * t) * (bold ? 1.1 : 0.7),
    bold,
  };
}

/** 같은 고도끼리 묶어 낮은 것부터(높은 선이 위에 그려지도록) */
export function groupByElevation(lines: ContourLine[]): Array<[number, ContourLine[]]> {
  const m = new Map<number, ContourLine[]>();
  for (const l of lines) {
    const g = m.get(l.e);
    if (g) g.push(l);
    else m.set(l.e, [l]);
  }
  return [...m.entries()].sort((a, b) => a[0] - b[0]);
}
