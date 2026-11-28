import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as geometry from "./geometry";
import type { SiteState } from "../data/model";
import { initialSelection, MAP_SHOW_ORDER, useSelection } from "../state/selection";
import { ThemeProvider } from "../theme/theme";
import MapClock from "./MapClock";
import MapPanel from "./MapPanel";

vi.mock("./geometry", async (orig) => {
  const m = await orig<typeof import("./geometry")>();
  return { ...m, fitView: vi.fn(m.fitView) };
});

const times = Array.from({ length: 48 }, (_, i) => Date.UTC(2026, 10, 9, 15, 0) + i * 1800000);

beforeEach(() => {
  useSelection.setState({ ...initialSelection, mapLevels: [...MAP_SHOW_ORDER] });
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null); // jsdom에는 캔버스 그리기가 없다
  globalThis.fetch = vi.fn().mockRejectedValue(new Error("no network")) as unknown as typeof fetch;
});

describe("지도 시계(표시 전용)", () => {
  it("조작 요소(슬라이더·재생·이전/다음)가 없다", () => {
    render(<MapClock times={times} slot={47} />);
    expect(screen.queryByRole("slider")).toBeNull();
    expect(screen.queryByRole("button", { name: /재생|이전|다음|최신/ })).toBeNull();
  });

  it("12시간 시계: 오전/오후와 시·분 숫자판을 한국 시각으로 보여 준다", () => {
    render(<MapClock times={times} slot={47} />);
    expect(screen.getByRole("img", { name: "지도 시각 오후 11시 30분" })).toBeInTheDocument();
    const digits = screen.getByRole("group", { name: "지도 선택 날짜와 시간" });
    expect(digits).toHaveTextContent("2026");
    expect(digits).toHaveTextContent("23");
    expect(digits).toHaveTextContent("30");
    expect(screen.getByText("최신 보관")).toBeInTheDocument();
  });

  it("바늘은 화살촉 없는 막대이고 시각에 맞는 각도를 가리킨다(시침 15도/30분, 분침 180도=30분)", () => {
    const { container } = render(<MapClock times={times} slot={1} />); // 00:30
    expect(container.querySelector('[data-hand="hour"]')).toHaveAttribute("data-angle", "15");
    expect(container.querySelector('[data-hand="minute"]')).toHaveAttribute("data-angle", "180");
    // 화살촉(채운 삼각형)은 없고, 바늘마다 선 하나다. 시침은 짧고 굵으며 분침은 길고 가늘다
    expect(container.querySelectorAll('[data-hand] path[fill]').length).toBe(0);
    const hour = container.querySelector('[data-hand="hour"] path')!;
    const minute = container.querySelector('[data-hand="minute"] path')!;
    expect(container.querySelectorAll('[data-hand] path').length).toBe(2);
    expect(Number(hour.getAttribute("stroke-width"))).toBeGreaterThan(Number(minute.getAttribute("stroke-width")));
    const tip = (d: string | null) => Number(d!.match(/V(-?[\d.]+)/)![1]);
    expect(tip(minute.getAttribute("d"))).toBeLessThan(tip(hour.getAttribute("d"))); // 분침 끝이 더 멀다(위쪽 y가 작다)
  });

  it("12·3·6·9는 로마 숫자(XII·III·VI·IX)로 보이고, 숫자 글자는 낭독에서 빠진다", () => {
    const { container } = render(<MapClock times={times} slot={1} />);
    const romans = [...container.querySelectorAll("text")].filter((t) => /^(XII|III|VI|IX)$/.test(t.textContent ?? ""));
    expect(romans.map((t) => t.textContent)).toEqual(["XII", "III", "VI", "IX"]);
    for (const t of romans) expect(t).toHaveAttribute("aria-hidden", "true");
    // 숫자는 눈금 자리(원 중심 100,100에서 같은 방향)에 서고, 그 자리의 눈금 선은 없다(8개만 남는다). 3·9는 세로 중심이 원의 중심 높이다
    const at = (label: string) => romans.find((t) => t.textContent === label)!;
    expect([at("XII"), at("VI")].map((t) => t.getAttribute("x"))).toEqual(["100", "100"]);
    expect([at("III"), at("IX")].map((t) => t.getAttribute("y"))).toEqual(["100", "100"]);
    expect(container.querySelectorAll("svg line").length).toBe(8);
    const arabic = [...container.querySelectorAll("svg text")].filter((t) => ["12", "3", "6", "9"].includes(t.textContent ?? ""));
    expect(arabic).toEqual([]); // 옛 아라비아 숫자판 글자는 없다
  });

  it("처음에는 넘기지 않고, 값이 바뀌면 플립이 돈다", () => {
    const { container, rerender } = render(<MapClock times={times} slot={46} />);
    expect(container.querySelector(".flip")).toBeNull();
    rerender(<MapClock times={times} slot={47} />);
    expect(container.querySelector(".flip")).not.toBeNull();
  });

  it("지난 시각이면 그렇게 표시하고, 접으면 작은 버튼이 된다", async () => {
    render(<MapClock times={times} slot={10} />);
    expect(screen.getByText("지난 시각")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "지도 시계 접기" }));
    expect(screen.getByRole("button", { name: "지도 시계 열기" })).toHaveTextContent("05:00");
  });
});

