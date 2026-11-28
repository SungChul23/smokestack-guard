import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import type { DayData, Site } from "../data/model";
import { initialSelection, useSelection } from "../state/selection";
import TrendChart, { CHART, DOT_R, formatPct } from "./TrendChart";

// 차트 그림 영역(TrendChart.tsx가 내보내는 값과 같은 것을 쓴다)
const TOP = CHART.PAD.t, IH = CHART.ih;
const site: Site = { id: "S", name: "시험공장", sido: "서울", sigungu: "중구", address: "", lon: 127, lat: 37, stacks: [{ key: "S:1", code: "1" }] };
const SLOT = 30 * 60 * 1000;
const t0 = Date.UTC(2026, 10, 9, 15, 0); // 한국 시각 11-10 00:00
const timesOf = (n: number) => Array.from({ length: n }, (_, i) => t0 + i * SLOT);

interface Opt {
  n?: number;
  nox?: (i: number) => string | null;
  sox?: (i: number) => string | null;
  noxLimit?: string | null;
  soxLimit?: string | null;
}
/** NOx·SOx 둘 다 있는 하루(기본 48칸). 기본값은 NOx 50/100 = 50%, SOx 70/140 = 50% */
function dayBoth({ n = 48, nox = () => "50", sox = () => "70", noxLimit = "100", soxLimit = "140" }: Opt = {}): DayData {
  const times = timesOf(n);
  return { times, stacks: { "S:1": { nox: times.map((_, i) => nox(i)), sox: times.map((_, i) => sox(i)), noxLimit, soxLimit } } };
}
/** NOx만 있는 하루(SOx는 측정·기준 없음). over로 칸별 값을 바꾼다 */
function dayWith(over: Record<number, string | null>, base: string | null = "50", limit: string | null = "100"): DayData {
  const times = timesOf(48);
  const nox = times.map((_, i) => (i in over ? over[i] : base));
  return { times, stacks: { "S:1": { nox, sox: nox.map(() => null), noxLimit: limit, soxLimit: null } } };
}

const dot = (c: HTMLElement) => c.querySelector(`svg circle[r="${DOT_R}"]`);
const cyOfDot = (c: HTMLElement) => Number(dot(c)!.getAttribute("cy"));
const yAt = (fraction: number) => TOP + IH - fraction * IH;
/** 물질 체크 상자와 그 카드 */
const box = (name: "NOx" | "SOx") => screen.getByRole("checkbox", { name: `${name} 그래프 표시` }) as HTMLInputElement;
const cardOf = (name: "NOx" | "SOx") => box(name).closest("label") as HTMLElement;
const seriesInSvg = (c: HTMLElement) => c.querySelectorAll("svg > g[data-series]");
const tickTexts = (c: HTMLElement) => [...c.querySelectorAll("svg text")].map((t) => t.textContent);

beforeEach(() => useSelection.setState({ ...initialSelection }));

