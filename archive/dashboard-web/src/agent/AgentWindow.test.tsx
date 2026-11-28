import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installMedia, setViewport } from "../test/media";
import AgentWindow from "./AgentWindow";
import { KEYS } from "./prefs";
import { WIDE_QUERY } from "./useMediaQuery";

// 창 1024×768(시험 기본). 기본 위치: 오른쪽 위 16px 여백, 폭 430, 높이 768-32=736 → x=578, y=16
const dialog = () => screen.getByRole("dialog", { name: "에이전트 대화" });
const header = () => dialog().firstElementChild as HTMLElement;
const edge = (e: string) => dialog().querySelector(`[data-edge="${e}"]`) as HTMLElement;
const grip = () => screen.getByRole("button", { name: /창 이동 손잡이/ });
const box = () => ({ left: dialog().style.left, top: dialog().style.top, width: dialog().style.width, height: dialog().style.height });
const saved = () => JSON.parse(window.localStorage.getItem(KEYS.rect) ?? "null");

const down = (el: Element, x: number, y: number) => fireEvent.pointerDown(el, { button: 0, clientX: x, clientY: y, pointerId: 1 });
const move = (el: Element, x: number, y: number) => fireEvent.pointerMove(el, { clientX: x, clientY: y, pointerId: 1 });
const up = (el: Element, x = 0, y = 0) => fireEvent.pointerUp(el, { button: 0, clientX: x, clientY: y, pointerId: 1 });
/** (x0,y0)에서 눌러 (x1,y1)까지 끌고 놓는다 */
const drag = (el: Element, [x0, y0]: [number, number], [x1, y1]: [number, number]) => { down(el, x0, y0); move(el, x1, y1); up(el, x1, y1); };

function open(props: Partial<React.ComponentProps<typeof AgentWindow>> = {}) {
  const onClose = vi.fn();
  const onMascotChange = vi.fn();
  render(<AgentWindow onClose={onClose} mascotOn={false} onMascotChange={onMascotChange} {...props} />);
  return { onClose, onMascotChange };
}

beforeEach(() => { installMedia({ [WIDE_QUERY]: true }); });
afterEach(() => vi.useRealTimers());

