import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installMedia } from "../test/media";
import { REDUCED_QUERY } from "../agent/useMediaQuery";
import NoticeBanner, { ROLL_MS } from "./NoticeBanner";
import NoticeSticker from "./NoticeSticker";
import type { Notice } from "./notices";

const mk = (id: string, name: string, level: Notice["level"], ratio: number): Notice => ({
  key: `${id}|1|${level}`, siteId: id, name, stackCode: "1", level, ratio,
});
const three = [mk("A", "가공장", "exceed", 150), mk("B", "나공장", "exceed", 120), mk("C", "다공장", "exceed", 105)];

beforeEach(() => {
  window.sessionStorage.clear();
  installMedia({});
});
afterEach(() => vi.useRealTimers());

const track = (c: HTMLElement) => c.querySelector('[class*="track"]') as HTMLElement;

describe("롤링 배너", () => {
  it("항목이 없으면 아무것도 그리지 않는다", () => {
    const { container } = render(<NoticeBanner items={[]} onPick={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("초과 공지를 한 줄씩 세로로 굴리고(3.5초마다) 끝에서 끊김 없이 처음으로 돌아간다", async () => {
    vi.useFakeTimers();
    const { container } = render(<NoticeBanner items={three} onPick={() => {}} />);
    expect(track(container).style.transform).toContain("* 0)");
    expect(screen.getByText("1/3")).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(ROLL_MS); });
    expect(track(container).style.transform).toContain("* -1)");
    expect(screen.getByText("2/3")).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(ROLL_MS * 2); }); // 복제본(처음 항목)까지
    await act(async () => { await vi.advanceTimersByTimeAsync(600); }); // 움직임 없이 처음으로
    expect(track(container).style.transform).toContain("* 0)");
    expect(track(container)).toHaveAttribute("data-jump");
  });

  it("마우스를 올리면 멈추고 내리면 다시 굴러간다", async () => {
    vi.useFakeTimers();
    const { container } = render(<NoticeBanner items={three} onPick={() => {}} />);
    const region = screen.getByRole("region", { name: "초과 공지" });
    fireEvent.mouseEnter(region);
    await act(async () => { await vi.advanceTimersByTimeAsync(ROLL_MS * 3); });
    expect(track(container).style.transform).toContain("* 0)");
    fireEvent.mouseLeave(region);
    await act(async () => { await vi.advanceTimersByTimeAsync(ROLL_MS); });
    expect(track(container).style.transform).toContain("* -1)");
  });

  it("키보드로 초점이 가도 멈춘다", async () => {
    vi.useFakeTimers();
    const { container } = render(<NoticeBanner items={three} onPick={() => {}} />);
    fireEvent.focus(screen.getAllByRole("button", { name: /가공장/ })[0]);
    await act(async () => { await vi.advanceTimersByTimeAsync(ROLL_MS * 2); });
    expect(track(container).style.transform).toContain("* 0)");
  });

  it("항목을 누르면 그 사업장·굴뚝을 고른다(복제본은 누를 수 없다)", async () => {
    const onPick = vi.fn();
    render(<NoticeBanner items={three} onPick={onPick} />);
    await userEvent.click(screen.getAllByRole("button", { name: /나공장/ })[0]);
    expect(onPick).toHaveBeenCalledWith(three[1]);
    expect(screen.getAllByRole("button", { name: /가공장/ })).toHaveLength(1); // 접근성 트리에는 복제본이 없다
  });

  it("항목이 하나면 굴리지 않고 개수도 보이지 않는다", async () => {
    vi.useFakeTimers();
    const { container } = render(<NoticeBanner items={[three[0]]} onPick={() => {}} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(ROLL_MS * 3); });
    expect(track(container).style.transform).toBe("");
    expect(screen.queryByText(/\/1/)).toBeNull();
  });

  it("움직임 줄이기 설정에서는 굴리지 않고 ‹ › 로 넘긴다", async () => {
    installMedia({ [REDUCED_QUERY]: true });
    render(<NoticeBanner items={three} onPick={() => {}} />);
    expect(screen.getByRole("button", { name: /가공장/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /나공장/ })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "다음 공지" }));
    expect(screen.getByRole("button", { name: /나공장/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "이전 공지" }));
    await userEvent.click(screen.getByRole("button", { name: "이전 공지" }));
    expect(screen.getByRole("button", { name: /다공장/ })).toBeInTheDocument(); // 처음에서 이전은 끝으로
  });
});

describe("스티커(즐겨찾기 공지)", () => {
  const fav = [mk("A", "가공장", "exceed", 150), mk("B", "나공장", "risk", 95)];

  it("즐겨찾기 사업장을 칩으로 보여 주고 누르면 그 사업장을 고른다", async () => {
    const onPick = vi.fn();
    render(<NoticeSticker items={fav} onPick={onPick} />);
    expect(screen.getByRole("region", { name: "내 즐겨찾기 알림" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /나공장/ }));
    expect(onPick).toHaveBeenCalledWith(fav[1]);
  });

  it("X로 닫으면 사라지고 이번 탭 동안 기억한다", async () => {
    const { unmount } = render(<NoticeSticker items={fav} onPick={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "즐겨찾기 알림 닫기" }));
    expect(screen.queryByRole("region", { name: "내 즐겨찾기 알림" })).toBeNull();
    unmount();
    render(<NoticeSticker items={fav} onPick={() => {}} />); // 다시 그려도 닫힌 채
    expect(screen.queryByRole("region", { name: "내 즐겨찾기 알림" })).toBeNull();
  });

  it("닫은 뒤 새 공지(새 굴뚝·더 나빠진 단계)가 생기면 다시 나온다", async () => {
    const { rerender } = render(<NoticeSticker items={fav} onPick={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "즐겨찾기 알림 닫기" }));
    rerender(<NoticeSticker items={[...fav, mk("C", "다공장", "exceed", 110)]} onPick={() => {}} />);
    expect(screen.getByRole("region", { name: "내 즐겨찾기 알림" })).toBeInTheDocument();
  });

  it("항목이 없으면 그리지 않는다", () => {
    const { container } = render(<NoticeSticker items={[]} onPick={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });
});