describe("큰 체크 상자(카드): 안에 기준 대비 %를 보여 준다", () => {
  it("물질마다 큰 체크 상자가 있고 처음에는 NOx만 켜져 있다", () => {
    render(<TrendChart site={site} day={dayBoth()} />);
    expect(box("NOx")).toBeChecked();
    expect(box("SOx")).not.toBeChecked();
    expect(within(cardOf("NOx")).getByText("표시 켬")).toBeInTheDocument();
    expect(within(cardOf("SOx")).getByText("표시 끔")).toBeInTheDocument();
  });

  it("카드 안에 선택한 시점의 기준 대비 %와 단계가 들어 있다(단일 물질이어도 %)", () => {
    render(<TrendChart site={site} day={dayBoth({ nox: () => "74", sox: () => "112" })} />); // NOx 74%(주의 이전=정상), SOx 80%
    expect(within(cardOf("NOx")).getByText("74%")).toBeInTheDocument();
    expect(within(cardOf("NOx")).getByText("주의")).toBeInTheDocument(); // 74% ≥ 70%
    expect(within(cardOf("SOx")).getByText("80%")).toBeInTheDocument();
    expect(within(cardOf("SOx")).getByText("경고")).toBeInTheDocument(); // 80% ≥ 80%
  });

  it("꺼 둔 물질의 카드에도 값이 보인다(켜기 전에 확인할 수 있다)", () => {
    render(<TrendChart site={site} day={dayBoth()} />);
    expect(box("SOx")).not.toBeChecked();
    expect(within(cardOf("SOx")).getByText("50%")).toBeInTheDocument();
  });

  it("카드는 눌러서 켜고 끈다(상자 안 글자를 눌러도 된다)", async () => {
    const { container } = render(<TrendChart site={site} day={dayBoth()} />);
    await userEvent.click(within(cardOf("SOx")).getByText("SOx"));
    expect(box("SOx")).toBeChecked();
    expect(seriesInSvg(container)).toHaveLength(2);
  });

  it("측정값이 없는 시점은 카드에 공백과 사유가 나온다", () => {
    render(<TrendChart site={site} day={dayWith({ 47: "미수신" })} />);
    // NOx만 측정하는 굴뚝: 체크 상자 없이 한 줄로 보여 준다
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(within(screen.getByLabelText("NOx 단일 측정")).getByText("측정 공백 (미수신)")).toBeInTheDocument();
  });

  it("한 물질만 측정하는 굴뚝은 체크 상자가 없고 그 물질을 늘 그린다(선택이 꺼져 있어도)", () => {
    useSelection.setState({ ...initialSelection, pollutants: [] });
    const { container } = render(<TrendChart site={site} day={dayWith({})} />);
    expect(screen.queryByRole("checkbox")).toBeNull();
    const one = within(screen.getByLabelText("NOx 단일 측정"));
    expect(one.getByText("50%")).toBeInTheDocument();
    expect(one.getByText("단일 측정")).toBeInTheDocument();
    expect(seriesInSvg(container)).toHaveLength(1);
  });

  it("SOx만 측정하는 굴뚝도 마찬가지다", () => {
    const times = timesOf(48);
    const day = { times, stacks: { "S:1": { nox: times.map(() => null), sox: times.map(() => "70"), noxLimit: null, soxLimit: "140" } } };
    render(<TrendChart site={site} day={day} />);
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(within(screen.getByLabelText("SOx 단일 측정")).getByText("50%")).toBeInTheDocument();
  });

  it("기준값이 없는 물질은 비율을 알 수 없어 켤 수 없고 이유를 적는다", () => {
    render(<TrendChart site={site} day={dayBoth({ soxLimit: null })} />);
    expect(box("SOx")).toBeDisabled();
    expect(within(cardOf("SOx")).getByText("기준값 없음")).toBeInTheDocument();
    expect(within(cardOf("SOx")).getByText("비율을 알 수 없음")).toBeInTheDocument();
  });
});

describe("두 물질 동시에 보기 · 둘 다 끄기", () => {
  it("SOx를 켜면 두 물질이 한 차트에 함께 그려진다", async () => {
    const { container } = render(<TrendChart site={site} day={dayBoth()} />);
    await userEvent.click(box("SOx"));
    expect(box("NOx")).toBeChecked();
    expect(box("SOx")).toBeChecked();
    expect(seriesInSvg(container)).toHaveLength(2);
  });

  it("둘 다 끌 수 있다: 그래프 대신 안내가 나오고 카드의 값은 그대로 보인다", async () => {
    const { container } = render(<TrendChart site={site} day={dayBoth()} />);
    await userEvent.click(box("NOx"));
    expect(box("NOx")).not.toBeChecked();
    expect(container.querySelector("svg[role='img']")).toBeNull();
    expect(screen.getByText("물질을 하나 이상 켜면 그래프가 나옵니다.")).toBeInTheDocument();
    expect(within(cardOf("NOx")).getByText("50%")).toBeInTheDocument();
    await userEvent.click(box("SOx")); // 다시 켜면 돌아온다
    expect(container.querySelector("svg[role='img']")).not.toBeNull();
  });

  it("모양으로도 구분한다: NOx는 원, SOx는 사각형", async () => {
    const { container } = render(<TrendChart site={site} day={dayBoth()} />);
    await userEvent.click(box("SOx"));
    expect(container.querySelectorAll(`svg circle[r="${DOT_R}"]`)).toHaveLength(1);
    expect(container.querySelectorAll('svg rect[data-marker="square"]')).toHaveLength(1);
  });

  it("같은 비율은 같은 높이다(각자 기준 대비 %로 같은 눈금)", async () => {
    const { container } = render(<TrendChart site={site} day={dayBoth()} />);
    await userEvent.click(box("SOx"));
    const cy = cyOfDot(container);
    const sq = container.querySelector('svg rect[data-marker="square"]')!;
    expect(Number(sq.getAttribute("y")) + DOT_R - 0.5).toBeCloseTo(cy);
    expect(cy).toBeCloseTo(yAt(0.4)); // 기준의 50% = 높이의 40%
  });

  it("한 물질이 크게 넘어가면 위쪽 한계가 둘에 공통으로 늘어난다", async () => {
    const { container } = render(<TrendChart site={site} day={dayBoth({ sox: (i) => (i === 10 ? "420" : "70") })} />); // SOx 300%
    await userEvent.click(box("SOx"));
    expect(tickTexts(container)).toContain("320%");
    expect(cyOfDot(container)).toBeCloseTo(yAt(0.4)); // NOx(50%)의 높이는 그대로
  });

  it("선택한 시점을 바꾸면 두 카드의 값이 함께 바뀐다", async () => {
    const { container } = render(<TrendChart site={site} day={dayBoth({ nox: (i) => String(10 + i), sox: (i) => String(70 + i) })} />);
    await userEvent.click(box("SOx"));
    fireEvent.click(container.querySelector("svg[role='img']")!, { clientX: CHART.PAD.l }); // 왼쪽 끝 = 첫 시점
    expect(within(cardOf("NOx")).getByText("10%")).toBeInTheDocument(); // 10/100
    expect(within(cardOf("SOx")).getByText("50%")).toBeInTheDocument(); // 70/140
    expect(container.textContent).not.toContain("(최신)");
  });

  it("켜 둔 물질에 기준값이 없으면 그래프에서 빼고 이유를 알린다", () => {
    useSelection.setState({ ...initialSelection, pollutants: ["nox", "sox"] });
    const { container } = render(<TrendChart site={site} day={dayBoth({ soxLimit: null })} />);
    expect(seriesInSvg(container)).toHaveLength(1);
    expect(container.textContent).toContain("SOx은(는) 기준값이 없어 기준 대비(%)로 나타낼 수 없습니다");
  });

  it("켜 둔 물질이 모두 기준값이 없으면 그릴 수 없다고 알린다", () => {
    const { container } = render(<TrendChart site={site} day={dayWith({}, "50", null)} />);
    expect(container.querySelector("svg[role='img']")).toBeNull();
    expect(screen.getByText("켜 둔 물질은 기준값이 없어 기준 대비(%)로 그릴 수 없습니다.")).toBeInTheDocument();
  });
});

