import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installMedia } from "../test/media";
import AgentDock from "./AgentDock";
import { KEYS } from "./prefs";
import { NARROW_QUERY, REDUCED_QUERY, WIDE_QUERY } from "./useMediaQuery";

const openButton = () => screen.queryByRole("button", { name: "에이전트 열기" });
const launcher = (c: HTMLElement) => c.querySelector('button[class*="launcher"]');
const mascot = (c: HTMLElement) => c.querySelector('button[class*="mascot"]');
const dialog = () => screen.queryByRole("dialog", { name: "에이전트 대화" });

beforeEach(() => {
  installMedia({ [WIDE_QUERY]: true });
  window.history.replaceState(null, "", "/");
});
afterEach(() => {
  vi.useRealTimers();
  window.history.replaceState(null, "", "/");
});

describe("에이전트 열기: 마스코트가 꺼져 있을 때(기본, 옛 웹과 같음)", () => {
  it("우하단에 고정된 열기 버튼이 있고 창·마스코트는 없다", () => {
    const { container } = render(<AgentDock />);
    expect(launcher(container)).not.toBeNull();
    expect(mascot(container)).toBeNull();
    expect(dialog()).toBeNull();
    expect(openButton()).toHaveAttribute("aria-expanded", "false");
  });

  it("누르면 창이 열리고 버튼은 숨는다", async () => {
    const { container } = render(<AgentDock />);
    await userEvent.click(openButton()!);
    expect(dialog()).toBeInTheDocument();
    expect(launcher(container)).toBeNull();
  });

  it("창을 닫으면 버튼이 돌아오고 초점도 그 버튼으로 간다", async () => {
    const { container } = render(<AgentDock />);
    await userEvent.click(openButton()!);
    await userEvent.click(screen.getByRole("button", { name: "에이전트 닫기" }));
    expect(dialog()).toBeNull();
    expect(launcher(container)).not.toBeNull();
    expect(openButton()).toHaveFocus();
  });

  it("Esc로도 닫힌다(사이드 창에서)", async () => {
    render(<AgentDock />);
    await userEvent.click(openButton()!);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(dialog()).toBeNull();
    expect(openButton()).toBeInTheDocument();
  });
});