describe("에이전트 창: 모양", () => {
  it("대화 창이 열리고 제목·환영 문구·시작 질문·입력칸이 있다", () => {
    open();
    expect(dialog()).toBeInTheDocument();
    expect(within(dialog()).getByText("에이전트")).toBeInTheDocument();
    expect(within(dialog()).getByText("무엇을 확인할까요?")).toBeInTheDocument();
    expect(within(dialog()).getAllByRole("button", { name: /굴뚝|초과|기준/ }).length).toBeGreaterThanOrEqual(3);
    expect(screen.getByLabelText("질문 입력")).toHaveFocus();
  });

  it("넓은 화면에서는 이동 손잡이와 8방향 크기 조절 손잡이가 있다", () => {
    open();
    expect(grip()).toBeInTheDocument();
    expect(dialog().querySelectorAll("[data-edge]")).toHaveLength(8);
    expect(within(dialog()).getAllByRole("separator")).toHaveLength(4); // 가장자리 4곳은 키보드로도 조절한다
  });

  it("처음에는 기본 자리(CSS 기본)에 있고 인라인 위치를 쓰지 않는다", () => {
    open();
    expect(box()).toEqual({ left: "", top: "", width: "", height: "" });
    expect(dialog().dataset.moved).toBeUndefined();
  });

  it("닫기 버튼은 닫는다", () => {
    const { onClose } = open();
    fireEvent.click(screen.getByRole("button", { name: "에이전트 닫기" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("에이전트 창: 자유 이동", () => {
  it("머리(빈 곳)를 끌면 창이 옮겨지고 크기는 그대로다", () => {
    open();
    drag(header(), [700, 30], [600, 40]); // (-100, +10)
    expect(box()).toEqual({ left: "478px", top: "26px", width: "430px", height: "736px" });
    expect(dialog().dataset.moved).toBe("1");
  });

  it("왼쪽 위 손잡이로도 같은 방식으로 옮긴다", () => {
    open();
    drag(grip(), [600, 30], [610, 20]); // (+10, -10)
    expect(box().left).toBe("588px");
    expect(box().top).toBe("6px");
    drag(grip(), [600, 30], [650, 20]); // 오른쪽 끝(1024-430=594)을 넘지는 못한다
    expect(box().left).toBe("594px");
  });

  it("끌어도 창 전체가 화면 안에 머문다(어느 방향으로 끌어도)", () => {
    open();
    drag(header(), [700, 30], [-5000, -5000]);
    expect(box()).toMatchObject({ left: "0px", top: "0px" });
    drag(header(), [100, 30], [5000, 5000]);
    expect(box()).toMatchObject({ left: `${1024 - 430}px`, top: `${768 - 736}px` });
  });

  it("높이를 줄인 창은 위아래로도 자유롭게 옮긴다", () => {
    open();
    drag(edge("s"), [700, 750], [700, 550]); // 높이 536
    drag(header(), [700, 30], [700, 300]);
    expect(box().top).toBe("232px"); // 아래 끝 = 768 → y = 768-536
  });

  it("버튼 위에서 시작한 끌기는 이동이 아니다(닫기·전환 버튼이 눌린다)", () => {
    open();
    drag(screen.getByRole("button", { name: "에이전트 닫기" }), [900, 30], [500, 300]);
    expect(box().left).toBe("");
  });

  it("끌기가 끝나면 위치를 저장하고, 다시 열면 그 자리에서 열린다", () => {
    const first = render(<AgentWindow onClose={() => {}} mascotOn={false} onMascotChange={() => {}} />);
    drag(header(), [700, 30], [600, 40]);
    expect(saved()).toEqual({ x: 478, y: 26, w: 430, h: 736 });
    first.unmount();
    open();
    expect(box()).toEqual({ left: "478px", top: "26px", width: "430px", height: "736px" });
  });

  it("누르기만 하고 움직이지 않으면 저장하지 않는다", () => {
    open();
    down(header(), 700, 30);
    up(header(), 700, 30);
    expect(window.localStorage.getItem(KEYS.rect)).toBeNull();
  });

  it("손잡이를 두 번 누르거나 Home을 누르면 원래 자리로 돌아간다", () => {
    open();
    drag(header(), [700, 30], [600, 40]);
    fireEvent.doubleClick(grip());
    expect(box().left).toBe("");
    expect(window.localStorage.getItem(KEYS.rect)).toBeNull();
    drag(header(), [700, 30], [600, 40]);
    fireEvent.keyDown(grip(), { key: "Home" });
    expect(box().left).toBe("");
  });

  it("방향키로 조금씩(16px), Shift와 함께면 크게(64px) 옮기고 저장한다", () => {
    open();
    fireEvent.keyDown(grip(), { key: "ArrowLeft" });
    expect(box().left).toBe("562px"); // 578-16
    fireEvent.keyDown(grip(), { key: "ArrowDown", shiftKey: true });
    expect(box().top).toBe("32px"); // 16+64 → 아래 끝 제한(768-736)
    expect(saved()).toMatchObject({ x: 562, y: 32 });
    fireEvent.keyDown(grip(), { key: "a" }); // 다른 키는 무시
    expect(box().left).toBe("562px");
  });

  it("저장된 위치로 열리고, 저장값이 망가졌으면 기본 자리로 연다", () => {
    window.localStorage.setItem(KEYS.rect, JSON.stringify({ x: 100, y: 60, w: 500, h: 600 }));
    const { unmount } = render(<AgentWindow onClose={() => {}} mascotOn={false} onMascotChange={() => {}} />);
    expect(box()).toEqual({ left: "100px", top: "60px", width: "500px", height: "600px" });
    unmount();
    window.localStorage.setItem(KEYS.rect, "{깨짐");
    open();
    expect(box().left).toBe("");
  });

  it("화면이 줄어들면 저장된 창을 안으로 끌어 넣는다", () => {
    window.localStorage.setItem(KEYS.rect, JSON.stringify({ x: 500, y: 40, w: 500, h: 700 }));
    open();
    setViewport(700, 500);
    act(() => { window.dispatchEvent(new Event("resize")); });
    const r = saved();
    expect(r.x + r.w).toBeLessThanOrEqual(700);
    expect(r.y + r.h).toBeLessThanOrEqual(500);
  });

  it("끄는 도중에 창이 사라져도 오류 없이 정리된다", () => {
    const { unmount } = render(<AgentWindow onClose={() => {}} mascotOn={false} onMascotChange={() => {}} />);
    down(header(), 700, 30);
    unmount();
    expect(() => { move(document.body, 600, 40); up(document.body, 600, 40); }).not.toThrow();
  });
});

describe("에이전트 창: 자유 크기 조절(상하 포함, 새 기능)", () => {
  it("아래쪽 가장자리를 끌면 높이만 바뀐다", () => {
    open();
    drag(edge("s"), [700, 750], [700, 550]);
    expect(box()).toEqual({ left: "578px", top: "16px", width: "430px", height: "536px" });
  });

  it("위쪽 가장자리를 끌면 아래쪽은 그대로 두고 높이가 바뀐다", () => {
    open();
    drag(edge("n"), [700, 20], [700, 120]); // 아래로 100
    expect(box()).toMatchObject({ top: "116px", height: "636px", width: "430px", left: "578px" });
  });

  it("왼쪽 가장자리를 바깥으로 끌면 폭이 늘고 오른쪽 끝은 그대로다", () => {
    open();
    drag(edge("w"), [580, 300], [480, 300]);
    expect(box()).toMatchObject({ left: "478px", width: "530px", height: "736px" });
  });

  it("오른쪽 가장자리를 끌면 폭이 바뀐다(화면 끝에서 멈춘다)", () => {
    open();
    drag(edge("w"), [580, 300], [380, 300]); // 먼저 넓힌다
    drag(edge("e"), [1000, 300], [1200, 300]);
    expect(Number.parseInt(box().left, 10) + Number.parseInt(box().width, 10)).toBeLessThanOrEqual(1024);
  });

  it("모서리를 끌면 폭과 높이가 함께 바뀐다", () => {
    open();
    drag(edge("sw"), [580, 750], [530, 650]); // 왼쪽으로 50 더(폭 +50), 위로 100(높이 -100)
    expect(box()).toEqual({ left: "528px", top: "16px", width: "480px", height: "636px" });
  });

  it("오른쪽 위 모서리는 왼쪽 아래를 고정하고, 왼쪽 위는 오른쪽 아래를 고정한다", () => {
    open();
    drag(edge("ne"), [1000, 20], [1000, 120]);
    expect(box()).toMatchObject({ top: "116px", height: "636px", left: "578px" });
    drag(edge("nw"), [580, 120], [480, 100]);
    const r = saved();
    expect(r.x + r.w).toBe(1008); // 오른쪽 끝 고정
    expect(r.y + r.h).toBe(752); // 아래쪽 끝 고정
  });

  it("최소 크기 아래로 줄지 않는다(폭 320, 높이 240)", () => {
    open();
    drag(edge("se"), [1000, 750], [-5000, -5000]);
    expect(box()).toMatchObject({ width: "320px", height: "240px" });
  });

  it("화면 밖으로 키우지 않는다", () => {
    open();
    drag(edge("s"), [700, 750], [700, 5000]);
    expect(Number.parseInt(box().top, 10) + Number.parseInt(box().height, 10)).toBeLessThanOrEqual(768);
    drag(edge("n"), [700, 20], [700, -5000]);
    expect(Number.parseInt(box().top, 10)).toBeGreaterThanOrEqual(0);
  });

  it("크기도 저장하고 다시 열면 그대로다", () => {
    const first = render(<AgentWindow onClose={() => {}} mascotOn={false} onMascotChange={() => {}} />);
    drag(edge("s"), [700, 750], [700, 550]);
    expect(saved()).toEqual({ x: 578, y: 16, w: 430, h: 536 });
    first.unmount();
    open();
    expect(box().height).toBe("536px");
  });

  it("방향키로 크기를 미세 조절한다(그 손잡이가 담당하는 방향만)", () => {
    open();
    fireEvent.keyDown(edge("s"), { key: "ArrowUp" }); // 아래 손잡이에서 위쪽 키 → 줄어든다
    expect(box().height).toBe("720px");
    fireEvent.keyDown(edge("s"), { key: "ArrowLeft" }); // 가로 키는 이 손잡이의 일이 아니다
    expect(box().width).toBe("430px");
    fireEvent.keyDown(edge("w"), { key: "ArrowLeft" }); // 왼쪽 손잡이를 바깥으로 → 넓어진다
    expect(box()).toMatchObject({ width: "446px", left: "562px" });
    fireEvent.keyDown(edge("s"), { key: "ArrowDown", shiftKey: true });
    expect(saved().h).toBeGreaterThan(720);
  });

  it("가장자리를 두 번 누르면 그 방향만 기본 크기로 돌아간다", () => {
    open();
    drag(edge("s"), [700, 750], [700, 550]); // 높이 536
    drag(edge("w"), [580, 300], [480, 300]); // 폭 530
    fireEvent.doubleClick(edge("s"));
    expect(box().height).toBe("736px"); // 높이만 기본으로
    expect(box().width).toBe("530px"); // 폭은 그대로
    fireEvent.doubleClick(edge("w"));
    expect(box().width).toBe("430px");
  });
});

describe("에이전트 창: 전체 모드와 키보드", () => {
  it("화살표 버튼으로 전체 ↔ 사이드를 바꾸고 모드를 저장한다", async () => {
    open();
    await userEvent.click(screen.getByRole("button", { name: "전체 창으로 넓히기" }));
    expect(dialog().dataset.mode).toBe("full");
    expect(window.localStorage.getItem(KEYS.mode)).toBe("full");
    expect(screen.getByRole("button", { name: "사이드 창으로 줄이기" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "사이드 창으로 줄이기" }));
    expect(dialog().dataset.mode).toBe("side");
  });

  it("전체 모드에서는 이동·크기 조절 손잡이가 없고, 저장된 위치도 쓰지 않는다", async () => {
    window.localStorage.setItem(KEYS.rect, JSON.stringify({ x: 100, y: 60, w: 500, h: 600 }));
    open();
    expect(box().left).toBe("100px");
    await userEvent.click(screen.getByRole("button", { name: "전체 창으로 넓히기" }));
    expect(dialog().querySelectorAll("[data-edge]")).toHaveLength(0);
    expect(screen.queryByRole("button", { name: /창 이동 손잡이/ })).toBeNull();
    expect(box().left).toBe(""); // 전체 모드는 화면 전체
    await userEvent.click(screen.getByRole("button", { name: "사이드 창으로 줄이기" }));
    expect(box().left).toBe("100px"); // 돌아오면 저장된 자리
  });

  it("Esc: 전체 모드에서는 사이드로, 사이드에서는 닫는다", async () => {
    const { onClose } = open();
    await userEvent.click(screen.getByRole("button", { name: "전체 창으로 넓히기" }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(dialog().dataset.mode).toBe("side");
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("저장된 전체 모드로 열린다", () => {
    window.localStorage.setItem(KEYS.mode, "full");
    open();
    expect(dialog().dataset.mode).toBe("full");
  });
});

describe("에이전트 창: 좁은 화면", () => {
  beforeEach(() => { installMedia({ [WIDE_QUERY]: false }); });

  it("이동·크기 조절 손잡이가 없고 머리를 끌어도 옮겨지지 않는다(전체 시트)", () => {
    open();
    expect(screen.queryByRole("button", { name: /창 이동 손잡이/ })).toBeNull();
    expect(dialog().querySelectorAll("[data-edge]")).toHaveLength(0);
    drag(header(), [300, 30], [100, 200]);
    expect(box().left).toBe("");
    expect(window.localStorage.getItem(KEYS.rect)).toBeNull();
  });

  it("저장된 위치가 있어도 좁은 화면에서는 쓰지 않는다", () => {
    window.localStorage.setItem(KEYS.rect, JSON.stringify({ x: 100, y: 60, w: 500, h: 600 }));
    open();
    expect(box().left).toBe("");
  });

  it("화면이 넓어지면 손잡이가 생긴다", () => {
    const m = installMedia({ [WIDE_QUERY]: false });
    open();
    expect(dialog().querySelectorAll("[data-edge]")).toHaveLength(0);
    act(() => m.set(WIDE_QUERY, true));
    expect(dialog().querySelectorAll("[data-edge]")).toHaveLength(8);
  });
});

describe("에이전트 창: 대화 틀(아직 모델에 연결하지 않음)", () => {
  it("질문을 보내면 내 말이 남고, 곧 '아직 연결되지 않았습니다' 안내가 나온다", () => {
    vi.useFakeTimers();
    open();
    const input = screen.getByLabelText("질문 입력");
    fireEvent.change(input, { target: { value: "오늘 초과한 굴뚝은?" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(within(dialog()).getByText("오늘 초과한 굴뚝은?")).toBeInTheDocument();
    expect(within(dialog()).queryByText("무엇을 확인할까요?")).toBeNull(); // 환영 문구는 사라진다
    expect(within(dialog()).queryByText("에이전트가 아직 연결되지 않았습니다.")).toBeNull();
    act(() => { vi.advanceTimersByTime(400); });
    expect(within(dialog()).getByText("에이전트가 아직 연결되지 않았습니다.")).toBeInTheDocument();
    expect(within(dialog()).getByText(/어디로도 전송되지 않습니다/)).toBeInTheDocument();
    expect((input as HTMLTextAreaElement).value).toBe("");
  });

  it("Shift+Enter(줄바꿈)와 빈 입력은 보내지 않는다", () => {
    open();
    const input = screen.getByLabelText("질문 입력");
    fireEvent.change(input, { target: { value: "줄바꿈" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(within(screen.getByRole("log")).queryByText("줄바꿈")).toBeNull(); // 대화 기록에는 없다(입력칸에만 있다)
    fireEvent.change(input, { target: { value: "   " } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(within(dialog()).getByText("무엇을 확인할까요?")).toBeInTheDocument();
  });

  it("시작 질문을 누르면 입력칸에 채워진다", async () => {
    open();
    await userEvent.click(within(dialog()).getByRole("button", { name: "오늘 초과한 굴뚝을 알려줘" }));
    expect((screen.getByLabelText("질문 입력") as HTMLTextAreaElement).value).toBe("오늘 초과한 굴뚝을 알려줘");
  });

  it("보내기 버튼으로도 보낸다", () => {
    open();
    fireEvent.change(screen.getByLabelText("질문 입력"), { target: { value: "안녕" } });
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));
    expect(within(dialog()).getByText("안녕")).toBeInTheDocument();
  });
});

describe("에이전트 창: 화면 돌아다니기(마스코트) 스위치", () => {
  it("현재 상태를 보여 준다", () => {
    open({ mascotOn: true });
    expect(screen.getByRole("switch", { name: "화면 돌아다니기" })).toHaveAttribute("aria-checked", "true");
  });

  it("누르면 바꾸라고 알린다", () => {
    const { onMascotChange } = open({ mascotOn: false });
    const sw = screen.getByRole("switch", { name: "화면 돌아다니기" });
    expect(sw).toHaveAttribute("aria-checked", "false");
    fireEvent.click(sw);
    expect(onMascotChange).toHaveBeenCalledWith(true);
  });

  it("스위치는 창 머리(제목 줄) 안에 있고 따로 한 줄을 차지하지 않는다", () => {
    open();
    const sw = screen.getByRole("switch", { name: "화면 돌아다니기" });
    expect(header().contains(sw)).toBe(true);
    // 머리 다음 줄은 바로 대화 영역이다(설정 줄이 없다)
    expect(header().nextElementSibling).toBe(screen.getByRole("log"));
    // 길었던 설명 문구는 줄로 두지 않고 마우스를 올리면 보이는 안내로만 둔다
    expect(within(dialog()).queryByText(/켜면 창을 닫았을 때 마스코트가/)).toBeNull();
    expect(sw.closest("label")).toHaveAttribute("title", expect.stringContaining("화면 가장자리를 돌아다닙니다"));
  });

  it("머리 글자 '돌아다니기'를 눌러도 스위치가 눌린다", () => {
    const { onMascotChange } = open();
    fireEvent.click(within(dialog()).getByText("돌아다니기"));
    expect(onMascotChange).toHaveBeenCalledWith(true);
  });

  it("머리에서 스위치를 눌러도 창이 끌려 다니지 않는다(버튼 위에서 시작한 끌기는 이동이 아니다)", () => {
    open();
    drag(screen.getByRole("switch", { name: "화면 돌아다니기" }), [800, 30], [300, 300]);
    expect(box().left).toBe("");
  });
});

