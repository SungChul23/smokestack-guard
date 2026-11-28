// 시험 공통 준비: jest-dom 판정(toBeInTheDocument 등)과 시험마다 화면·저장소 정리
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";
import { useChartStyle } from "../state/chartStyle";
import { LEGACY_CHART_STYLE } from "./legacyChartStyle";
import { setViewport, uninstallMedia } from "./media";

// localStorage를 메모리 저장소로 고정한다. 최신 Node(25 이상)는 자체 localStorage를 전역에 만들어
// jsdom의 것이 들어오지 못하고 undefined가 되므로, Node 버전과 상관없이 같게 동작하게 한다.
class MemoryStorage {
  private items = new Map<string, string>();
  get length() {
    return this.items.size;
  }
  clear() {
    this.items.clear();
  }
  getItem(key: string) {
    return this.items.has(key) ? (this.items.get(key) as string) : null;
  }
  key(index: number) {
    return Array.from(this.items.keys())[index] ?? null;
  }
  removeItem(key: string) {
    this.items.delete(key);
  }
  setItem(key: string, value: string) {
    this.items.set(key, String(value));
  }
}

// jsdom에는 PointerEvent가 없어 fireEvent.pointer*의 좌표(clientX/Y)와 button이 전달되지 않는다. 마우스 이벤트를 확장해 채운다.
if (typeof window.PointerEvent === "undefined") {
  class PointerEventPolyfill extends MouseEvent {
    pointerId: number;
    pointerType: string;
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 1;
      this.pointerType = init.pointerType ?? "mouse";
    }
  }
  Object.defineProperty(window, "PointerEvent", { value: PointerEventPolyfill, configurable: true, writable: true });
}

const storage = new MemoryStorage();
for (const target of [window, globalThis]) {
  Object.defineProperty(target, "localStorage", { value: storage, configurable: true, writable: true });
}

// 그래프를 그리는 시험은 기본값이 바뀌어도 같은 모양을 보도록 예전 모양으로 시작한다(새 기본값을 보는 시험은 reset()을 부른다)
beforeEach(() => {
  useChartStyle.setState({ styles: { dark: { ...LEGACY_CHART_STYLE }, light: { ...LEGACY_CHART_STYLE } } });
});

afterEach(() => {
  cleanup();
  uninstallMedia(); // 시험이 정한 화면 조건·창 크기를 다음 시험으로 넘기지 않는다
  setViewport(1024, 768);
  storage.clear();
  document.documentElement.removeAttribute("data-theme");
});
