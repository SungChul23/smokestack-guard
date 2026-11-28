// 지도 시각이 바뀔 때 "새로 경고가 된 굴뚝"을 찾는다(번쩍이는 효과의 대상). 순수 함수.
import type { SiteState } from "../data/model";
import { rankOf } from "./geometry";

export const FLARE_MAX_JUMP = 2; // 시각이 이보다 크게 뛰면(슬라이더로 점프) 번쩍이지 않는다

export type RankMap = Map<string, number>;

export function ranksOf(states: SiteState[]): RankMap {
  return new Map(states.map((s) => [s.site.id, rankOf(s.level)]));
}

/**
 * 이전 시각과 비교해 주의(1단계) 이상이면서 단계가 오른 사업장. 공백·정상에서 올라온 것과 단계가 더 높아진 것을 포함한다.
 * 크게 뛰었거나(slotJump), 같은 시각이면 빈 목록을 돌려준다. 개수 상한은 두지 않는다: 그리는 쪽이 묶음 단위로 한 번만 번쩍인다.
 */
export function freshAlerts(prev: RankMap | null, states: SiteState[], slotJump: number): SiteState[] {
  if (!prev || slotJump === 0 || Math.abs(slotJump) > FLARE_MAX_JUMP) return [];
  return states.filter((s) => {
    const r = rankOf(s.level);
    return r >= 1 && r > (prev.get(s.site.id) ?? -1);
  });
}