describe("절대 수치(ppm)는 보이지 않는다: 상대 수치(%)만", () => {
  const states: Array<[string, () => HTMLElement]> = [
    ["단일 물질", () => render(<TrendChart site={site} day={dayBoth()} />).container],
    ["두 물질", () => { useSelection.setState({ ...initialSelection, pollutants: ["nox", "sox"] }); return render(<TrendChart site={site} day={dayBoth()} />).container; }],
    ["기준값 없음", () => render(<TrendChart site={site} day={dayBoth({ soxLimit: null })} />).container],
    ["측정 공백", () => render(<TrendChart site={site} day={dayWith({ 47: "미수신" })} />).container],
    ["크게 초과", () => render(<TrendChart site={site} day={dayWith({ 47: "900" })} />).container],
  ];
  for (const [label, make] of states) {
    it(`${label}: 어디에도 ppm이 없다`, () => {
      expect(make().textContent).not.toMatch(/ppm/i);
    });
  }

  it("세로 눈금은 모두 %다(단일 물질이어도)", () => {
    const { container } = render(<TrendChart site={site} day={dayBoth()} />);
    const ticks = tickTexts(container);
    expect(ticks).toContain("120%");
    expect(ticks).toContain("100%");
    expect(ticks).toContain("0%");
    // 측정값 눈금(100, 140 같은 맨숫자)이 없다
    expect(ticks.filter((t) => /^\d+$/.test(t ?? ""))).toEqual([]);
  });

  it("기준값 숫자는 화면에 나오지 않는다(상세 패널 포함)", () => {
    render(<TrendChart site={site} day={dayBoth({ noxLimit: "115", soxLimit: "140" })} />);
    const chart = screen.getByRole("region", { name: "추세 차트" });
    expect(chart.textContent).not.toContain("115");
    expect(chart.textContent).not.toContain("140");
  });

  it("비율 표기: 10% 이상은 정수, 그 아래는 소수 한 자리", () => {
    expect(formatPct(74.4)).toBe("74%");
    expect(formatPct(105)).toBe("105%");
    expect(formatPct(9.96)).toBe("10%");
    expect(formatPct(3.456)).toBe("3.5%");
    expect(formatPct(0)).toBe("0%");
  });
});

