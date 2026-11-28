// 추세 차트의 세로 눈금(순수 함수).
// 기준값(100%) 아래를 높이의 80%에 고정하고, 남은 위쪽 20%를 "기준 초과 영역"으로 쓴다. 이 영역은 기본 120%까지이고
// 값이 그보다 크면 위쪽 한계만 늘어난다. 그래서 기준을 크게 넘어도 아래쪽 80%의 모양이 변하지 않고, 선이 뾰족해지지 않는다.

/** 높이에서 기준값 이하(0~100%)가 차지하는 몫 */
export const FIXED_FRACTION = 0.8;
/** 위쪽 영역의 기본 한계(기준값 대비 %) */
export const DEFAULT_TOP_RATIO = 120;

/** 위쪽 영역의 한계(%): 120%까지는 120%로 고정하고, 최대 비율이 120%를 넘을 때만 10% 단위로 올림해 늘린다(5% 여유) */
export function topRatioFor(maxRatio: number): number {
  if (!Number.isFinite(maxRatio) || maxRatio <= DEFAULT_TOP_RATIO) return DEFAULT_TOP_RATIO;
  return Math.ceil((maxRatio * 1.05) / 10) * 10;
}

/** 기준 대비 비율(%) → 높이 비율(0~1, 아래가 0). 100% 아래는 80%에 선형, 위는 남은 20%에 선형 */
export function fractionOf(ratioPct: number, top: number): number {
  if (!(ratioPct > 0)) return 0;
  if (ratioPct <= 100) return (FIXED_FRACTION * ratioPct) / 100;
  const span = Math.max(top - 100, 1e-9);
  return FIXED_FRACTION + (1 - FIXED_FRACTION) * Math.min(1, (ratioPct - 100) / span);
}

export interface ChartScale {
  /** 측정값 → 높이 비율(0~1) */
  toFraction: (value: number) => number;
  /** 기준값(없으면 null: 눈금이 선형이고 위쪽 영역도 없다) */
  limit: number | null;
  /** 위쪽 한계(기준 대비 %). 기준값이 없으면 null */
  topRatio: number | null;
  /** 위쪽 한계의 측정값 */
  topValue: number;
}

/** 값들과 기준값으로 눈금을 만든다. 기준값이 없으면 단계를 알 수 없으므로 예전처럼 선형으로 둔다 */
export function makeScale(values: Array<number | null>, limit: number | null): ChartScale {
  const max = Math.max(0, ...values.filter((v): v is number => v !== null));
  if (limit !== null && limit > 0) {
    const top = topRatioFor((max / limit) * 100);
    return {
      toFraction: (v) => fractionOf((v / limit) * 100, top),
      limit,
      topRatio: top,
      topValue: (limit * top) / 100,
    };
  }
  const yMax = Math.max(max * 1.2, 1);
  return { toFraction: (v) => Math.min(1, Math.max(0, v / yMax)), limit: null, topRatio: null, topValue: yMax };
}

export interface GapLink {
  /**
   * bridge: 값이 없는 구간 양쪽의 실측 사이를 이은 선,
   * leading: 왼쪽 끝에서 첫 실측까지(첫 실측 높이의 안내선), trailing: 마지막 실측에서 오른쪽 끝까지(마지막 실측 높이의 안내선)
   */
  kind: "bridge" | "leading" | "trailing";
  i0: number; // 이어지는 두 점의 위치(배열 인덱스)와 값
  v0: number;
  i1: number;
  v1: number;
}

/**
 * 값이 없는 구간을 점선으로 이을 선분들. 값이 없는 구간은 모두 여기에 들어가므로 칠하지 않은 빈 영역이 남지 않는다.
 *  - 실측이 둘 이상 떨어져 있으면 그 사이를 잇는다(bridge).
 *  - 첫 실측 앞이 비어 있으면 첫 값 높이로 왼쪽 끝부터 안내선(leading), 마지막 실측 뒤가 비어 있으면 마지막 값 높이로 오른쪽 끝까지 안내선(trailing)을 낸다.
 *  - 실측이 하나도 없으면 이을 기준이 없어 비어 있다(그리는 쪽에서 구간 전체를 옅게 칠한다).
 * 이은 선은 추정일 뿐 측정값이 아니므로 그리기만 하고 값으로 쓰지 않는다.
 */
export function gapLinks(points: Array<{ value: number | null }>): GapLink[] {
  const valid: number[] = [];
  points.forEach((p, i) => { if (p.value !== null) valid.push(i); });
  const links: GapLink[] = [];
  const first = valid[0];
  if (first !== undefined && first > 0) {
    const v = points[first].value as number;
    links.push({ kind: "leading", i0: 0, v0: v, i1: first, v1: v });
  }
  for (let k = 1; k < valid.length; k++) {
    const a = valid[k - 1], b = valid[k];
    if (b - a > 1) links.push({ kind: "bridge", i0: a, v0: points[a].value as number, i1: b, v1: points[b].value as number });
  }
  const last = valid[valid.length - 1];
  if (last !== undefined && last < points.length - 1) {
    const v = points[last].value as number;
    links.push({ kind: "trailing", i0: last, v0: v, i1: points.length - 1, v1: v });
  }
  return links;
}
