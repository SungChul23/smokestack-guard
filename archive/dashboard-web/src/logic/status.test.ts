import { describe, expect, it } from "vitest";
import { ALERT_LEVELS, labelOf, levelOf, LEVELS, thresholdText } from "./status";

describe("levelOf: 비율(%)로 상태 단계를 고른다", () => {
  it.each([
    [0, "ok"],
    [69.99, "ok"],
    [70, "caution"], // 경계값은 그 단계에 속한다(이상)
    [79.99, "caution"],
    [80, "warn"],
    [89.99, "warn"],
    [90, "risk"],
    [99.99, "risk"],
    [100, "exceed"],
    [250, "exceed"],
  ])("%s%% → %s", (ratio, expected) => {
    expect(levelOf(ratio)).toBe(expected);
  });

  it("값이 없으면 정상이 아니라 공백(null)이다", () => {
    expect(levelOf(null)).toBeNull();
    expect(levelOf(undefined)).toBeNull();
    expect(levelOf(Number.NaN)).toBeNull();
    expect(levelOf(Number.POSITIVE_INFINITY)).toBeNull();
  });

  it("음수는 정상이다(유한한 값)", () => {
    expect(levelOf(-3)).toBe("ok");
  });
});

describe("단계 정의", () => {
  it("낮은 단계부터 기준이 오른다", () => {
    const mins = LEVELS.map((l) => l.min);
    expect(mins).toEqual([...mins].sort((a, b) => a - b));
  });

  it("지표 카드는 정상을 뺀 4단계다", () => {
    expect(ALERT_LEVELS.map((l) => l.label)).toEqual(["주의", "경고", "위험", "초과"]);
  });

  it("푸터 문구가 기준과 같다", () => {
    expect(thresholdText()).toBe("주의 ≥70% · 경고 ≥80% · 위험 ≥90% · 초과 ≥100%");
  });

  it("이름을 돌려준다", () => {
    expect(labelOf("risk")).toBe("위험");
  });
});
