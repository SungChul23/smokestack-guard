import { afterEach, describe, expect, it, vi } from "vitest";
import { MAP_MODES, MODE_KEY, readMapMode, writeMapMode } from "./mode";

afterEach(() => { vi.restoreAllMocks(); window.localStorage.clear(); });

describe("지도 종류 저장", () => {
  it("저장 키는 tms-map-mode, 선택지는 관제·일반·위성", () => {
    expect(MODE_KEY).toBe("tms-map-mode");
    expect(MAP_MODES.map((m) => m.key)).toEqual(["control", "normal", "satellite"]);
    expect(MAP_MODES.map((m) => m.aria)).toEqual(["관제 지도", "네이버 일반", "네이버 위성"]);
  });

  it("저장한 게 없거나 이상한 값이면 관제 지도", () => {
    expect(readMapMode()).toBe("control");
    window.localStorage.setItem(MODE_KEY, "해적지도");
    expect(readMapMode()).toBe("control");
  });

  it("일반·위성은 저장하고 다시 읽는다, 관제로 돌아오면 지운다", () => {
    writeMapMode("satellite");
    expect(window.localStorage.getItem(MODE_KEY)).toBe("satellite");
    expect(readMapMode()).toBe("satellite");
    writeMapMode("normal");
    expect(readMapMode()).toBe("normal");
    writeMapMode("control");
    expect(window.localStorage.getItem(MODE_KEY)).toBeNull();
  });

  it("저장소가 막혀 있어도 오류 없이 동작한다", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(readMapMode()).toBe("control");
    expect(() => writeMapMode("normal")).not.toThrow();
    expect(() => writeMapMode("control")).not.toThrow();
  });
});
