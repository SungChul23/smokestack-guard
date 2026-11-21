import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DayData, Site } from "../data/model";
import { defaultsFor, getStyle, useChartStyle } from "../state/chartStyle";
import { LEGACY_CHART_STYLE } from "../test/legacyChartStyle";
import { initialSelection, useSelection } from "../state/selection";
import ChartStylePanel from "./ChartStylePanel";
import TrendChart, { CHART } from "./TrendChart";

const style = () => getStyle();
beforeEach(() => {
  window.localStorage.clear();
  useChartStyle.setState({ styles: { dark: { ...LEGACY_CHART_STYLE }, light: { ...LEGACY_CHART_STYLE } } }); // 예전 모양에서 시작한다(새 기본값을 보는 시험은 reset()을 부른다)
  useSelection.setState({ ...initialSelection });
});

describe("그래프 설정 패널", () => {
  it("닫혀 있으면 그리지 않고, 열면 제목과 바꾼 개수를 보여 준다", () => {
    useChartStyle.getState().reset();
    const { rerender } = render(<ChartStylePanel open={false} onClose={() => {}} />);
    expect(screen.queryByRole("dialog")).toBeNull();
    rerender(<ChartStylePanel open onClose={() => {}} />);
    expect(screen.getByRole("dialog", { name: "그래프 설정" })).toBeInTheDocument();
    expect(screen.getByText("이 모드의 기본값 그대로")).toBeInTheDocument();
    act(() => useChartStyle.getState().set({ lineWidth: 5 }));
    expect(screen.getByText("이 모드의 기본값에서 1개 바꿈")).toBeInTheDocument();
  });

  it("슬라이더를 움직이면 바로 설정이 바뀌고 '바꿈'이 센다", () => {
    useChartStyle.getState().reset();
    render(<ChartStylePanel open onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("굵기"), { target: { value: "5" } });
    expect(style().lineWidth).toBe(5);
    // "빛(라이팅)" 라벨은 선·바깥 글자·축에 각각 있어서 id로 집는다(선의 빛 = cs-lg)
    fireEvent.change(document.getElementById("cs-lg")!, { target: { value: "8" } });
    expect(style().lineGlow).toBe(8);
    expect(screen.getByText("이 모드의 기본값에서 2개 바꿈")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument(); // 현재 값 표시
  });

  it("켬/끔 스위치와 색을 바꾸고, 기본색으로 되돌린다", async () => {
    render(<ChartStylePanel open onClose={() => {}} />);
    await userEvent.click(screen.getByRole("checkbox", { name: "부드러운 곡선" }));
    expect(style().smooth).toBe(true);
    await userEvent.click(screen.getByRole("checkbox", { name: "영역 채움" }));
    expect(style().areaOn).toBe(false);
    const nox = screen.getByLabelText("NOx");
    fireEvent.change(nox, { target: { value: "#ff8800" } });
    expect(style().noxColor).toBe("#ff8800");
    const noxRow = nox.closest("div")!;
    await userEvent.click(within(noxRow).getByRole("button", { name: "기본색" }));
    expect(style().noxColor).toBeNull();
  });

  it("기본값으로 되돌리기는 바꾼 것이 있을 때만 켜진다", async () => {
    useChartStyle.getState().reset();
    render(<ChartStylePanel open onClose={() => {}} />);
    const reset = screen.getByRole("button", { name: "기본값으로 되돌리기" });
    expect(reset).toBeDisabled();
    fireEvent.change(screen.getByLabelText("굵기"), { target: { value: "6" } });
    expect(reset).toBeEnabled();
    await userEvent.click(reset);
    expect(style()).toEqual(defaultsFor("dark"));
  });

  it("현재 값을 JSON으로 복사하고, 복사할 수 없으면 글상자에 보여 준다", async () => {
    render(<ChartStylePanel open onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("굵기"), { target: { value: "4" } });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    await userEvent.click(screen.getByRole("button", { name: "현재 값 복사(JSON)" }));
    expect(JSON.parse(writeText.mock.calls[0][0] as string).lineWidth).toBe(4);
    expect(screen.getByRole("status")).toHaveTextContent("복사했습니다");

    Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn().mockRejectedValue(new Error("no")) }, configurable: true });
    await userEvent.click(screen.getByRole("button", { name: "현재 값 복사(JSON)" }));
    expect((screen.getByLabelText("그래프 설정 JSON") as HTMLTextAreaElement).value).toContain('"lineWidth": 4');
  });

  it("복사한 JSON을 붙여 넣어 적용한다(이상한 값은 알려 준다)", async () => {
    render(<ChartStylePanel open onClose={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "값 붙여 넣기" }));
    const box = screen.getByLabelText("그래프 설정 JSON");
    fireEvent.change(box, { target: { value: "이건 JSON이 아님" } });
    await userEvent.click(screen.getByRole("button", { name: "적용" }));
    expect(screen.getByRole("status")).toHaveTextContent("읽지 못했습니다");
    fireEvent.change(box, { target: { value: JSON.stringify({ smooth: true, dotR: 10, lineWidth: 999 }) } });
    await userEvent.click(screen.getByRole("button", { name: "적용" }));
    expect(style()).toMatchObject({ smooth: true, dotR: 10, lineWidth: 8 }); // 범위 밖은 맞춰서
  });

  it("Esc와 × 버튼으로 닫힌다", async () => {
    const onClose = vi.fn();
    render(<ChartStylePanel open onClose={onClose} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: "그래프 설정 닫기" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("예시 사업장 열기 버튼은 값을 줄 때만 있고 누르면 부른다", async () => {
    const onPick = vi.fn();
    const { rerender } = render(<ChartStylePanel open onClose={() => {}} />);
    expect(screen.queryByRole("button", { name: "예시 사업장 열기" })).toBeNull();
    rerender(<ChartStylePanel open onClose={() => {}} onPickSample={onPick} />);
    await userEvent.click(screen.getByRole("button", { name: "예시 사업장 열기" }));
    expect(onPick).toHaveBeenCalled();
  });
});

describe("설정이 실제 그래프에 반영된다", () => {
  const N = 48;
  const times = Array.from({ length: N }, (_, i) => Date.UTC(2026, 10, 10, 0, 0) + i * 1800000);
  const site: Site = { id: "S", name: "시험공장", sido: "서울", sigungu: "중구", address: "", lon: 127, lat: 37, stacks: [{ key: "S:1", code: "1" }] };
  const nox = times.map((_, i) => String(40 + 30 * Math.sin(i / 5) + (i % 7)));
  const day: DayData = { times, stacks: { "S:1": { nox, sox: nox.map(() => "30"), noxLimit: "100", soxLimit: "100" } } };
  const draw = () => render(<TrendChart site={site} day={day} />).container;
  const set = (patch: Parameters<ReturnType<typeof useChartStyle.getState>["set"]>[0]) => act(() => useChartStyle.getState().set(patch));

  it("다크 기본값(D가 정한 값)이면 가는 곡선·빛, 눈금 없음, 옅은 바탕, 흰 세로선, 단계 글자 하나만 보인다", () => {
    useChartStyle.getState().reset();
    const c = draw();
    const line = c.querySelector("path[data-line]") as SVGElement;
    expect(line.getAttribute("stroke-width")).toBe("1");
    expect(line.style.filter).toContain("drop-shadow(0 0 2px");
    expect(line.getAttribute("d")).toContain("C");
    expect(c.querySelector("path[data-area]")).not.toBeNull();
    expect(c.querySelector("line[data-grid]")).toBeNull();
    expect(c.querySelectorAll("line[data-level-line]")).toHaveLength(4);
    expect(c.querySelector("line[data-level-line]")!.getAttribute("stroke-opacity")).toBe("0.25");
    expect(c.querySelector("line[data-crosshair]")!.getAttribute("stroke")).toBe("#ffffff");
    const inner = c.querySelector("rect[data-inner]")!;
    expect(inner.getAttribute("rx")).toBe("10");
    expect(inner.getAttribute("fill-opacity")).toBe("0.35");
    const dot = c.querySelector("circle[data-dot]")!;
    expect(dot.getAttribute("r")).toBe("4");
    expect(dot.getAttribute("stroke")).toBe("#dbf6ff");
    // 바깥 글자: 단계 글자는 점의 단계 하나만, 크기 23·빛 2, 초과 영역·축 글자는 흰색
    expect(c.querySelectorAll("text[data-level-label]").length).toBeLessThanOrEqual(1);
    const zone = c.querySelector("text[data-zone-label]") as SVGElement;
    expect(zone.getAttribute("fill")).toBe("#ffffff");
    expect(zone.style.filter).toContain("drop-shadow(0 0 2px");
    expect(c.querySelector("text[data-axis]")!.getAttribute("fill")).toBe("#ffffff");
    expect((c.querySelector("text[data-axis]") as SVGElement).style.fontSize).toBe("19px");
  });

  it("예전 모양(옛 기본값)으로도 그대로 그려진다", () => {
    const c = draw(); // 이 파일의 시험은 예전 모양에서 시작한다
    expect((c.querySelector("path[data-line]") as SVGElement).getAttribute("stroke-width")).toBe("2.8");
    expect(c.querySelectorAll("line[data-grid]")).toHaveLength(3);
    expect(c.querySelector("rect[data-inner]")!.getAttribute("rx")).toBe("8");
  });

  it("굵기·빛·곡선이 선에 반영된다", () => {
    const c = draw();
    set({ lineWidth: 5, lineGlow: 9, smooth: true });
    const line = c.querySelector("path[data-line]") as SVGElement;
    expect(line.getAttribute("stroke-width")).toBe("5");
    expect(line.style.filter).toContain("drop-shadow(0 0 9px");
    expect(line.getAttribute("d")).toContain("C");
  });

  it("영역·눈금·기준선·세로선을 끌 수 있다", () => {
    const c = draw();
    set({ areaOn: false, gridOn: false, levelLinesOn: false, crosshairOn: false });
    expect(c.querySelector("path[data-area]")).toBeNull();
    expect(c.querySelector("line[data-grid]")).toBeNull();
    expect(c.querySelector("line[data-level-line]")).toBeNull();
    expect(c.querySelector("line[data-crosshair]")).toBeNull();
  });

  it("기준선 점선을 끄면 실선이 되고, 진하기·안쪽 판 모서리가 바뀐다", () => {
    const c = draw();
    const warn = () => c.querySelector('line[data-level-line="warn"]')!;
    expect(warn().getAttribute("stroke-dasharray")).toBe("4 4");
    set({ levelLinesDashed: false, levelLineOpacity: 0.3, innerRadius: 20, innerOpacity: 0.5, gridOpacity: 0.4 });
    expect(warn().getAttribute("stroke-dasharray")).toBe("0");
    expect(warn().getAttribute("stroke-opacity")).toBe("0.3");
    const inner = c.querySelector("rect[data-inner]")!;
    expect(inner.getAttribute("rx")).toBe("20");
    expect(inner.getAttribute("fill-opacity")).toBe("0.5");
    expect(c.querySelector("line[data-grid]")!.getAttribute("stroke-opacity")).toBe("0.4");
  });

  it("선택 시점의 점 크기와 빛, 물질 색이 반영된다", () => {
    const c = draw();
    set({ dotR: 10, dotGlow: 6, noxColor: "#ff8800" });
    const dot = c.querySelector("circle[data-dot]")!;
    expect(dot.getAttribute("r")).toBe("10");
    expect((dot as SVGElement).style.filter).toContain("drop-shadow(0 0 6px #ff8800");
    expect(dot.getAttribute("fill")).toBe("#ff8800");
    expect(c.querySelector("path[data-line]")!.getAttribute("stroke")).toBe("#ff8800");
  });
});

describe("색 바꾸기", () => {
  const N = 48;
  const times = Array.from({ length: N }, (_, i) => Date.UTC(2026, 10, 10, 0, 0) + i * 1800000);
  const site: Site = { id: "S", name: "시험공장", sido: "서울", sigungu: "중구", address: "", lon: 127, lat: 37, stacks: [{ key: "S:1", code: "1" }] };
  // 앞 칸들은 값이 없는 공백(점선·칠이 보이도록), 뒤는 값
  const nox = times.map((_, i) => (i < 10 ? "미수신" : String(60 + (i % 9) * 5)));
  const day: DayData = { times, stacks: { "S:1": { nox, sox: nox.map(() => "30"), noxLimit: "100", soxLimit: "100" } } };
  const draw = () => render(<TrendChart site={site} day={day} />).container;
  const set = (patch: Parameters<ReturnType<typeof useChartStyle.getState>["set"]>[0]) => act(() => useChartStyle.getState().set(patch));

  it("패널에는 영역·공백·눈금·기준선 4개·초과 영역·바탕·글자·세로선·점 테두리 색 줄이 있다", () => {
    render(<ChartStylePanel open onClose={() => {}} />);
    for (const name of ["NOx", "SOx", "영역 색", "점선·칠 색", "눈금선 색", "초과 영역 색", "주의 기준선 색", "경고 기준선 색", "위험 기준선 색", "초과 기준선 색", "바탕 색", "축 글자 색", "세로선 색", "점 테두리 색"]) {
      expect(screen.getByLabelText(name), name).toHaveAttribute("type", "color");
    }
  });

  it("색을 고르면 설정에 들어가고 '기본색' 버튼은 그 줄만 되돌린다", async () => {
    render(<ChartStylePanel open onClose={() => {}} />);
    const grid = screen.getByLabelText("눈금선 색");
    fireEvent.change(grid, { target: { value: "#00ff00" } });
    fireEvent.change(screen.getByLabelText("경고 기준선 색"), { target: { value: "#0000ff" } });
    expect(style().gridColor).toBe("#00ff00");
    expect(style().levelWarnColor).toBe("#0000ff");
    await userEvent.click(within(grid.closest("div")!).getByRole("button", { name: "기본색" }));
    expect(style().gridColor).toBeNull();
    expect(style().levelWarnColor).toBe("#0000ff"); // 다른 줄은 그대로
  });

  it("고른 색이 그래프에 반영된다(눈금선·기준선·초과 영역·바탕·점 테두리·세로선·글자)", () => {
    const c = draw();
    set({ gridColor: "#111111", levelWarnColor: "#222222", levelExceedColor: "#333333", zoneColor: "#444444", innerColor: "#555555", dotStrokeColor: "#666666", crosshairColor: "#777777", textColor: "#888888" });
    expect(c.querySelector("line[data-grid]")!.getAttribute("stroke")).toBe("#111111");
    expect(c.querySelector('line[data-level-line="warn"]')!.getAttribute("stroke")).toBe("#222222");
    expect(c.querySelector('line[data-level-line="exceed"]')!.getAttribute("stroke")).toBe("#333333");
    expect(c.querySelector('line[data-level-line="caution"]')!.getAttribute("stroke")).toBe("var(--lv-caution)"); // 안 고른 줄은 테마색
    expect(c.querySelector('g[data-zone="exceed"] rect')!.getAttribute("fill")).toBe("#444444");
    expect(c.querySelector("rect[data-inner]")!.getAttribute("fill")).toBe("#555555");
    expect(c.querySelector("circle[data-dot]")!.getAttribute("stroke")).toBe("#666666");
    expect(c.querySelector("line[data-crosshair]")!.getAttribute("stroke")).toBe("#777777");
    const texts = [...c.querySelectorAll("svg text")].filter((t) => t.getAttribute("fill") === "#888888").map((t) => t.textContent);
    expect(texts).toContain("0%"); // 축 글자
  });

  it("기본값에서는 공백 점선이 D가 고른 청록 회색(#84b3a6)이다", () => {
    useChartStyle.getState().reset();
    const c = draw();
    expect(c.querySelector("[data-gap-link] path:last-child")!.getAttribute("stroke")).toBe("#84b3a6");
  });

  it("영역·공백 점선 색은 고르지 않으면 물질 색을 따르고, 고르면 그 색이다", () => {
    const c = draw();
    set({ noxColor: "#ff8800" });
    const stopColors = () => [...c.querySelectorAll("linearGradient stop")].map((s) => s.getAttribute("stop-color"));
    expect(stopColors().filter((x) => x === "#ff8800").length).toBeGreaterThanOrEqual(4); // 영역·공백 그라데이션 모두 물질 색
    const gapLine = () => c.querySelector("[data-gap-link] path:last-child")!.getAttribute("stroke");
    expect(gapLine()).toBe("#ff8800");
    set({ areaColor: "#00aa00", gapLineColor: "#aa00aa" });
    expect(gapLine()).toBe("#aa00aa");
    expect(stopColors()).toContain("#00aa00");
    expect(stopColors()).toContain("#aa00aa");
  });
});

describe("바깥 글자·숫자, 점의 단계 글자, 박동", () => {
  const N = 48;
  const times = Array.from({ length: N }, (_, i) => Date.UTC(2026, 10, 10, 0, 0) + i * 1800000);
  const site: Site = { id: "S", name: "시험공장", sido: "서울", sigungu: "중구", address: "", lon: 127, lat: 37, stacks: [{ key: "S:1", code: "1" }] };
  /** 앞 40칸은 50%(정상), 마지막 8칸은 last% — 마지막 점이 기본 선택 */
  const dayWith = (last: number): DayData => {
    const nox = times.map((_, i) => (i >= 40 ? String(last) : "50"));
    return { times, stacks: { "S:1": { nox, sox: nox.map(() => null), noxLimit: "100", soxLimit: null } } };
  };
  const draw = (last: number) => render(<TrendChart site={site} day={dayWith(last)} />).container;
  const set = (patch: Parameters<ReturnType<typeof useChartStyle.getState>["set"]>[0]) => act(() => useChartStyle.getState().set(patch));
  const label = (c: HTMLElement, key: string) => c.querySelector(`text[data-level-label="${key}"]`) as SVGElement | null;

  it("바깥 글자의 크기와 빛이 반영된다(초과 영역 글자·단계 글자·축 숫자 각각)", () => {
    const c = draw(95);
    set({ zoneLabelSize: 22, zoneLabelGlow: 5, levelLabelSize: 19, levelLabelGlow: 4, axisSize: 20, axisGlow: 3 });
    const zone = c.querySelector("text[data-zone-label]") as SVGElement;
    expect(zone.style.fontSize).toBe("22px");
    expect(zone.style.filter).toContain("drop-shadow(0 0 5px");
    expect(label(c, "warn")!.style.fontSize).toBe("19px");
    expect(label(c, "warn")!.style.filter).toContain("drop-shadow(0 0 4px");
    const axis = [...c.querySelectorAll("text[data-axis]")] as SVGElement[];
    expect(axis).toHaveLength(3); // 위 %, 100%, 0%
    for (const a of axis) expect(a.style.fontSize).toBe("20px");
    expect(axis[0].style.filter).toContain("drop-shadow(0 0 3px");
  });

  it("빛이 0이면 빛 필터를 넣지 않는다", () => {
    const c = draw(95);
    expect(label(c, "warn")!.style.filter).toBe("");
  });

  it("기본은 단계 글자 네 개가 모두 보인다", () => {
    const c = draw(95);
    for (const k of ["caution", "warn", "risk", "exceed"]) expect(label(c, k), k).not.toBeNull();
  });

  it("점의 단계 글자만 보이기를 켜면 선택한 점의 %가 속한 단계 하나만 남는다", () => {
    const c = draw(95); // 마지막 점 95% = 위험
    set({ labelsActiveOnly: true });
    expect([...c.querySelectorAll("text[data-level-label]")].map((t) => t.getAttribute("data-level-label"))).toEqual(["risk"]);
    expect(c.querySelectorAll("line[data-level-line]")).toHaveLength(4); // 기준선은 그대로
  });

  it("점을 찍어(클릭) 70% 미만인 자리를 고르면 단계 글자가 모두 숨고, 높은 자리를 고르면 그 단계가 나온다", () => {
    const c = draw(95);
    set({ labelsActiveOnly: true });
    const svg = c.querySelector("svg[role=img]")!;
    const xAt = (i: number) => CHART.PAD.l + (i / (N - 1)) * CHART.iw;
    fireEvent.click(svg, { clientX: xAt(10) }); // 50% 자리(정상)
    expect(c.querySelectorAll("text[data-level-label]")).toHaveLength(0);
    fireEvent.click(svg, { clientX: xAt(45) }); // 95% 자리
    expect([...c.querySelectorAll("text[data-level-label]")].map((t) => t.getAttribute("data-level-label"))).toEqual(["risk"]);
  });

  it("박동: 선택한 점의 단계 글자만 박동하고 배율·속도·빛 값이 변수로 들어간다(위험은 0.8배 빠르게)", () => {
    const c = draw(95);
    set({ pulseOn: true, pulseScale: 1.2, pulseSpeed: 2, pulseGlow: 12 });
    const beating = [...c.querySelectorAll("text[data-beat]")];
    expect(beating.map((t) => t.getAttribute("data-level-label"))).toEqual(["risk"]);
    const st = (beating[0] as SVGElement).style;
    expect(st.getPropertyValue("--beat-a1")).toBe("1.2");
    expect(Number(st.getPropertyValue("--beat-a2"))).toBeCloseTo(1.13, 2);
    expect(st.getPropertyValue("--beat-dur")).toBe("1.60s"); // 2초 x 0.8
    expect(st.getPropertyValue("--beat-glow")).toBe("12px");
    expect(st.getPropertyValue("--beat-color")).toBe("var(--lv-risk)");
  });

  it("초과는 0.64배, 경고는 그대로 빠르기이고, 높은 단계일수록 빠르게를 끄면 모두 같다", () => {
    const dur = (last: number) => (draw(last).querySelector("text[data-beat]") as SVGElement).style.getPropertyValue("--beat-dur");
    set({ pulseOn: true, pulseSpeed: 1.25, pulseFast: true });
    expect(dur(105)).toBe("0.80s");
    cleanup();
    expect(dur(85)).toBe("1.25s");
    cleanup();
    set({ pulseFast: false });
    expect(dur(105)).toBe("1.25s");
  });

  it("박동을 끄면 어느 글자도 박동하지 않고, 정상(70% 미만)이면 박동할 글자가 없다", () => {
    let c = draw(95);
    set({ pulseOn: false });
    expect(c.querySelector("text[data-beat]")).toBeNull();
    cleanup();
    set({ pulseOn: true });
    c = draw(50);
    expect(c.querySelector("text[data-beat]")).toBeNull();
  });

  it("두 물질을 함께 보면 둘 중 높은 %의 단계가 기준이다", () => {
    const nox = times.map(() => "40"), sox = times.map(() => "105");
    const day: DayData = { times, stacks: { "S:1": { nox, sox, noxLimit: "100", soxLimit: "100" } } };
    const c = render(<TrendChart site={site} day={day} />).container;
    act(() => useSelection.setState({ pollutants: ["nox", "sox"] }));
    set({ pulseOn: true });
    expect([...c.querySelectorAll("text[data-beat]")].map((t) => t.getAttribute("data-level-label"))).toEqual(["exceed"]);
  });
});

describe("다크·라이트 모드별 그래프", () => {
  const N = 48;
  const times = Array.from({ length: N }, (_, i) => Date.UTC(2026, 10, 10, 0, 0) + i * 1800000);
  const site: Site = { id: "S", name: "시험공장", sido: "서울", sigungu: "중구", address: "", lon: 127, lat: 37, stacks: [{ key: "S:1", code: "1" }] };
  const nox = times.map((_, i) => String(40 + (i % 9) * 5));
  const day: DayData = { times, stacks: { "S:1": { nox, sox: nox.map(() => null), noxLimit: "100", soxLimit: null } } };
  // 테마 속성이 바뀐 것은 MutationObserver가 한 박자 뒤에 알려 주므로 기다린다
  const theme = (t: "dark" | "light") => act(async () => { document.documentElement.setAttribute("data-theme", t); await Promise.resolve(); });

  it("모드를 바꾸면 그래프가 그 모드의 설정으로 바뀐다", async () => {
    await theme("dark");
    const c = render(<TrendChart site={site} day={day} />).container;
    act(() => { useChartStyle.getState().set({ lineWidth: 6 }, "dark"); useChartStyle.getState().set({ lineWidth: 2 }, "light"); });
    const w = () => c.querySelector("path[data-line]")!.getAttribute("stroke-width");
    expect(w()).toBe("6");
    await theme("light");
    expect(w()).toBe("2");
    await theme("dark");
    expect(w()).toBe("6");
  });

  it("패널은 지금 모드를 보여 주고, 그 모드의 값만 바꾼다", async () => {
    await theme("light");
    render(<ChartStylePanel open onClose={() => {}} />);
    expect(screen.getByRole("dialog")).toHaveTextContent("그래프 설정 · 라이트 모드");
    fireEvent.change(screen.getByLabelText("굵기"), { target: { value: "7" } });
    expect(getStyle("light").lineWidth).toBe(7);
    expect(getStyle("dark").lineWidth).toBe(LEGACY_CHART_STYLE.lineWidth); // 다크는 그대로
    await theme("dark");
    expect(screen.getByRole("dialog")).toHaveTextContent("그래프 설정 · 다크 모드");
    expect((screen.getByLabelText("굵기") as HTMLInputElement).value).toBe(String(LEGACY_CHART_STYLE.lineWidth));
  });

  it("다른 모드 설정 가져오기는 반대 모드의 값을 이 모드로 복사한다", async () => {
    await theme("dark");
    useChartStyle.getState().set({ lineWidth: 5, noxColor: "#ff00aa" }, "light");
    render(<ChartStylePanel open onClose={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "라이트 모드 설정 가져오기" }));
    expect(getStyle("dark").lineWidth).toBe(5);
    expect(getStyle("dark").noxColor).toBe("#ff00aa");
    expect(screen.getByRole("status")).toHaveTextContent("라이트 모드의 설정을 다크 모드로 복사했습니다");
  });

  it("기본값으로 되돌리기는 지금 모드만 되돌린다", async () => {
    await theme("dark");
    useChartStyle.getState().set({ lineWidth: 6 }, "dark");
    useChartStyle.getState().set({ lineWidth: 7 }, "light");
    render(<ChartStylePanel open onClose={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "기본값으로 되돌리기" }));
    expect(getStyle("dark")).toEqual(defaultsFor("dark"));
    expect(getStyle("light").lineWidth).toBe(7);
  });

  it("패널에 바깥 글자·박동 조절이 있다", () => {
    render(<ChartStylePanel open onClose={() => {}} />);
    for (const name of ["박동 켜기", "점의 단계 글자만 보이기", "높은 단계일수록 빠르게"]) expect(screen.getByRole("checkbox", { name })).toBeInTheDocument();
    for (const id of ["cs-zs", "cs-zg", "cs-ls", "cs-lg2", "cs-as", "cs-ag", "cs-ps", "cs-pt", "cs-pg"]) expect(document.getElementById(id), id).toHaveAttribute("type", "range");
    expect(screen.getByLabelText("글자 색(영역)")).toHaveAttribute("type", "color");
  });
});
