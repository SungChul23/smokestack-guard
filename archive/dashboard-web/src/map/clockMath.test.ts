import { describe, expect, it } from "vitest";
import { hourAngle, isPm, minuteAngle, minutesOfDay, nextUnwrapped, partsOf, spinFor } from "./clockMath";

// 한국 시각 11-10 00:00부터 30분 간격 48개
const start = Date.UTC(2026, 10, 9, 15, 0);
const times = Array.from({ length: 48 }, (_, i) => start + i * 1800000);

describe("지도 시계(12시간)", () => {
  it("한국 시각 기준 하루 중 분", () => {
    expect(minutesOfDay(times[0])).toBe(0);
    expect(minutesOfDay(times[47])).toBe(23 * 60 + 30);
  });
  it("시침: 12시는 위쪽(0도), 3시는 90도, 6시는 180도, 9시는 270도", () => {
    expect(hourAngle(times[0])).toBe(0); // 00:00 = 12시
    expect(hourAngle(times[6])).toBe(90); // 03:00
    expect(hourAngle(times[12])).toBe(180); // 06:00
    expect(hourAngle(times[18])).toBe(270); // 09:00
  });
  it("정오·자정은 같은 위치이고, 오전·오후로 구분한다", () => {
    expect(hourAngle(times[24])).toBe(0); // 12:00
    expect(isPm(times[23])).toBe(false);
    expect(isPm(times[24])).toBe(true);
    expect(isPm(times[47])).toBe(true);
  });
  it("시침은 30분마다 15도씩 간다", () => {
    expect(hourAngle(times[1])).toBe(15);
  });
  it("분침: 0분은 위쪽, 30분은 아래쪽", () => {
    expect(minuteAngle(times[0])).toBe(0);
    expect(minuteAngle(times[1])).toBe(180);
  });
  it("날짜·시각 조각은 한국 시각이다", () => {
    expect(partsOf(times[47])).toEqual({ year: "2026", month: "11", day: "10", hour: "23", minute: "30" });
  });
});

describe("바늘 누적 각도(재생 중 부드럽게 돌기)", () => {
  it("재생 중에는 0도를 넘어도 계속 앞으로 간다", () => {
    expect(nextUnwrapped(345, 0, "forward")).toBe(360);
    expect(nextUnwrapped(360, 15, "forward")).toBe(375);
  });
  it("분침은 30분마다 180도씩 앞으로 간다(되감기지 않는다)", () => {
    let a = 0;
    const seen = [a];
    for (let i = 0; i < 4; i++) { a = nextUnwrapped(a, (a + 180) % 360, "forward"); seen.push(a); }
    expect(seen).toEqual([0, 180, 360, 540, 720]);
  });
  it("같은 각도면 움직이지 않는다", () => {
    expect(nextUnwrapped(100, 100, "forward")).toBe(100);
    expect(nextUnwrapped(100, 100, "near")).toBe(100);
  });
  it("슬라이더로 뛸 때는 가까운 쪽으로 간다(뒤로 가면 뒤로)", () => {
    expect(nextUnwrapped(10, 350, "near")).toBe(-10); // 20도 뒤로
    expect(nextUnwrapped(350, 10, "near")).toBe(370); // 20도 앞으로
    expect(nextUnwrapped(100, 40, "near")).toBe(40);
  });
  it("누적해도 실제 각도(360으로 나눈 나머지)는 맞다", () => {
    const a = nextUnwrapped(720 + 345, 10, "forward");
    expect(((a % 360) + 360) % 360).toBeCloseTo(10);
  });
  it("분침 180도(30분)도 뒤로 가라고 하면 되감는다(정지·되돌릴 때 앞으로 도는 것을 막는다)", () => {
    expect(nextUnwrapped(180, 0, "back")).toBe(0);
    expect(nextUnwrapped(360, 180, "back")).toBe(180);
    expect(nextUnwrapped(100, 100, "back")).toBe(100);
  });
  it("방향은 시점 번호 변화로 정한다", () => {
    expect(spinFor(3, 4)).toBe("forward");
    expect(spinFor(4, 3)).toBe("back");
    expect(spinFor(3, 3)).toBe("forward");
    expect(spinFor(3, 20)).toBe("near");
    expect(spinFor(20, 3)).toBe("near");
  });
});