describe("지도", () => {
  const states: SiteState[] = [
    { site: { id: "A", name: "가", sido: "서울", sigungu: "중구", address: "", lon: 127, lat: 37.5, stacks: [] }, ratio: 95, level: "risk", worstStack: "1" },
  ];
  function Harness({ initial = 47 }: { initial?: number }) {
    const [slot, setSlot] = useState(initial);
    return (
      <ThemeProvider>
        <MapPanel states={states} geo={[]} times={times} slot={slot} onSlot={setSlot} />
      </ThemeProvider>
    );
  }

  it("휠이 페이지 스크롤로 새지 않는다(기본 동작을 막는다)", () => {
    render(<Harness />);
    const canvas = screen.getByRole("img", { name: /굴뚝 .*곳을 보여 주는 지도/ });
    expect(fireEvent.wheel(canvas, { deltaY: 120 })).toBe(false); // preventDefault가 불렸다
  });

  it("등고선은 기본이 꺼짐이고, 켜고 끌 수 있다", async () => {
    render(<Harness />);
    expect(screen.getByRole("button", { name: "등고선 끔" })).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(screen.getByRole("button", { name: "등고선 끔" }));
    expect(screen.getByRole("button", { name: "등고선 켬" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "등고선 켬" }));
    expect(screen.getByRole("button", { name: "등고선 끔" })).toHaveAttribute("aria-pressed", "false");
  });

  it("등고선 목록은 켤 때만 읽는다(꺼져 있으면 요청하지 않는다)", async () => {
    const f = vi.fn(() => Promise.resolve(new Response("{}", { status: 404 })));
    vi.stubGlobal("fetch", f);
    render(<Harness />);
    await new Promise((r) => setTimeout(r, 900)); // 한가할 때 읽는 시간(600ms)보다 오래 기다린다
    expect(f).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "등고선 끔" }));
    await waitFor(() => expect(f).toHaveBeenCalledTimes(1));
    expect(String((f.mock.calls[0] as unknown[])[0])).toContain("/contours/index.json");
    vi.unstubAllGlobals();
  });

  it("아래 슬라이더로 지도 시각을 바꾸고 최신으로 돌아온다", async () => {
    render(<Harness />);
    const slider = screen.getByLabelText("지도 시각");
    expect(slider).toHaveValue("47");
    fireEvent.change(slider, { target: { value: "10" } });
    expect(slider).toHaveValue("10");
    expect(screen.getByText("지난 시각")).toBeInTheDocument(); // 시계가 따라간다
    await userEvent.click(screen.getByRole("button", { name: "최신" }));
    expect(slider).toHaveValue("47");
    expect(screen.getByRole("button", { name: "최신" })).toBeDisabled();
  });

  describe("재생과 배속", () => {
    it("재생하면 한 칸씩 앞으로 가고 끝에서 멈춘다", () => {
      vi.useFakeTimers();
      try {
        render(<Harness initial={45} />);
        fireEvent.click(screen.getByRole("button", { name: "하루 흐름 재생" }));
        expect(screen.getByRole("button", { name: "재생 멈춤" })).toBeInTheDocument();
        act(() => { vi.advanceTimersByTime(1600); });
        expect(screen.getByLabelText("지도 시각")).toHaveValue("46");
        act(() => { vi.advanceTimersByTime(1600); });
        expect(screen.getByLabelText("지도 시각")).toHaveValue("47");
        expect(screen.getByRole("button", { name: "하루 흐름 재생" })).toBeInTheDocument(); // 끝에 닿자 멈춤
      } finally {
        vi.useRealTimers();
      }
    });

    it("배속 버튼을 누를 때마다 속도가 바뀌고 재생 간격이 따라 바뀐다", () => {
      vi.useFakeTimers();
      try {
        render(<Harness initial={0} />);
        const speed = () => screen.getByRole("button", { name: /^재생 속도/ });
        expect(speed()).toHaveTextContent("1×");
        fireEvent.click(speed());
        expect(speed()).toHaveTextContent("2×"); // 800ms마다 한 칸
        fireEvent.click(screen.getByRole("button", { name: "하루 흐름 재생" }));
        act(() => { vi.advanceTimersByTime(800 * 3); });
        expect(screen.getByLabelText("지도 시각")).toHaveValue("3");
        fireEvent.click(speed());
        expect(speed()).toHaveTextContent("4×");
        act(() => { vi.advanceTimersByTime(400 * 2); });
        expect(screen.getByLabelText("지도 시각")).toHaveValue("5");
        fireEvent.click(speed());
        fireEvent.click(speed());
        expect(speed()).toHaveTextContent("1×"); // 한 바퀴 돌아 처음으로
      } finally {
        vi.useRealTimers();
      }
    });

    it("끝에서 재생을 누르면 처음부터 시작한다", () => {
      vi.useFakeTimers();
      try {
        render(<Harness initial={47} />);
        fireEvent.click(screen.getByRole("button", { name: "하루 흐름 재생" }));
        expect(screen.getByLabelText("지도 시각")).toHaveValue("0");
        act(() => { vi.advanceTimersByTime(1600); });
        expect(screen.getByLabelText("지도 시각")).toHaveValue("1");
      } finally {
        vi.useRealTimers();
      }
    });

    it("슬라이더를 건드리거나 최신을 누르면 재생이 멈춘다", () => {
      vi.useFakeTimers();
      try {
        render(<Harness initial={5} />);
        fireEvent.click(screen.getByRole("button", { name: "하루 흐름 재생" }));
        fireEvent.change(screen.getByLabelText("지도 시각"), { target: { value: "20" } });
        expect(screen.getByRole("button", { name: "하루 흐름 재생" })).toBeInTheDocument();
        act(() => { vi.advanceTimersByTime(5000); });
        expect(screen.getByLabelText("지도 시각")).toHaveValue("20"); // 더 가지 않는다
        fireEvent.click(screen.getByRole("button", { name: "하루 흐름 재생" }));
        fireEvent.click(screen.getByRole("button", { name: "최신" }));
        expect(screen.getByRole("button", { name: "하루 흐름 재생" })).toBeInTheDocument();
      } finally {
        vi.useRealTimers();
      }
    });

    it("재생 중 시계 바늘은 다음 칸을 향해 한 칸 간격 동안 돈다", () => {
      vi.useFakeTimers();
      try {
        const { container } = render(<Harness initial={10} />); // 05:00
        const minute = () => container.querySelector('[data-hand="minute"]') as HTMLElement;
        const hour = () => container.querySelector('[data-hand="hour"]') as HTMLElement;
        expect(hour().style.transition).toContain("0.25s"); // 멈춰 있을 때는 짧게
        fireEvent.click(screen.getByRole("button", { name: "하루 흐름 재생" }));
        // 5:00 칸이지만 바늘은 5:30(다음 칸)을 향해 간다
        expect(minute()).toHaveAttribute("data-angle", "180");
        expect(hour().style.transition).toContain("1600ms linear");
        fireEvent.click(screen.getByRole("button", { name: /^재생 속도/ })); // 2×
        expect(hour().style.transition).toContain("800ms linear"); // 시계도 배속에 맞춘다
      } finally {
        vi.useRealTimers();
      }
    });
  });

  describe("지도 보기(확대·위치)", () => {
    const geoSeoul = [{
      name: "서울", type: "Polygon" as const,
      coordinates: [[[126.8, 37.4], [127.2, 37.4], [127.2, 37.7], [126.8, 37.7], [126.8, 37.4]]],
    }];
    // 전국 범위(한국 전체를 덮는 큰 상자): 크게 축소해도 이 범위까지는 줄일 수 있다
    const geoKorea = {
      name: "전국", type: "Polygon" as const,
      coordinates: [[[124.6, 33.0], [131.9, 33.0], [131.9, 38.7], [124.6, 38.7], [124.6, 33.0]]],
    };
    function setSize() {
      Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 800 });
      Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => 500 });
    }

    it("시각이 바뀌거나 재생돼도 보기를 전체 화면으로 되돌리지 않는다(예전 결함)", () => {
      setSize();
      const fit = vi.mocked(geometry.fitView);
      const make = (n: number): SiteState[] => states.map((s) => ({ ...s, ratio: 90 + n })); // 칸마다 새 배열
      const { rerender } = render(
        <ThemeProvider>
          <MapPanel states={make(0)} geo={geoSeoul} times={times} slot={10} onSlot={() => {}} />
        </ThemeProvider>,
      );
      const initial = fit.mock.calls.length;
      expect(initial).toBeGreaterThan(0); // 처음에는 맞춘다
      for (let i = 1; i <= 5; i++) {
        rerender(
          <ThemeProvider>
            <MapPanel states={make(i)} geo={geoSeoul} times={times} slot={10 + i} onSlot={() => {}} />
          </ThemeProvider>,
        );
      }
      expect(fit.mock.calls.length).toBe(initial); // 칸이 넘어가도 다시 맞추지 않았다
    });

    it("오른쪽 클릭하면 선택이 해제되고 브라우저 메뉴는 뜨지 않는다", () => {
      setSize();
      useSelection.getState().selectSite("A", "1");
      render(
        <ThemeProvider>
          <MapPanel states={states} geo={geoSeoul} times={times} slot={47} onSlot={() => {}} />
        </ThemeProvider>,
      );
      const canvas = screen.getByRole("img", { name: /굴뚝 .*곳을 보여 주는 지도/ });
      expect(useSelection.getState().selectedSiteId).toBe("A");
      const notPrevented = fireEvent.contextMenu(canvas);
      expect(notPrevented).toBe(false); // 기본 메뉴를 막았다
      expect(useSelection.getState().selectedSiteId).toBeNull();
    });


    it("땅을 눌러도(두 번 눌러도) 지역이 바뀌거나 지도가 움직이지 않는다", () => {
      setSize();
      render(
        <ThemeProvider>
          <MapPanel states={states} geo={geoSeoul} times={times} slot={47} onSlot={() => {}} />
        </ThemeProvider>,
      );
      const canvas = screen.getByRole("img", { name: /굴뚝 .*곳을 보여 주는 지도/ });
      const before = useSelection.getState().mapPath;
      fireEvent.pointerDown(canvas, { button: 0, clientX: 300, clientY: 200 });
      fireEvent.pointerUp(canvas, { button: 0, clientX: 300, clientY: 200 });
      fireEvent.doubleClick(canvas, { clientX: 300, clientY: 200 });
      expect(useSelection.getState().mapPath).toBe(before);
    });

    it("확대·이동을 멈추면 화면 중앙을 보고 지역을 판단해 경로를 채운다", () => {
      setSize();
      vi.useFakeTimers();
      try {
        render(
          <ThemeProvider>
            <MapPanel states={states} geo={geoSeoul} times={times} slot={47} onSlot={() => {}} />
          </ThemeProvider>,
        );
        const canvas = screen.getByRole("img", { name: /굴뚝 .*곳을 보여 주는 지도/ });
        act(() => useSelection.getState().setMapPath({ sido: null, sigungu: null })); // 처음 판단은 지우고 시작한다
        expect(useSelection.getState().mapPath.sido).toBeNull();
        fireEvent.wheel(canvas, { deltaY: -120, clientX: 400, clientY: 250 }); // 확대
        expect(useSelection.getState().mapPath.sido).toBeNull(); // 움직이는 동안은 판단하지 않는다
        act(() => { vi.advanceTimersByTime(200); }); // 멈춤
        expect(useSelection.getState().mapPath.sido).toBe("서울");
      } finally {
        vi.useRealTimers();
      }
    });

    it("너무 넓게 보면(광역) 지역을 특정하지 않는다", () => {
      setSize();
      vi.useFakeTimers();
      try {
        useSelection.getState().setMapPath({ sido: "서울", sigungu: "중구" });
        render(
          <ThemeProvider>
            <MapPanel states={states} geo={[...geoSeoul, geoKorea]} times={times} slot={47} onSlot={() => {}} />
          </ThemeProvider>,
        );
        const canvas = screen.getByRole("img", { name: /굴뚝 .*곳을 보여 주는 지도/ });
        for (let i = 0; i < 12; i++) fireEvent.wheel(canvas, { deltaY: 120, clientX: 400, clientY: 250 }); // 축소
        act(() => { vi.advanceTimersByTime(200); });
        expect(useSelection.getState().mapPath).toEqual({ sido: null, sigungu: null });
      } finally {
        vi.useRealTimers();
      }
    });

    describe("축소·이동 한계(관제 지도)", () => {
      const open = () => {
        setSize();
        vi.useFakeTimers();
        render(
          <ThemeProvider>
            <MapPanel states={states} geo={[...geoSeoul, geoKorea]} times={times} slot={47} onSlot={() => {}} />
          </ThemeProvider>,
        );
        return screen.getByRole("img", { name: /굴뚝 .*곳을 보여 주는 지도/ });
      };
      const widthOf = (b: { minX: number; maxX: number }) => b.maxX - b.minX;
      const settle = () => act(() => { vi.advanceTimersByTime(200); });

      it("아무리 축소해도 전국이 화면에 꽉 차는 크기보다 작아지지 않는다", () => {
        try {
          const canvas = open();
          const first = useSelection.getState().mapBounds!; // 처음 = 전국 보기
          for (let i = 0; i < 40; i++) fireEvent.wheel(canvas, { deltaY: 120, clientX: 400, clientY: 250 });
          settle();
          const out = useSelection.getState().mapBounds!;
          expect(widthOf(out)).toBeCloseTo(widthOf(first), 6); // 더 넓게는 못 본다
          expect(out.minX).toBeCloseTo(first.minX, 6);
        } finally {
          vi.useRealTimers();
        }
      });

      it("전국 크기에서 화면 모서리에 대고 축소해도 지도가 밀려나지 않는다", () => {
        try {
          const canvas = open();
          const first = useSelection.getState().mapBounds!;
          for (let i = 0; i < 20; i++) fireEvent.wheel(canvas, { deltaY: 120, clientX: 5, clientY: 5 });
          settle();
          const out = useSelection.getState().mapBounds!;
          expect(out.minX).toBeCloseTo(first.minX, 6);
          expect(out.minY).toBeCloseTo(first.minY, 6);
        } finally {
          vi.useRealTimers();
        }
      });

      it("확대한 뒤에는 한도까지만 줄어들고, 다시 줄이면 전국 크기에서 멈춘다", () => {
        try {
          const canvas = open();
          const first = useSelection.getState().mapBounds!;
          for (let i = 0; i < 6; i++) fireEvent.wheel(canvas, { deltaY: -120, clientX: 400, clientY: 250 });
          settle();
          const zoomed = useSelection.getState().mapBounds!;
          expect(widthOf(zoomed)).toBeLessThan(widthOf(first) * 0.5);
          for (let i = 0; i < 40; i++) fireEvent.wheel(canvas, { deltaY: 120, clientX: 400, clientY: 250 });
          settle();
          expect(widthOf(useSelection.getState().mapBounds!)).toBeCloseTo(widthOf(first), 6);
        } finally {
          vi.useRealTimers();
        }
      });

      it("끌어서 지도를 화면 밖으로 밀어낼 수 없다(보이는 범위가 지도 범위에서 멀리 벗어나지 않는다)", () => {
        try {
          const canvas = open();
          const first = useSelection.getState().mapBounds!; // 전국 범위(여백 포함)
          for (let i = 0; i < 6; i++) fireEvent.wheel(canvas, { deltaY: -120, clientX: 400, clientY: 250 });
          settle();
          // 오른쪽으로 크게 끌기(지도를 오른쪽 밖으로 밀어내려는 시도)
          fireEvent.pointerDown(canvas, { button: 0, clientX: 100, clientY: 250, pointerId: 1 });
          for (let x = 150; x <= 5000; x += 250) fireEvent.pointerMove(canvas, { clientX: x, clientY: 250, pointerId: 1 });
          fireEvent.pointerUp(canvas, { button: 0, clientX: 5000, clientY: 250, pointerId: 1 });
          settle();
          const b = useSelection.getState().mapBounds!;
          // 지도의 왼쪽 끝(first.minX 근처)이 화면 안쪽으로 25% 이상 들어오지 못한다 → 보이는 범위의 왼쪽이 지도 왼쪽 끝보다 많이 왼쪽으로 못 간다
          expect(b.minX).toBeGreaterThanOrEqual(first.minX - widthOf(b) * 0.3);
          expect(b.minX).toBeLessThan(first.maxX); // 그리고 지도는 여전히 화면 안에 있다
        } finally {
          vi.useRealTimers();
        }
      });
    });

    it("위치 표시는 눌러서 이동하는 버튼이 아니라 지도 중앙의 지역을 보여 준다", () => {
      setSize();
      useSelection.getState().setMapPath({ sido: "서울", sigungu: "중구" });
      render(
        <ThemeProvider>
          <MapPanel states={states} geo={geoSeoul} times={times} slot={47} onSlot={() => {}} />
        </ThemeProvider>,
      );
      const nav = screen.getByRole("navigation", { name: "지도 중앙 위치" });
      expect(nav).toHaveTextContent("지도 중앙");
      expect(nav).toHaveTextContent("서울");
      expect(nav).toHaveTextContent("중구");
      expect(nav.querySelectorAll("button").length).toBe(0);
      expect(screen.queryByRole("button", { name: "상위로" })).toBeNull();
      expect(screen.queryByRole("group", { name: "시군 선택" })).toBeNull();
    });


    it("지도 윗줄은 한 줄이다: 제목·위치는 왼쪽, 등고선·지도 종류·상태 칩·전국 보기는 오른쪽에 모여 있다", () => {
      setSize();
      render(
        <ThemeProvider>
          <MapPanel states={states} geo={geoSeoul} times={times} slot={47} onSlot={() => {}} />
        </ThemeProvider>,
      );
      const bar = screen.getByText("지도", { selector: "strong" }).parentElement!;
      const nav = within(bar).getByRole("navigation", { name: "지도 중앙 위치" });
      const chips = within(bar).getByRole("group", { name: "지도에 표시할 상태" });
      const contour = within(bar).getByRole("button", { name: "등고선 끔" });
      const nation = within(bar).getByRole("button", { name: "전국 보기" });
      // 칩·등고선·전국 보기는 같은 오른쪽 묶음 안에 있다(위치 표시는 그 밖, 왼쪽)
      const right = chips.parentElement!;
      expect(right.contains(contour)).toBe(true);
      expect(right.contains(nation)).toBe(true);
      expect(right.contains(nav)).toBe(false);
      // 문서 순서: 제목 → 위치 → 등고선 → 지도 종류(관제·일반·위성) → 상태 칩 → 전국 보기
      const follows = (a: Node, b: Node) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
      const kinds = within(bar).getByRole("group", { name: "지도 종류" });
      expect(follows(nav, contour)).toBe(true);
      expect(follows(contour, kinds)).toBe(true);
      expect(follows(kinds, chips)).toBe(true);
      expect(follows(chips, nation)).toBe(true);
    });

    it("정상·주의·경고·위험·초과·공백 칩이 있고 처음(웹 기본)에는 위험·초과만 켜져 있다", () => {
      useSelection.setState({ ...initialSelection });
      setSize();
      render(
        <ThemeProvider>
          <MapPanel states={states} geo={geoSeoul} times={times} slot={47} onSlot={() => {}} />
        </ThemeProvider>,
      );
      const group = screen.getByRole("group", { name: "지도에 표시할 상태" });
      const names = within(group).getAllByRole("button").map((b) => b.textContent!.trim());
      expect(names).toEqual(["정상", "주의", "경고", "위험", "초과", "공백"]);
      for (const b of within(group).getAllByRole("button")) {
        expect(b).toHaveAttribute("aria-pressed", ["위험", "초과"].includes(b.textContent!.trim()) ? "true" : "false");
      }
    });

    it("공백 칩에는 미수신·점검·가동중지 같은 뜻이 안내돼 있다", () => {
      setSize();
      render(
        <ThemeProvider>
          <MapPanel states={states} geo={geoSeoul} times={times} slot={47} onSlot={() => {}} />
        </ThemeProvider>,
      );
      expect(screen.getByRole("button", { name: /공백/ })).toHaveAttribute("title", expect.stringContaining("미수신"));
    });

    it("칩을 누르면 그 상태의 표시가 꺼지고 다시 누르면 켜지며, 지도 설명의 곳 수가 따라 바뀐다", async () => {
      setSize();
      render(
        <ThemeProvider>
          <MapPanel states={states} geo={geoSeoul} times={times} slot={47} onSlot={() => {}} />
        </ThemeProvider>,
      );
      const group = screen.getByRole("group", { name: "지도에 표시할 상태" });
      const risk = within(group).getByRole("button", { name: /위험/ });
      expect(screen.getByRole("img", { name: /굴뚝 1곳을 보여 주는 지도/ })).toBeInTheDocument(); // 위험 1곳
      await userEvent.click(risk);
      expect(risk).toHaveAttribute("aria-pressed", "false");
      expect(useSelection.getState().mapLevels).toEqual(["ok", "caution", "warn", "exceed", "gap"]);
      expect(screen.getByRole("img", { name: /굴뚝 0곳을 보여 주는 지도/ })).toBeInTheDocument();
      await userEvent.click(risk);
      expect(risk).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("img", { name: /굴뚝 1곳을 보여 주는 지도/ })).toBeInTheDocument();
    });

    it("정상 칩도 꺼진다(예전에는 정상·공백이 늘 보였다)", async () => {
      setSize();
      const ok: SiteState[] = [
        { site: { id: "N", name: "정상공장", sido: "서울", sigungu: "중구", address: "", lon: 127, lat: 37.5, stacks: [] }, ratio: 10, level: "ok", worstStack: "1" },
        ...states,
      ];
      render(
        <ThemeProvider>
          <MapPanel states={ok} geo={geoSeoul} times={times} slot={47} onSlot={() => {}} />
        </ThemeProvider>,
      );
      expect(screen.getByRole("img", { name: /굴뚝 2곳을 보여 주는 지도/ })).toBeInTheDocument();
      await userEvent.click(within(screen.getByRole("group", { name: "지도에 표시할 상태" })).getByRole("button", { name: /정상/ }));
      expect(screen.getByRole("img", { name: /굴뚝 1곳을 보여 주는 지도/ })).toBeInTheDocument();
    });


    describe("같은 자리에 붙은 사업장", () => {
      // 아무 호출이나 받아 주는 가짜 그리기 도구(jsdom에는 캔버스 그리기가 없다). 묶음 계산과 클릭 판정이 돌게 한다.
      function fakeContext() {
        const store: Record<string, unknown> = {};
        return new Proxy(store, {
          get: (t, k: string) => {
            if (k in t) return t[k];
            if (k === "measureText") return () => ({ width: 10 });
            if (k === "createLinearGradient") return () => ({ addColorStop() {} });
            return () => {};
          },
          set: (t, k: string, v) => { t[k] = v; return true; },
        }) as unknown as CanvasRenderingContext2D;
      }
      const at = (id: string, lon: number, lat: number, level: SiteState["level"] = "risk", ratio = 95): SiteState => ({
        site: { id, name: `공장${id}`, sido: "서울", sigungu: "중구", address: "", lon, lat, stacks: [] },
        ratio, level, worstStack: "1",
      });
      const geo = [{ name: "서울", type: "Polygon" as const, coordinates: [[[126.8, 37.4], [127.2, 37.4], [127.2, 37.7], [126.8, 37.7], [126.8, 37.4]]] }];
      function sizeAndContext() {
        Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 800 });
        Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => 500 });
        vi.mocked(HTMLCanvasElement.prototype.getContext).mockReturnValue(fakeContext() as never);
      }
      /** 지도가 전국에 맞춘 뒤 이 좌표의 화면 위치(테스트가 눌러야 할 곳) */
      function screenOf(lon: number, lat: number) {
        const corners = [[126.8, 37.4], [127.2, 37.7]].map(([x, y]) => geometry.project(x, y));
        const b = geometry.boundsOf(corners)!;
        const view = geometry.fitView(b, 800, 500, 28);
        const [px, py] = geometry.project(lon, lat);
        return geometry.toScreen(view, px, py);
      }
      const press = (canvas: HTMLElement, [x, y]: readonly [number, number]) => {
        fireEvent.pointerDown(canvas, { button: 0, clientX: x, clientY: y });
        fireEvent.pointerUp(canvas, { button: 0, clientX: x, clientY: y });
      };
      const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 60)); });

      it("좌표가 같아 확대해도 안 갈라지는 묶음을 누르면 사업장 고르기 목록이 뜨고, 고르면 선택된다", async () => {
        sizeAndContext();
        const same = [at("A", 127.0, 37.5, "risk", 95), at("B", 127.0, 37.5, "exceed", 120), at("C", 127.0, 37.5, "warn", 82)];
        render(
          <ThemeProvider>
            <MapPanel states={same} geo={geo} times={times} slot={47} onSlot={() => {}} />
          </ThemeProvider>,
        );
        await settle();
        const canvas = screen.getByRole("img", { name: /굴뚝 3곳을 보여 주는 지도/ });
        press(canvas, screenOf(127.0, 37.5));
        const menu = await screen.findByRole("menu", { name: /같은 자리의 사업장 3곳 중 고르기/ });
        const items = within(menu).getAllByRole("menuitem");
        expect(items).toHaveLength(3);
        // 단계 높은 순: 초과 → 위험 → 경고
        expect(items[0]).toHaveTextContent("공장B");
        expect(items[1]).toHaveTextContent("공장A");
        expect(items[2]).toHaveTextContent("공장C");
        await userEvent.click(items[1]);
        expect(useSelection.getState().selectedSiteId).toBe("A");
        expect(screen.queryByRole("menu")).toBeNull();
      });

      it("고르기 목록은 Escape, 오른쪽 클릭, 지도 조작으로 닫힌다", async () => {
        sizeAndContext();
        const same = [at("A", 127.0, 37.5), at("B", 127.0, 37.5)];
        render(
          <ThemeProvider>
            <MapPanel states={same} geo={geo} times={times} slot={47} onSlot={() => {}} />
          </ThemeProvider>,
        );
        await settle();
        const canvas = screen.getByRole("img", { name: /굴뚝 2곳을 보여 주는 지도/ });
        press(canvas, screenOf(127.0, 37.5));
        const menu = await screen.findByRole("menu");
        fireEvent.keyDown(menu, { key: "Escape" });
        expect(screen.queryByRole("menu")).toBeNull();
        press(canvas, screenOf(127.0, 37.5));
        await screen.findByRole("menu");
        fireEvent.contextMenu(canvas);
        expect(screen.queryByRole("menu")).toBeNull();
        press(canvas, screenOf(127.0, 37.5));
        await screen.findByRole("menu");
        fireEvent.wheel(canvas, { deltaY: -120 });
        expect(screen.queryByRole("menu")).toBeNull();
      });

      it("조금 떨어져 있어 확대하면 갈라지는 묶음은 목록이 아니라 확대로 풀린다", async () => {
        sizeAndContext();
        const near = [at("A", 127.0, 37.5), at("B", 127.01, 37.5)]; // 약 1km 떨어짐
        render(
          <ThemeProvider>
            <MapPanel states={near} geo={geo} times={times} slot={47} onSlot={() => {}} />
          </ThemeProvider>,
        );
        await settle();
        const canvas = screen.getByRole("img", { name: /굴뚝 2곳을 보여 주는 지도/ });
        const [ax, ay] = screenOf(127.0, 37.5), [bx, by] = screenOf(127.01, 37.5);
        press(canvas, [(ax + bx) / 2, (ay + by) / 2]); // 묶음 위치(가운데)
        expect(screen.queryByRole("menu")).toBeNull();
      });
    });


    it("지도가 지금 보이는 범위를 목록에 알린다(처음, 확대한 뒤)", () => {
      setSize();
      vi.useFakeTimers();
      try {
        render(
          <ThemeProvider>
            <MapPanel states={states} geo={geoSeoul} times={times} slot={47} onSlot={() => {}} />
          </ThemeProvider>,
        );
        const first = useSelection.getState().mapBounds!;
        expect(first).not.toBeNull(); // 처음 보이는 범위(전국에 맞춘 화면)
        expect(first.maxX).toBeGreaterThan(first.minX);
        expect(first.maxY).toBeGreaterThan(first.minY);
        // 서울 사업장(127, 37.5)이 처음 화면 안에 들어온다
        const [sx, sy] = geometry.project(127.0, 37.5);
        expect(sx >= first.minX && sx <= first.maxX && sy >= first.minY && sy <= first.maxY).toBe(true);
        const canvas = screen.getByRole("img", { name: /굴뚝 .*곳을 보여 주는 지도/ });
        fireEvent.wheel(canvas, { deltaY: -120, clientX: 400, clientY: 250 }); // 확대
        expect(useSelection.getState().mapBounds).toBe(first); // 움직이는 동안은 갱신하지 않는다
        act(() => { vi.advanceTimersByTime(200); }); // 멈춤
        const zoomed = useSelection.getState().mapBounds!;
        expect(zoomed.maxX - zoomed.minX).toBeLessThan(first.maxX - first.minX); // 더 좁은 범위
        expect(zoomed.maxY - zoomed.minY).toBeLessThan(first.maxY - first.minY);
      } finally {
        vi.useRealTimers();
      }
    });
  });
});
