import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installMedia, setViewport } from "../test/media";
import Mascot from "./Mascot";
import { REDUCED_QUERY } from "./useMediaQuery";

const SIZE = 76;
// 창 1024×768, 마스코트 76px, 우하단 여백 22px → 처음 자리는 (1024-76-22, 768-76)
const START = "translate3d(926.0px,692.0px,0)";

const btn = () => screen.getByRole("button", { name: "에이전트 열기" });
const pos = () => /translate3d\(([-\d.]+)px,([-\d.]+)px/.exec(btn().style.transform)!.slice(1, 3).map(Number) as [number, number];
const down = (el: Element, x: number, y: number, extra = {}) => fireEvent.pointerDown(el, { button: 0, clientX: x, clientY: y, pointerId: 1, ...extra });
const move = (el: Element, x: number, y: number) => fireEvent.pointerMove(el, { clientX: x, clientY: y, pointerId: 1 });
const up = (el: Element, x = 0, y = 0) => fireEvent.pointerUp(el, { button: 0, clientX: x, clientY: y, pointerId: 1 });
const tick = (ms: number) => { for (let t = 0; t < ms; t += 16) act(() => { vi.advanceTimersByTime(16); }); };
const fixed = (v: number) => () => v;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["requestAnimationFrame", "cancelAnimationFrame", "performance", "setTimeout", "clearTimeout", "Date"] });
});
afterEach(() => {
  vi.useRealTimers();
  Reflect.deleteProperty(document, "hidden");
});

describe("마스코트: 나타남", () => {
  it("보이지 않을 때는 아무것도 그리지 않는다", () => {
    render(<Mascot visible={false} onOpen={() => {}} />);
    expect(screen.queryByRole("button", { name: "에이전트 열기" })).toBeNull();
  });

  it("보이면 우하단(옛 런처 자리)에서 시작한다", () => {
    render(<Mascot visible onOpen={() => {}} rng={fixed(0.5)} />);
    expect(btn().style.transform).toBe(START);
    expect(btn().dataset.mode).toBe("IDLE");
    expect(btn().getAttribute("aria-controls")).toBe("agent-window");
  });

  it("몸은 이미지(마스코트)다", () => {
    render(<Mascot visible onOpen={() => {}} />);
    expect(btn().querySelector("img")).toHaveAttribute("src", "/mascot.png");
  });
});

