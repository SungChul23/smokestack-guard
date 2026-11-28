import { afterEach, describe, expect, it, vi } from "vitest";
import { KEYS, mascotWanted, readMode, readRect, writeMascot, writeMode, writeRect } from "./prefs";

const vp = { w: 1200, h: 800 };

describe("에이전트 설정 저장", () => {
  afterEach(() => vi.restoreAllMocks());

  it("옛 웹과 같은 키를 쓴다(저장해 둔 값이 그대로 이어진다)", () => {
    expect(KEYS).toEqual({ rect: "tms-agent-frame-rect", mode: "tms-agent-frame-mode", mascot: "tms-mascot" });
  });

  it("창 위치·크기를 저장하고 읽는다", () => {
    writeRect({ x: 100, y: 50, w: 500, h: 600 });
    expect(readRect(vp)).toEqual({ x: 100, y: 50, w: 500, h: 600 });
    writeRect(null);
    expect(readRect(vp)).toBeNull();
  });

  it("저장값이 망가졌거나 형식이 틀리면 기본 위치로(null)", () => {
    window.localStorage.setItem(KEYS.rect, "{깨진 json");
    expect(readRect(vp)).toBeNull();
    window.localStorage.setItem(KEYS.rect, JSON.stringify({ x: 1, y: 2, w: "a", h: 4 }));
    expect(readRect(vp)).toBeNull();
    window.localStorage.setItem(KEYS.rect, "null");
    expect(readRect(vp)).toBeNull();
  });

  it("화면이 줄었으면 저장된 창을 안으로 끌어 넣는다", () => {
    writeRect({ x: 900, y: 700, w: 430, h: 700 });
    const r = readRect({ w: 700, h: 500 })!;
    expect(r.x + r.w).toBeLessThanOrEqual(700);
    expect(r.y + r.h).toBeLessThanOrEqual(500);
  });

  it("모드는 full이 아니면 모두 side다", () => {
    expect(readMode()).toBe("side");
    writeMode("full");
    expect(readMode()).toBe("full");
    window.localStorage.setItem(KEYS.mode, "이상한값");
    expect(readMode()).toBe("side");
  });

  it("마스코트는 기본이 꺼짐이고 저장하면 켜진다", () => {
    expect(mascotWanted("")).toBe(false);
    writeMascot(true);
    expect(mascotWanted("")).toBe(true);
    writeMascot(false);
    expect(mascotWanted("")).toBe(false);
  });

  it("주소의 ?mascot=off가 가장 우선이고 ?mascot=on은 저장 없이도 켠다", () => {
    writeMascot(true);
    expect(mascotWanted("?mascot=off")).toBe(false); // 저장은 켬이지만 주소가 우선
    writeMascot(false);
    expect(mascotWanted("?mascot=on")).toBe(true);
    expect(mascotWanted("?mascot=아무거나")).toBe(false);
  });

  it("저장소를 못 써도 던지지 않고 기본값을 쓴다(막힘·시크릿 창)", () => {
    vi.spyOn(window.localStorage, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(window.localStorage, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(window.localStorage, "removeItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(readRect(vp)).toBeNull();
    expect(readMode()).toBe("side");
    expect(mascotWanted("")).toBe(false);
    expect(() => { writeRect({ x: 1, y: 2, w: 400, h: 300 }); writeMode("full"); writeMascot(true); writeMascot(false); }).not.toThrow();
  });
});
