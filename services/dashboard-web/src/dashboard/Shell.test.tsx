import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "../theme/theme";
import Shell, { type ShellProps } from "./Shell";
import LevelMark from "./LevelMark";

function setup(props: Partial<ShellProps> = {}) {
  const onLogout = vi.fn();
  render(
    <ThemeProvider>
      <Shell email="a@b.com" onLogout={onLogout} {...props} />
    </ThemeProvider>,
  );
  return { onLogout };
}

describe("관제 화면 공통 틀", () => {
  it("머리·레일·푸터가 있고 지표 카드는 4개(정상 제외)다", () => {
    setup();
    expect(screen.getByRole("heading", { level: 1, name: "굴뚝 통합 관제" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "주 메뉴" })).toBeInTheDocument();
    const cards = screen.getByRole("region", { name: "단계별 굴뚝 수" });
    for (const label of ["주의", "경고", "위험", "초과"]) {
      expect(within(cards).getByText(label)).toBeInTheDocument();
    }
    expect(within(cards).queryByText("정상")).toBeNull();
  });

  it("푸터에 단계 기준과 보관 기록 안내가 있다", () => {
    setup();
    expect(screen.getByText(/주의 ≥70%.*초과 ≥100%/)).toBeInTheDocument();
    expect(screen.getByText(/법적 판정 아님/)).toBeInTheDocument();
  });

  it("데이터가 없으면 값 자리는 0이 아니라 —로 둔다", () => {
    setup();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(4);
    expect(screen.getByText(/데이터 연결 전/)).toBeInTheDocument();
  });

  it("경고 건수가 있으면 접근성 이름에 건수가 들어간다", () => {
    setup({ alertCount: 3 });
    expect(screen.getByRole("link", { name: "경고 목록, 3건" })).toBeInTheDocument();
  });

  it("테마 버튼으로 전환된다", async () => {
    setup();
    await userEvent.click(screen.getByRole("button", { name: "라이트 모드로 전환" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(screen.getByRole("button", { name: "다크 모드로 전환" })).toBeInTheDocument();
  });

  it("로그아웃 버튼이 콜백을 부른다", async () => {
    const { onLogout } = setup();
    await userEvent.click(screen.getByRole("button", { name: "로그아웃" }));
    expect(onLogout).toHaveBeenCalledOnce();
  });

  it("본문 건너뛰기 링크가 있다", () => {
    setup();
    expect(screen.getByRole("link", { name: "본문으로 건너뛰기" })).toHaveAttribute("href", "#main");
  });
});

describe("LevelMark", () => {
  it("단계마다 모양이 다르다(색만으로 구분하지 않는다)", () => {
    const shapes = (["ok", "caution", "warn", "risk", "exceed"] as const).map((level) => {
      const { container, unmount } = render(<LevelMark level={level} />);
      const html = container.querySelector("svg")!.innerHTML;
      unmount();
      return html;
    });
    expect(new Set(shapes).size).toBe(5);
  });
});

describe("레일", () => {
  it("통합 관제를 누르면 지도가 아니라 맨 위로 올라간다", async () => {
    const scrollTo = vi.fn();
    window.scrollTo = scrollTo as unknown as typeof window.scrollTo;
    setup();
    await userEvent.click(screen.getByRole("button", { name: /통합 관제/ }));
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" });
  });
});

describe("에이전트", () => {
  it("화면에 에이전트 열기 버튼이 있고, 누르면 대화 창이 열린다", async () => {
    setup();
    await userEvent.click(screen.getByRole("button", { name: "에이전트 열기" }));
    expect(screen.getByRole("dialog", { name: "에이전트 대화" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "에이전트 열기" })).toBeNull();
  });
});

describe("톱니바퀴(그래프 설정) 버튼", () => {
  it("열기 함수를 줄 때만 왼쪽 레일에 나타난다", () => {
    setup();
    expect(screen.queryByRole("button", { name: "그래프 설정" })).toBeNull();
  });
  it("누르면 열기 함수를 부르고, 열려 있으면 눌림 상태로 보인다", async () => {
    const onOpenSettings = vi.fn();
    setup({ onOpenSettings, settingsOpen: false });
    const gear = screen.getByRole("button", { name: "그래프 설정" });
    expect(within(screen.getByRole("navigation", { name: "주 메뉴" })).getByRole("button", { name: "그래프 설정" })).toBe(gear);
    expect(gear).toHaveAttribute("aria-expanded", "false");
    expect(gear).toHaveAttribute("aria-haspopup", "dialog");
    await userEvent.click(gear);
    expect(onOpenSettings).toHaveBeenCalledTimes(1);
  });
  it("열려 있으면 aria-expanded가 참이다", () => {
    setup({ onOpenSettings: () => {}, settingsOpen: true });
    expect(screen.getByRole("button", { name: "그래프 설정" })).toHaveAttribute("aria-expanded", "true");
  });
});