describe("차트 세로 눈금: 기준 아래 80% 고정 + 위쪽 20% 가변", () => {
  it("기준값(100%)의 점은 그림 높이의 80% 자리에 놓인다", () => {
    const { container } = render(<TrendChart site={site} day={dayWith({ 47: "100" })} />);
    expect(cyOfDot(container)).toBeCloseTo(yAt(0.8));
  });
  it("기준의 50%는 40% 자리, 70%·80%·90% 기준선은 80% 안쪽에 등분되어 있다", () => {
    const { container } = render(<TrendChart site={site} day={dayWith({ 47: "50" })} />);
    expect(cyOfDot(container)).toBeCloseTo(yAt(0.4));
    const lines = [...container.querySelectorAll("line")].map((l) => Number(l.getAttribute("y1")));
    for (const pct of [70, 80, 90, 100]) {
      expect(lines.some((y) => Math.abs(y - yAt((0.8 * pct) / 100)) < 0.01)).toBe(true);
    }
  });
  it("기본 위쪽 한계는 120%: 120%의 점은 맨 위에 닿는다", () => {
    const { container } = render(<TrendChart site={site} day={dayWith({ 47: "120" })} />);
    expect(cyOfDot(container)).toBeCloseTo(TOP);
  });
  it("기준을 조금 넘으면(110%) 위쪽 20%의 중간에 놓인다", () => {
    const { container } = render(<TrendChart site={site} day={dayWith({ 47: "110" })} />);
    expect(cyOfDot(container)).toBeCloseTo(yAt(0.9));
  });
  it("값이 크게 넘어가면 위쪽 한계가 늘어나 꼭대기 안에 들어온다(잘리거나 뾰족해지지 않는다)", () => {
    const { container } = render(<TrendChart site={site} day={dayWith({ 47: "300" })} />);
    const cy = cyOfDot(container);
    expect(cy).toBeGreaterThan(TOP);
    expect(cy).toBeLessThan(yAt(0.8));
    expect(tickTexts(container)).toContain("320%");
  });
  it("위쪽에 큰 값이 있어도 아래쪽 80%의 점 위치는 변하지 않는다", () => {
    const calm = render(<TrendChart site={site} day={dayWith({})} />);
    const spiky = render(<TrendChart site={site} day={dayWith({ 10: "900" })} />);
    expect(cyOfDot(spiky.container)).toBeCloseTo(cyOfDot(calm.container));
    expect(cyOfDot(calm.container)).toBeCloseTo(yAt(0.4));
  });
  it("기준 초과 영역(위쪽 20%)이 표시된다", () => {
    const { container } = render(<TrendChart site={site} day={dayWith({})} />);
    const zone = container.querySelector('[data-zone="exceed"] rect')!;
    expect(Number(zone.getAttribute("y"))).toBeCloseTo(TOP);
    expect(Number(zone.getAttribute("height"))).toBeCloseTo(IH * 0.2);
    expect(container.textContent).toContain("기준 초과 영역");
  });
});

