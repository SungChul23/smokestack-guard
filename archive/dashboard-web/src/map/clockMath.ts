// 지도 시계 계산(순수 함수). 시계는 보여 주기만 한다(조작은 아래 슬라이더). 12시간 아날로그 + 플립 숫자판.

/** 시점(ms)의 한국 시각 기준 하루 중 분(0~1439) */
export function minutesOfDay(ms: number): number {
  const d = new Date(ms + 9 * 3600000);
  return d.getUTCHours() * 60 + d.getUTCMinutes();
}

/** 시침 각도(도, 12시가 위쪽, 시계 방향). 12시간에 한 바퀴 */
export function hourAngle(ms: number): number {
  return ((minutesOfDay(ms) % 720) / 720) * 360;
}

/** 분침 각도(도). 60분에 한 바퀴 */
export function minuteAngle(ms: number): number {
  return ((minutesOfDay(ms) % 60) / 60) * 360;
}

/** 오후(12시 이후)인지 */
export function isPm(ms: number): boolean {
  return minutesOfDay(ms) >= 720;
}

/** 한국 시각 날짜·시각 조각(24시간 숫자판용) */
export function partsOf(ms: number) {
  const iso = new Date(ms + 9 * 3600000).toISOString();
  return { year: iso.slice(0, 4), month: iso.slice(5, 7), day: iso.slice(8, 10), hour: iso.slice(11, 13), minute: iso.slice(14, 16) };
}

const mod360 = (a: number) => ((a % 360) + 360) % 360;

/** 바늘이 도는 방향: 앞으로(시계 방향) / 뒤로 / 가까운 쪽 */
export type Spin = "forward" | "back" | "near";

/**
 * 바늘의 누적 각도. 0도를 넘을 때 거꾸로 한 바퀴 돌지 않게, 이전 누적 각도에서 얼마나 더 가는지만 더한다.
 * 분침은 30분이 정확히 180도라 "가까운 쪽"이 모호하므로, 한 칸씩 갈 때는 방향을 정해 준다.
 */
export function nextUnwrapped(prevUnwrapped: number, nextAngle: number, spin: Spin): number {
  const prev = mod360(prevUnwrapped);
  const next = mod360(nextAngle);
  if (spin === "forward") return prevUnwrapped + mod360(next - prev);
  if (spin === "back") return prevUnwrapped - mod360(prev - next);
  let d = mod360(next - prev);
  if (d > 180) d -= 360; // (-180, 180]
  return prevUnwrapped + d;
}

/** 시점 번호가 얼마나 바뀌었는지로 방향을 정한다: 한 칸 이내면 그 방향, 크게 뛰면 가까운 쪽 */
export function spinFor(prevIndex: number, nextIndex: number): Spin {
  const d = nextIndex - prevIndex;
  if (Math.abs(d) <= 1) return d >= 0 ? "forward" : "back";
  return "near";
}
