// 지도 중앙이 어느 지역인지 판단한다(순수 함수). 땅을 눌러 이동하는 대신, 확대하고 움직인 뒤 멈추면 화면 중앙을 보고 정한다.
// 경로는 경고 목록을 거르고 위치 표시(전국 › 시도 › 시군)를 채우는 데만 쓰이며, 지도를 움직이지 않는다.
import { centerOf, GRADE_SCALES, pointInRings, type View } from "./geometry";

export interface RegionPoly {
  name: string;
  polys: Array<Array<Array<[number, number]>>>; // 다각형마다 [바깥 고리, 구멍…] (월드 좌표)
}
export interface SitePos {
  sido: string;
  sigungu: string;
  x: number; // 월드 좌표
  y: number;
}
export interface MapPathValue {
  sido: string | null;
  sigungu: string | null;
}

/** 중앙에서 이 거리(px) 안의 사업장으로만 지역을 짐작한다(바다·빈 곳에서 엉뚱한 지역이 잡히지 않게) */
export const SIDO_GUESS_PX = 150;
export const SIGUNGU_GUESS_PX = 120;

export function regionAtCenter(view: View, w: number, h: number, regions: RegionPoly[], sites: SitePos[]): MapPathValue {
  // 넓게(광역) 보면 지역을 특정하지 않는다
  if (view.scale < GRADE_SCALES[0]) return { sido: null, sigungu: null };
  const [cx, cy] = centerOf(view, w, h);

  // 가장 가까운 사업장(화면 거리 px)
  let nearest: SitePos | null = null;
  let nearestD = Infinity;
  for (const s of sites) {
    const d = Math.hypot(s.x - cx, s.y - cy) * view.scale;
    if (d < nearestD) { nearestD = d; nearest = s; }
  }

  // 시도: 중앙이 든 경계. 바다 등 경계 밖이면 가까운 사업장으로 짐작
  let sido = regions.find((r) => r.polys.some((rings) => pointInRings(cx, cy, rings)))?.name ?? null;
  if (!sido && nearest && nearestD <= SIDO_GUESS_PX) sido = nearest.sido;
  if (!sido) return { sido: null, sigungu: null };

  // 시군: 상세 등급부터. 같은 시도 안에서 중앙에 가장 가까운 사업장의 시군
  let sigungu: string | null = null;
  if (view.scale >= GRADE_SCALES[1]) {
    let best: SitePos | null = null;
    let bestD = Infinity;
    for (const s of sites) {
      if (s.sido !== sido) continue;
      const d = Math.hypot(s.x - cx, s.y - cy) * view.scale;
      if (d < bestD) { bestD = d; best = s; }
    }
    if (best && bestD <= SIGUNGU_GUESS_PX) sigungu = best.sigungu;
  }
  return { sido, sigungu };
}