describe("값이 없는 구간: 점선으로 잇고 점선 아래만 옅게 칠하기", () => {
  const gapOver = (from: number, to: number, raw: string | null = "미수신") => {
    const o: Record<number, string | null> = {};
    for (let i = from; i <= to; i++) o[i] = raw;
    return o;
  };
  const pointsOfPath = (d: string) => [...d.matchAll(/(-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)/g)].map((m) => [Number(m[1]), Number(m[2])] as const);

  it("가운데가 비면 양쪽 실측 사이를 점선으로 잇고 그 아래를 칠한다", () => {
    const { container } = render(<TrendChart site={site} day={dayWith(gapOver(20, 25))} />);
    const bridge = container.querySelectorAll('[data-gap-link="bridge"]');
    expect(bridge).toHaveLength(1);
    const [fill, line] = [...bridge[0].querySelectorAll("path")];
    expect(line.getAttribute("stroke-dasharray")).toBeTruthy(); // 점선
    expect(fill.getAttribute("fill")).toMatch(/^url\(#gapfill-/);
    expect(fill.getAttribute("d")).toMatch(/Z$/);
  });

  it("칠한 영역은 점선 아래쪽뿐이다: 점선보다 위로는 한 점도 올라가지 않는다", () => {
    const { container } = render(<TrendChart site={site} day={dayWith({ ...gapOver(20, 25), 30: "90" })} />);
    for (const g of container.querySelectorAll("[data-gap-link]")) {
      const [fill, line] = [...g.querySelectorAll("path")];
      const lp = pointsOfPath(line.getAttribute("d")!), fp = pointsOfPath(fill.getAttribute("d")!);
      expect(lp).toHaveLength(2);
      expect(fp.length).toBeGreaterThanOrEqual(4);
      expect(Math.min(...fp.map(([, y]) => y))).toBeGreaterThanOrEqual(Math.min(...lp.map(([, y]) => y)) - 1e-6);
    }
  });

  it("차트 전체 높이를 덮는 회색 띠는 없다", () => {
    const { container } = render(<TrendChart site={site} day={dayWith(gapOver(20, 25))} />);
    const full = [...container.querySelectorAll("rect")].filter((r) => (r.getAttribute("fill") ?? "").startsWith("url(#gap-"));
    expect(full).toHaveLength(0);
  });

  it("점선 구간은 종류와 상관없이 같은 방식으로 칠한다(앞·가운데·뒤)", () => {
    const over = { ...gapOver(0, 3), ...gapOver(20, 22, "기기점검"), ...gapOver(46, 47, "미수신") };
    const { container } = render(<TrendChart site={site} day={dayWith(over)} />);
    const kinds = [...container.querySelectorAll("[data-gap-link]")].map((g) => g.getAttribute("data-gap-link"));
    expect(kinds).toEqual(["leading", "bridge", "trailing"]);
    const fills = [...container.querySelectorAll("[data-gap-link] path:first-child")].map((p) => p.getAttribute("fill"));
    expect(new Set(fills).size).toBe(1);
  });

  it("값이 없는 칸은 모두 칠해진 구간 안에 들어간다(빈 영역이 남지 않는다)", () => {
    const over = { ...gapOver(0, 4), ...gapOver(10, 12), ...gapOver(40, 47) };
    const { container } = render(<TrendChart site={site} day={dayWith(over)} />);
    const xOf = (i: number) => CHART.PAD.l + (i / 47) * CHART.iw;
    const spans = [...container.querySelectorAll("[data-gap-link] path:first-child")].map((p) => {
      const xs = pointsOfPath(p.getAttribute("d")!).map(([x]) => x);
      return [Math.min(...xs), Math.max(...xs)] as const;
    });
    for (const i of [...Array(5).keys(), 10, 11, 12, ...Array.from({ length: 8 }, (_, k) => 40 + k)]) {
      expect(spans.some(([a, b]) => xOf(i) >= a - 0.1 && xOf(i) <= b + 0.1)).toBe(true);
    }
  });

  it("칠한 영역에 올리면 공백 사유(미수신·기기점검)가 안내된다", () => {
    const over = { ...gapOver(10, 12, "미수신"), ...gapOver(30, 31, "기기점검") };
    const { container } = render(<TrendChart site={site} day={dayWith(over)} />);
    const titles = [...container.querySelectorAll("[data-gap-link] title")].map((t) => t.textContent);
    expect(titles).toEqual(["측정 공백 · 미수신", "측정 공백 · 기기점검"]);
  });

  it("두 물질의 빈 구간 점선은 각자 자기 색으로 그려진다", async () => {
    const nox = (i: number) => (i >= 20 && i <= 25 ? "미수신" : "50");
    const sox = (i: number) => (i >= 30 && i <= 31 ? "기기점검" : "70");
    const { container } = render(<TrendChart site={site} day={dayBoth({ nox, sox })} />);
    await userEvent.click(box("SOx"));
    const noxLink = container.querySelector('g[data-series="nox"] [data-gap-link="bridge"] path:last-child')!;
    const soxLink = container.querySelector('g[data-series="sox"] [data-gap-link="bridge"] path:last-child')!;
    expect(noxLink.getAttribute("stroke")).toBe("var(--accent)");
    expect(soxLink.getAttribute("stroke")).toBe("var(--series-2)");
  });

  it("실측이 하나도 없을 때만 기간 전체를 옅게 칠한다", () => {
    const { container } = render(<TrendChart site={site} day={dayWith({}, "보수중")} />);
    expect(container.querySelectorAll("[data-gap-link]")).toHaveLength(0);
    const bands = [...container.querySelectorAll("rect")].filter((r) => (r.getAttribute("fill") ?? "").startsWith("url(#gap-"));
    expect(bands.length).toBeGreaterThan(0);
  });

  it("이은 점선은 추정일 뿐이라 값 점을 찍지 않는다", () => {
    const { container } = render(<TrendChart site={site} day={dayWith({ 47: "미수신" })} />);
    expect(dot(container)).toBeNull();
  });
});

describe("조회 범위: 달력·구간 이동·슬라이더·끌기", () => {
  const range = () => screen.getByRole("region", { name: "조회 범위" });
  const summary = () => within(range()).getByRole("status");
  const startInput = () => within(range()).getByLabelText("시작 일시") as HTMLInputElement;
  const endInput = () => within(range()).getByLabelText("종료 일시") as HTMLInputElement;
  const btn = (name: string | RegExp) => within(range()).getByRole("button", { name });
  const slider = () => within(range()).getByLabelText("조회 구간 위치") as HTMLInputElement;
  const periodChip = (name: string) => within(screen.getByRole("group", { name: "기간" })).getByRole("button", { name });

  it("시작·종료 일시를 고르는 달력 입력이 있고, 고를 수 있는 날짜는 보관된 기간으로 제한된다", () => {
    render(<TrendChart site={site} day={dayBoth()} />);
    for (const input of [startInput(), endInput()]) {
      expect(input).toHaveAttribute("type", "datetime-local");
      expect(input).toHaveAttribute("min", "2026-11-10T00:00");
      expect(input).toHaveAttribute("max", "2026-11-10T23:30");
      expect(input).toHaveAttribute("step", "1800");
    }
    expect(startInput().value).toBe("2026-11-10T00:00");
    expect(endInput().value).toBe("2026-11-10T23:30");
  });

  it("처음에는 자료 기준 기본 범위를 요약한다", () => {
    render(<TrendChart site={site} day={dayBoth()} />);
    expect(summary()).toHaveTextContent("기본 범위 · 11-10 00:00 → 11-10 23:30 · 23시간 30분");
  });

  it("기간 버튼은 자료가 채우는 길이만 있다(하루치면 6·12·24시간, 사흘치면 2일·3일까지)", () => {
    const { unmount } = render(<TrendChart site={site} day={dayBoth()} />);
    const names = (g: HTMLElement) => within(g).getAllByRole("button").map((b) => b.textContent);
    expect(names(screen.getByRole("group", { name: "기간" }))).toEqual(["6시간", "12시간", "24시간"]);
    unmount();
    render(<TrendChart site={site} day={dayBoth({ n: 144 })} />);
    expect(names(screen.getByRole("group", { name: "기간" }))).toEqual(["6시간", "12시간", "24시간", "2일", "3일"]);
  });

  it("시작·종료를 입력하고 조회 적용을 누르면 그 범위만 보인다", async () => {
    render(<TrendChart site={site} day={dayBoth()} />);
    fireEvent.change(startInput(), { target: { value: "2026-11-10T09:00" } });
    fireEvent.change(endInput(), { target: { value: "2026-11-10T12:00" } });
    await userEvent.click(btn("조회 적용"));
    expect(summary()).toHaveTextContent("사용자 지정 · 11-10 09:00 → 11-10 12:00 · 3시간");
    expect(useSelection.getState().chartRange).toEqual({ start: t0 + 18 * SLOT, end: t0 + 24 * SLOT });
    expect(screen.getByRole("region", { name: "추세 차트" })).toHaveTextContent("11-10 12:00 (최신)");
  });

  it("자료 기준으로 누르면 기본 범위로 돌아간다", async () => {
    render(<TrendChart site={site} day={dayBoth()} />);
    expect(btn("자료 기준으로")).toBeDisabled();
    fireEvent.change(startInput(), { target: { value: "2026-11-10T09:00" } });
    fireEvent.change(endInput(), { target: { value: "2026-11-10T12:00" } });
    await userEvent.click(btn("조회 적용"));
    await userEvent.click(btn("자료 기준으로"));
    expect(useSelection.getState().chartRange).toBeNull();
    expect(summary()).toHaveTextContent("기본 범위");
  });

  it("종료가 시작보다 앞이면 오류를 알리고 범위는 바뀌지 않는다", async () => {
    render(<TrendChart site={site} day={dayBoth()} />);
    fireEvent.change(startInput(), { target: { value: "2026-11-10T12:00" } });
    fireEvent.change(endInput(), { target: { value: "2026-11-10T09:00" } });
    await userEvent.click(btn("조회 적용"));
    expect(within(range()).getByRole("alert")).toHaveTextContent("종료는 시작보다 뒤여야 합니다");
    expect(useSelection.getState().chartRange).toBeNull();
  });

  it("보관된 기간 밖의 날짜를 넣으면 보관된 기간을 알려 준다", async () => {
    render(<TrendChart site={site} day={dayBoth()} />);
    fireEvent.change(startInput(), { target: { value: "2026-11-15T09:00" } });
    fireEvent.change(endInput(), { target: { value: "2026-11-15T12:00" } });
    await userEvent.click(btn("조회 적용"));
    expect(within(range()).getByRole("alert")).toHaveTextContent("보관된 기간(2026-11-10 00:00 ~ 2026-11-10 23:30) 밖입니다");
  });

  it("값을 고치면 오류 표시가 사라진다", async () => {
    render(<TrendChart site={site} day={dayBoth()} />);
    fireEvent.change(startInput(), { target: { value: "2026-11-10T12:00" } });
    fireEvent.change(endInput(), { target: { value: "2026-11-10T09:00" } });
    await userEvent.click(btn("조회 적용"));
    fireEvent.change(endInput(), { target: { value: "2026-11-10T13:00" } });
    expect(within(range()).queryByRole("alert")).toBeNull();
  });

  it("이전·다음 구간은 창에 든 칸 수만큼 넘기고 자료 끝에서 멈춘다", async () => {
    render(<TrendChart site={site} day={dayBoth()} />);
    await userEvent.click(periodChip("6시간"));
    expect(summary()).toHaveTextContent("5시간 30분");
    expect(btn(/다음 구간/)).toBeDisabled();
    await userEvent.click(btn(/이전 구간/));
    expect(useSelection.getState().chartRange).toEqual({ start: t0 + 24 * SLOT, end: t0 + 35 * SLOT });
    await userEvent.click(btn(/다음 구간/));
    expect(useSelection.getState().chartRange).toEqual({ start: t0 + 36 * SLOT, end: t0 + 47 * SLOT });
    for (let i = 0; i < 6; i++) if (!(btn(/이전 구간/) as HTMLButtonElement).disabled) await userEvent.click(btn(/이전 구간/));
    expect(btn(/이전 구간/)).toBeDisabled();
    expect(useSelection.getState().chartRange!.start).toBe(t0);
  });

  it("슬라이더로 구간을 30분 단위로 민다(구간이 자료 전체면 움직일 수 없다)", () => {
    const { unmount } = render(<TrendChart site={site} day={dayBoth()} />);
    expect(slider()).toBeDisabled();
    unmount();
    useSelection.setState({ ...initialSelection, periodHours: 6 });
    render(<TrendChart site={site} day={dayBoth()} />);
    expect(slider()).not.toBeDisabled();
    expect(slider()).toHaveAttribute("max", "36");
    fireEvent.change(slider(), { target: { value: "10" } });
    expect(useSelection.getState().chartRange).toEqual({ start: t0 + 10 * SLOT, end: t0 + 21 * SLOT });
    expect(summary()).toHaveTextContent("사용자 지정 · 11-10 05:00 → 11-10 10:30");
  });

  it("기간 버튼을 누르면 지정한 범위가 사라지고 그 길이의 기본 범위가 된다", async () => {
    render(<TrendChart site={site} day={dayBoth()} />);
    fireEvent.change(startInput(), { target: { value: "2026-11-10T09:00" } });
    fireEvent.change(endInput(), { target: { value: "2026-11-10T12:00" } });
    await userEvent.click(btn("조회 적용"));
    await userEvent.click(periodChip("12시간"));
    expect(useSelection.getState().chartRange).toBeNull();
    expect(periodChip("12시간")).toHaveAttribute("aria-pressed", "true");
    expect(summary()).toHaveTextContent("기본 범위 · 11-10 12:00 → 11-10 23:30");
  });

  it("그래프를 오른쪽으로 끌면 이전 시간대로 30분씩 이동한다", () => {
    useSelection.setState({ ...initialSelection, periodHours: 6 });
    const { container } = render(<TrendChart site={site} day={dayBoth()} />);
    const svg = container.querySelector("svg[role='img']") as SVGSVGElement;
    fireEvent.pointerDown(svg, { button: 0, clientX: 300, clientY: 100 });
    fireEvent.pointerMove(svg, { clientX: 400, clientY: 100 });
    fireEvent.pointerUp(svg, { button: 0, clientX: 400, clientY: 100 });
    const r = useSelection.getState().chartRange!;
    expect(r.end).toBeLessThan(t0 + 47 * SLOT); // 앞으로(과거 쪽) 이동했다
    expect(r.end - r.start).toBe(11 * SLOT); // 창 길이는 그대로
  });

  it("왼쪽으로 끌어도 자료의 끝을 넘지 않는다", () => {
    useSelection.setState({ ...initialSelection, periodHours: 6 });
    const { container } = render(<TrendChart site={site} day={dayBoth()} />);
    const svg = container.querySelector("svg[role='img']") as SVGSVGElement;
    fireEvent.pointerDown(svg, { button: 0, clientX: 400, clientY: 100 });
    fireEvent.pointerMove(svg, { clientX: 100, clientY: 100 });
    fireEvent.pointerUp(svg, { button: 0, clientX: 100, clientY: 100 });
    const r = useSelection.getState().chartRange;
    expect(r === null || r.end === t0 + 47 * SLOT).toBe(true);
  });

  it("끌고 놓은 뒤에는 시점이 선택되지 않고, 가만히 누르면 선택된다", () => {
    useSelection.setState({ ...initialSelection, periodHours: 6 });
    const { container } = render(<TrendChart site={site} day={dayBoth()} />);
    const svg = container.querySelector("svg[role='img']") as SVGSVGElement;
    fireEvent.pointerDown(svg, { button: 0, clientX: 300, clientY: 100 });
    fireEvent.pointerMove(svg, { clientX: 420, clientY: 100 });
    fireEvent.pointerUp(svg, { button: 0, clientX: 420, clientY: 100 });
    fireEvent.click(svg, { clientX: 420 });
    expect(container.textContent).toContain("(최신)");
    fireEvent.click(svg, { clientX: CHART.PAD.l });
    expect(container.textContent).not.toContain("(최신)");
  });

  it("지정한 범위는 물질을 바꿔도 유지되어 같은 시간대를 비교할 수 있다", async () => {
    render(<TrendChart site={site} day={dayBoth()} />);
    fireEvent.change(startInput(), { target: { value: "2026-11-10T09:00" } });
    fireEvent.change(endInput(), { target: { value: "2026-11-10T12:00" } });
    await userEvent.click(btn("조회 적용"));
    await userEvent.click(box("SOx"));
    expect(summary()).toHaveTextContent("사용자 지정 · 11-10 09:00 → 11-10 12:00");
  });

  it("범위를 좁히면 그 시간대의 값만 보인다(바깥 시점의 값은 나오지 않는다)", async () => {
    const nox = (i: number) => (i < 24 ? "10" : "90");
    render(<TrendChart site={site} day={dayBoth({ nox })} />);
    fireEvent.change(startInput(), { target: { value: "2026-11-10T00:00" } });
    fireEvent.change(endInput(), { target: { value: "2026-11-10T05:00" } });
    await userEvent.click(btn("조회 적용"));
    expect(within(cardOf("NOx")).getByText("10%")).toBeInTheDocument();
    expect(within(cardOf("NOx")).queryByText("90%")).toBeNull();
  });
});

describe("배치: 왼쪽 차트, 오른쪽 상세 패널(옛 웹과 같은 자리)", () => {
  it("조회 범위는 오른쪽 상세 패널 안에 있고 차트·물질·기간 버튼은 왼쪽에 있다", () => {
    const { container } = render(<TrendChart site={site} day={dayBoth()} />);
    const side = screen.getByRole("complementary", { name: "상세와 조회 범위" });
    expect(within(side).getByRole("region", { name: "조회 범위" })).toBeInTheDocument();
    expect(within(side).getByLabelText("시작 일시")).toBeInTheDocument();
    expect(within(side).getByRole("button", { name: "조회 적용" })).toBeInTheDocument();
    expect(side.contains(container.querySelector("svg[role='img']"))).toBe(false);
    expect(side.contains(screen.getByRole("group", { name: "물질" }))).toBe(false);
    expect(side.contains(screen.getByRole("group", { name: "기간" }))).toBe(false);
    const chart = container.querySelector("svg[role='img']")!;
    expect(chart.compareDocumentPosition(side) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("상세 패널에 사업장 정보가 있다: 이름·주소·지역·굴뚝·보관 기간(절대 수치는 없다)", () => {
    render(<TrendChart site={{ ...site, address: "서울 중구 테스트로 1" }} day={dayBoth()} />);
    const detail = within(screen.getByRole("complementary")).getByRole("region", { name: "사업장 정보" });
    expect(within(detail).getByRole("heading", { name: "시험공장" })).toBeInTheDocument();
    expect(detail).toHaveTextContent("서울 중구 테스트로 1");
    expect(detail).toHaveTextContent("서울 중구");
    expect(detail).toHaveTextContent("1번 (전체 1개)");
    expect(detail).toHaveTextContent("11-10 00:00 ~ 11-10 23:30");
    expect(detail.textContent).not.toMatch(/ppm|기준값/);
  });

  it("주소가 비어 있으면 안내 문구가 보인다", () => {
    render(<TrendChart site={site} day={dayBoth()} />);
    expect(within(screen.getByRole("complementary")).getByRole("region", { name: "사업장 정보" })).toHaveTextContent("주소 정보 없음");
  });

  it("상세 패널의 굴뚝 표시는 선택한 굴뚝을 따라간다", async () => {
    const two: Site = { ...site, stacks: [{ key: "S:1", code: "1" }, { key: "S:2", code: "2" }] };
    const times = timesOf(48);
    const one = { nox: times.map(() => "50"), sox: times.map(() => null), noxLimit: "100", soxLimit: null };
    render(<TrendChart site={two} day={{ times, stacks: { "S:1": one, "S:2": { ...one, noxLimit: "200" } } }} />);
    const detail = () => within(screen.getByRole("complementary")).getByRole("region", { name: "사업장 정보" });
    expect(detail()).toHaveTextContent("1번 (전체 2개)");
    useSelection.getState().selectSite("S", "2");
    await userEvent.click(within(screen.getByRole("group", { name: "굴뚝 선택" })).getByRole("button", { name: "굴뚝 2" }));
    expect(detail()).toHaveTextContent("2번 (전체 2개)");
    expect(within(screen.getByLabelText("NOx 단일 측정")).getByText("25%")).toBeInTheDocument(); // 50/200
  });
});
