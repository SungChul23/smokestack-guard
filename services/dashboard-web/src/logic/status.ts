// 상태 분류 (spec 318 §10). 비율 = 측정값 / 허용기준 × 100.
// 주의 ≥70, 경고 ≥80, 위험 ≥90, 초과 ≥100. 그 아래는 정상.
// 값이 없으면(미수신·점검 등 상태 행) 정상이 아니라 "공백"(null)이다. 0이나 정상으로 채우지 않는다.

export type LevelKey = "ok" | "caution" | "warn" | "risk" | "exceed";

export interface LevelInfo {
  key: LevelKey;
  label: string;
  /** 이 비율(%) 이상이면 이 단계 */
  min: number;
}

/** 낮은 단계부터 순서대로. 판정은 가장 높은 min을 넘은 단계를 고른다. */
export const LEVELS: readonly LevelInfo[] = [
  { key: "ok", label: "정상", min: 0 },
  { key: "caution", label: "주의", min: 70 },
  { key: "warn", label: "경고", min: 80 },
  { key: "risk", label: "위험", min: 90 },
  { key: "exceed", label: "초과", min: 100 },
];

/** 지표 카드·경고 목록에 올리는 단계(정상 제외) */
export const ALERT_LEVELS: readonly LevelInfo[] = LEVELS.filter((l) => l.key !== "ok");

export function levelOf(ratioPct: number | null | undefined): LevelKey | null {
  if (ratioPct === null || ratioPct === undefined || !Number.isFinite(ratioPct)) return null;
  let found: LevelKey = "ok";
  for (const level of LEVELS) {
    if (ratioPct >= level.min) found = level.key;
  }
  return found;
}

export function labelOf(key: LevelKey): string {
  return LEVELS.find((l) => l.key === key)?.label ?? "";
}

/** 푸터 문구: "주의 ≥70% · 경고 ≥80% · 위험 ≥90% · 초과 ≥100%" */
export function thresholdText(): string {
  return ALERT_LEVELS.map((l) => `${l.label} ≥${l.min}%`).join(" · ");
}