describe("에이전트 열기: 마스코트(화면 돌아다니기)", () => {
  it("켜져 있으면 고정 버튼 대신 마스코트가 나타난다", () => {
    window.localStorage.setItem(KEYS.mascot, "on");
    const { container } = render(<AgentDock />);
    expect(mascot(container)).not.toBeNull();
    expect(launcher(container)).toBeNull();
  });

  it("마스코트를 누르면 창이 열리고, 창이 열려 있는 동안은 숨는다", async () => {
    window.localStorage.setItem(KEYS.mascot, "on");
    const { container } = render(<AgentDock />);
    const m = mascot(container)!;
    fireEvent.pointerDown(m, { button: 0, clientX: 950, clientY: 700, pointerId: 1 });
    fireEvent.pointerUp(m, { button: 0, clientX: 950, clientY: 700, pointerId: 1 });
    expect(dialog()).toBeInTheDocument();
    expect(mascot(container)).toBeNull();
    expect(launcher(container)).toBeNull(); // 열려 있을 때는 고정 버튼도 없다
  });

  it("창을 닫으면 마스코트가 우하단에서 다시 나타난다", async () => {
    window.localStorage.setItem(KEYS.mascot, "on");
    const { container } = render(<AgentDock />);
    fireEvent.keyDown(mascot(container)!, { key: "Enter" });
    await userEvent.click(screen.getByRole("button", { name: "에이전트 닫기" }));
    expect(dialog()).toBeNull();
    expect(mascot(container)).not.toBeNull();
    expect((mascot(container) as HTMLElement).style.transform).toBe("translate3d(926.0px,692.0px,0)");
  });

  it("창 안의 '화면 돌아다니기' 스위치로 켜면 저장되고, 창을 닫으면 마스코트가 나온다", async () => {
    const { container } = render(<AgentDock />);
    await userEvent.click(openButton()!);
    const sw = screen.getByRole("switch", { name: "화면 돌아다니기" });
    expect(sw).toHaveAttribute("aria-checked", "false");
    await userEvent.click(sw);
    expect(sw).toHaveAttribute("aria-checked", "true");
    expect(window.localStorage.getItem(KEYS.mascot)).toBe("on");
    await userEvent.click(screen.getByRole("button", { name: "에이전트 닫기" }));
    expect(mascot(container)).not.toBeNull();
    expect(launcher(container)).toBeNull();
  });

  it("스위치로 끄면 저장이 지워지고 고정 버튼으로 돌아간다", async () => {
    window.localStorage.setItem(KEYS.mascot, "on");
    const { container } = render(<AgentDock />);
    fireEvent.keyDown(mascot(container)!, { key: "Enter" });
    await userEvent.click(screen.getByRole("switch", { name: "화면 돌아다니기" }));
    expect(window.localStorage.getItem(KEYS.mascot)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "에이전트 닫기" }));
    expect(launcher(container)).not.toBeNull();
    expect(mascot(container)).toBeNull();
  });

  it("좁은 화면(540px 이하)에서는 켜 두어도 고정 버튼이다", () => {
    installMedia({ [WIDE_QUERY]: false, [NARROW_QUERY]: true });
    window.localStorage.setItem(KEYS.mascot, "on");
    const { container } = render(<AgentDock />);
    expect(launcher(container)).not.toBeNull();
    expect(mascot(container)).toBeNull();
  });

  it("화면 폭이 바뀌면 따라간다(넓어지면 마스코트가 나타난다)", () => {
    const m = installMedia({ [WIDE_QUERY]: true, [NARROW_QUERY]: true });
    window.localStorage.setItem(KEYS.mascot, "on");
    const { container } = render(<AgentDock />);
    expect(launcher(container)).not.toBeNull();
    act(() => m.set(NARROW_QUERY, false));
    expect(mascot(container)).not.toBeNull();
    expect(launcher(container)).toBeNull();
  });

  it("주소의 ?mascot=off가 가장 우선이다(저장은 켬이어도 고정 버튼)", () => {
    window.localStorage.setItem(KEYS.mascot, "on");
    window.history.replaceState(null, "", "/?mascot=off");
    const { container } = render(<AgentDock />);
    expect(launcher(container)).not.toBeNull();
    expect(mascot(container)).toBeNull();
  });

  it("?mascot=on이면 저장 없이도 켠다", () => {
    window.history.replaceState(null, "", "/?mascot=on");
    const { container } = render(<AgentDock />);
    expect(mascot(container)).not.toBeNull();
  });

  it("움직임 줄이기 설정에서도 마스코트는 보이되 제자리에서 누르면 열린다", async () => {
    installMedia({ [WIDE_QUERY]: true, [REDUCED_QUERY]: true });
    window.localStorage.setItem(KEYS.mascot, "on");
    const { container } = render(<AgentDock />);
    const m = mascot(container)!;
    fireEvent.pointerDown(m, { button: 0, clientX: 950, clientY: 700, pointerId: 1 });
    fireEvent.pointerUp(m, { button: 0, clientX: 950, clientY: 700, pointerId: 1 });
    expect(dialog()).toBeInTheDocument();
  });
});

describe("에이전트 열기: 한 번에 하나만", () => {
  it("열기 버튼(또는 마스코트)은 어느 순간에도 하나만 있다", async () => {
    render(<AgentDock />);
    expect(screen.getAllByRole("button", { name: "에이전트 열기" })).toHaveLength(1);
    await userEvent.click(openButton()!);
    expect(screen.queryAllByRole("button", { name: "에이전트 열기" })).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "에이전트 닫기" }));
    expect(screen.getAllByRole("button", { name: "에이전트 열기" })).toHaveLength(1);
  });

  it("창은 동시에 둘이 열리지 않는다", async () => {
    render(<AgentDock />);
    await userEvent.click(openButton()!);
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(within(dialog()!).getByText("에이전트")).toBeInTheDocument();
  });
});