describe("마스코트: 열기", () => {
  it("움직이지 않고 누르면 에이전트 창을 연다", () => {
    const onOpen = vi.fn();
    render(<Mascot visible onOpen={onOpen} rng={fixed(0.5)} />);
    down(btn(), 950, 700);
    up(btn(), 950, 700);
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(btn().style.transform).toBe(START); // 누르기 전 자리로 돌아온다
  });

  it("조금 흔들려도(6px 안쪽) 클릭이다", () => {
    const onOpen = vi.fn();
    render(<Mascot visible onOpen={onOpen} rng={fixed(0.5)} />);
    down(btn(), 950, 700);
    move(btn(), 953, 703);
    up(btn(), 953, 703);
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("Enter·Space로도 연다(키보드)", () => {
    const onOpen = vi.fn();
    render(<Mascot visible onOpen={onOpen} />);
    fireEvent.keyDown(btn(), { key: "Enter" });
    fireEvent.keyDown(btn(), { key: " " });
    expect(onOpen).toHaveBeenCalledTimes(2);
  });

  it("보조기기가 누르면(클릭 detail 0) 연다", () => {
    const onOpen = vi.fn();
    render(<Mascot visible onOpen={onOpen} />);
    fireEvent.click(btn(), { detail: 0 });
    expect(onOpen).toHaveBeenCalledTimes(1);
    fireEvent.click(btn(), { detail: 1 }); // 마우스 클릭은 pointerup이 처리하므로 여기서는 열지 않는다
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("오른쪽 버튼은 잡기도 열기도 아니다", () => {
    const onOpen = vi.fn();
    render(<Mascot visible onOpen={onOpen} />);
    down(btn(), 950, 700, { button: 2 });
    up(btn(), 950, 700);
    expect(onOpen).not.toHaveBeenCalled();
  });
});

describe("마스코트: 잡아서 옮기기", () => {
  it("끌면 포인터를 따라가고(잡은 자리를 유지) 열리지는 않는다", () => {
    const onOpen = vi.fn();
    render(<Mascot visible onOpen={onOpen} rng={fixed(0.5)} />);
    down(btn(), 950, 700); // 몸 왼쪽 위에서 (24, 8) 떨어진 곳을 잡았다
    move(btn(), 500, 300);
    expect(pos()).toEqual([476, 292]);
    expect(btn().dataset.mode).toBe("DRAG");
    up(btn(), 500, 300);
    expect(onOpen).not.toHaveBeenCalled();
  });

  it("끌어도 화면 밖으로 나가지 않는다", () => {
    render(<Mascot visible onOpen={() => {}} rng={fixed(0.5)} />);
    down(btn(), 950, 700);
    move(btn(), -999, -999);
    expect(pos()).toEqual([0, 0]);
    move(btn(), 9999, 9999);
    expect(pos()).toEqual([1024 - SIZE, 768 - SIZE]);
  });

  it("놓으면 떨어져 바닥에 내려앉는다", () => {
    render(<Mascot visible onOpen={() => {}} rng={fixed(0.5)} />);
    down(btn(), 950, 700);
    move(btn(), 500, 300);
    up(btn(), 500, 300);
    expect(btn().dataset.mode).toBe("FALL");
    tick(1500);
    expect(pos()[1]).toBe(768 - SIZE); // 바닥
    expect(["LAND", "IDLE", "WALK"]).toContain(btn().dataset.mode);
  });

  it("포인터가 취소되면 던지지 않고 안전하게 떨어진다", () => {
    render(<Mascot visible onOpen={() => {}} rng={fixed(0.5)} />);
    down(btn(), 950, 700);
    move(btn(), 500, 300);
    fireEvent.pointerCancel(btn(), { pointerId: 1 });
    expect(btn().dataset.mode).toBe("FALL");
    tick(1500);
    expect(pos()[1]).toBe(768 - SIZE);
  });
});

describe("마스코트: 돌아다니기", () => {
  it("시간이 지나면 화면 가장자리를 따라 움직인다", () => {
    render(<Mascot visible onOpen={() => {}} rng={fixed(0.5)} />);
    const first = pos();
    tick(6000);
    expect(pos()).not.toEqual(first);
  });

  it("오래 돌아다녀도 화면 밖으로 나가지 않는다", () => {
    render(<Mascot visible onOpen={() => {}} rng={fixed(0.5)} />);
    for (let i = 0; i < 400; i++) {
      tick(160);
      const [x, y] = pos();
      expect(x).toBeGreaterThanOrEqual(-1e-6);
      expect(y).toBeGreaterThanOrEqual(-1e-6);
      expect(x).toBeLessThanOrEqual(1024 - SIZE + 1e-6);
      expect(y).toBeLessThanOrEqual(768 - SIZE + 1e-6);
    }
  });

  it("보이지 않게 되면 멈추고, 다시 보이면 우하단에서 새로 나타난다", () => {
    const { rerender } = render(<Mascot visible onOpen={() => {}} rng={fixed(0.5)} />);
    tick(6000);
    expect(pos()).not.toEqual([926, 692]);
    rerender(<Mascot visible={false} onOpen={() => {}} rng={fixed(0.5)} />);
    expect(screen.queryByRole("button", { name: "에이전트 열기" })).toBeNull();
    expect(() => tick(1000)).not.toThrow();
    rerender(<Mascot visible onOpen={() => {}} rng={fixed(0.5)} />);
    expect(btn().style.transform).toBe(START);
  });

  it("탭이 숨으면 멈추고, 돌아오면 이어서 움직인다", () => {
    render(<Mascot visible onOpen={() => {}} rng={fixed(0.5)} />);
    tick(2500); // 쉬는 시간이 지나 걷는 중
    Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
    act(() => { document.dispatchEvent(new Event("visibilitychange")); });
    tick(500); // 이미 걸린 프레임이 끝나도록
    const frozen = pos();
    tick(3000);
    expect(pos()).toEqual(frozen);
    Reflect.deleteProperty(document, "hidden");
    act(() => { document.dispatchEvent(new Event("visibilitychange")); });
    tick(3000);
    expect(pos()).not.toEqual(frozen);
  });

  it("창 크기가 줄면 화면 안으로 끌어 넣는다", () => {
    render(<Mascot visible onOpen={() => {}} rng={fixed(0.5)} />);
    setViewport(500, 400);
    act(() => { window.dispatchEvent(new Event("resize")); });
    const [x, y] = pos();
    expect(x).toBeLessThanOrEqual(500 - SIZE);
    expect(y).toBeLessThanOrEqual(400 - SIZE);
  });

  it("떼어낼 때(unmount) 반복을 멈춘다", () => {
    const { unmount } = render(<Mascot visible onOpen={() => {}} rng={fixed(0.5)} />);
    tick(500);
    unmount();
    expect(() => tick(2000)).not.toThrow();
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("마스코트: 움직임 줄이기", () => {
  it("제자리에 두고 클릭만 받는다(끌어도 움직이지 않는다)", () => {
    installMedia({ [REDUCED_QUERY]: true });
    const onOpen = vi.fn();
    render(<Mascot visible onOpen={onOpen} rng={fixed(0.5)} />);
    tick(3000);
    expect(btn().style.transform).toBe(START); // 돌아다니지 않는다
    down(btn(), 950, 700);
    move(btn(), 500, 300);
    expect(btn().style.transform).toBe(START); // 끌려 가지 않는다
    up(btn(), 500, 300);
    expect(onOpen).toHaveBeenCalledTimes(1); // 대신 누른 것으로 친다
  });
});
