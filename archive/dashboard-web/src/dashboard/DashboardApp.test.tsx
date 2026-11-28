import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DayData, Site, SiteState } from "../data/model";
import type { DashboardData } from "../data/useDay";
import type { LevelKey } from "../logic/status";
import { project } from "../map/geometry";
import { initialSelection, MAP_SHOW_ORDER, useSelection, type MapBounds } from "../state/selection";
import { ThemeProvider } from "../theme/theme";
import { inBounds, listAlerts } from "./AlertList";
import DashboardApp from "./DashboardApp";
import { findStacks, pointsOf, runsOf } from "./TrendChart";

const mk = (id: string, name: string, sido: string, gun: string, codes: string[]): Site => ({
  id, name, sido, sigungu: gun, address: `${sido} ${gun} 1`, lon: 127, lat: 37,
  stacks: codes.map((c) => ({ key: `${id}:${c}`, code: c })),
});
const sites = [
  mk("S1", "가나다공장", "서울", "중구", ["1"]),
  mk("S2", "라마바공장", "서울", "종로구", ["1", "2"]),
  mk("S3", "사아자공장", "경기", "수원시", ["1"]),
  mk("S4", "공백공장", "경기", "수원시", ["1"]),
];
const times = Array.from({ length: 48 }, (_, i) => Date.UTC(2026, 10, 9, 15, 0) + i * 1800000);
const fill = (v: (i: number) => string | null) => Array.from({ length: 48 }, (_, i) => v(i));
const day: DayData = {
  times,
  stacks: {
    "S1:1": { nox: fill(() => "95"), sox: fill(() => null), noxLimit: "100", soxLimit: null }, // 위험
    "S2:1": { nox: fill(() => "10"), sox: fill(() => null), noxLimit: "100", soxLimit: null }, // 정상
    "S2:2": { nox: fill(() => "105"), sox: fill(() => null), noxLimit: "100", soxLimit: null }, // 초과
    "S3:1": { nox: fill((i) => (i === 47 ? "보수중" : "72")), sox: fill(() => null), noxLimit: "100", soxLimit: null }, // 최신만 공백
    "S4:1": { nox: fill(() => "기기점검"), sox: fill(() => null), noxLimit: "100", soxLimit: null }, // 전부 공백
  },
};
const data: DashboardData = { sites, day, geo: [] };

function setup() {
  render(
    <ThemeProvider>
      <DashboardApp email="a@b.c" onLogout={() => {}} load={() => Promise.resolve(data)} />
    </ThemeProvider>,
  );
}

const scrollIntoView = vi.fn();
beforeEach(() => {
  scrollIntoView.mockClear();
  Element.prototype.scrollIntoView = scrollIntoView as unknown as typeof Element.prototype.scrollIntoView;
  useSelection.setState({ ...initialSelection, mapLevels: [...MAP_SHOW_ORDER] });
  // jsdom에는 캔버스 그리기가 없다. 지도는 그리기만 건너뛰고 나머지(목록·카드·차트)를 시험한다.
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
});

describe("관제 화면 통합", () => {
  it("단계별 사업장 수 카드를 채우고, 공백·정상은 세지 않는다", async () => {
    setup();
    const cards = await screen.findByRole("region", { name: "단계별 굴뚝 수" });
    const key = { 주의: "caution", 경고: "warn", 위험: "risk", 초과: "exceed" } as const;
    const text = (label: keyof typeof key) => cards.querySelector(`[data-level="${key[label]}"]`)!.textContent;
    // 데이터를 읽기 전에도 카드 틀은 보이므로 값이 채워질 때까지 기다린다
    await waitFor(() => expect(text("위험")).toContain("1")); // S1
    expect(text("초과")).toContain("1"); // S2 (굴뚝 2)
    expect(text("주의")).toContain("0"); // S3는 최신이 공백이라 세지 않는다
  });

  it("목록은 높은 단계부터, 공백 사업장은 나오지 않는다", async () => {
    setup();
    const list = await screen.findByRole("list", { name: "경고 목록" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("라마바공장"); // 초과
    expect(rows[1]).toHaveTextContent("가나다공장"); // 위험
    expect(screen.queryByText("공백공장")).toBeNull();
  });

  it("검색과 단계 필터가 목록을 줄인다", async () => {
    setup();
    await screen.findByRole("list", { name: "경고 목록" });
    await userEvent.type(screen.getByLabelText("경고 목록 검색"), "가나다");
    expect(within(screen.getByRole("list", { name: "경고 목록" })).getAllByRole("listitem")).toHaveLength(1);
    await userEvent.clear(screen.getByLabelText("경고 목록 검색"));
    await userEvent.click(screen.getByRole("button", { name: /초과/, pressed: false }));
    expect(within(screen.getByRole("list", { name: "경고 목록" })).getAllByRole("listitem")).toHaveLength(1);
  });

  it("목록에서 사업장을 고르면 차트에 최신 값이 나오고, 그 굴뚝으로 열린다", async () => {
    setup();
    await userEvent.click(await screen.findByText("라마바공장"));
    // 최악 굴뚝(2번, 105)이 선택된다
    const chart = await screen.findByRole("region", { name: "추세 차트" });
    expect(within(chart).getByText("105%")).toBeInTheDocument(); // 기준 대비 %로만 보인다
    expect(chart.textContent).not.toContain("ppm"); // 절대 수치(ppm)는 화면에 없다
    expect(screen.getByRole("button", { name: "굴뚝 2", pressed: true })).toBeInTheDocument();
    // 같은 사업장의 다른 굴뚝으로 바꾼다
    await userEvent.click(screen.getByRole("button", { name: "굴뚝 1" }));
    expect(await within(await screen.findByRole("region", { name: "추세 차트" })).findByText("10%")).toBeInTheDocument();
  });

  it("선택한 사업장을 목록에서 다시 누르면 선택이 해제된다", async () => {
    setup();
    const list = await screen.findByRole("list", { name: "경고 목록" });
    await userEvent.click(within(list).getByText("라마바공장"));
    expect(useSelection.getState().selectedSiteId).toBe("S2");
    expect(await screen.findByRole("region", { name: "추세 차트" })).toBeInTheDocument();
    await userEvent.click(within(list).getByText("라마바공장"));
    expect(useSelection.getState().selectedSiteId).toBeNull();
    expect(screen.queryByRole("region", { name: "추세 차트" })).toBeNull();
  });

  it("사업장을 고르면 바로 아래 굴뚝 그래프로 화면을 밀어 준다", async () => {
    setup();
    const list = await screen.findByRole("list", { name: "경고 목록" });
    expect(scrollIntoView).not.toHaveBeenCalled(); // 고르기 전에는 움직이지 않는다
    await userEvent.click(within(list).getByText("라마바공장"));
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(1));
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
    // 밀려 가는 대상은 굴뚝 그래프 구역이다
    const target = scrollIntoView.mock.contexts[0] as HTMLElement;
    expect(target.id).toBe("trend");
    expect(within(target).getByRole("region", { name: "추세 차트" })).toBeInTheDocument();
  });

  it("선택을 해제할 때는 화면을 밀지 않고, 다른 사업장을 고르면 다시 민다", async () => {
    setup();
    const list = await screen.findByRole("list", { name: "경고 목록" });
    await userEvent.click(within(list).getByText("라마바공장"));
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(1));
    await userEvent.click(within(list).getByText("라마바공장")); // 해제
    await new Promise((r) => setTimeout(r, 50));
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
    await userEvent.click(within(list).getByText("가나다공장"));
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(2));
  });

  it("즐겨찾기한 사업장이 위로 올라온다", async () => {
    setup();
    await screen.findByRole("list", { name: "경고 목록" });
    await userEvent.click(screen.getByRole("button", { name: "가나다공장 즐겨찾기" }));
    const rows = within(screen.getByRole("list", { name: "경고 목록" })).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("가나다공장");
  });

  it("데이터를 못 읽으면 그 사실을 알린다", async () => {
    render(
      <ThemeProvider>
        <DashboardApp email="a@b.c" onLogout={() => {}} load={() => Promise.reject(new Error("없음"))} />
      </ThemeProvider>,
    );
    expect((await screen.findAllByText(/데이터 연결 전 \(없음\)/)).length).toBeGreaterThan(0);
  });
});

describe("목록 고르기(순수): 검색어 없으면 지도에 보이는 경고, 있으면 전국 검색", () => {
  const at = (id: string, name: string, lon: number, lat: number, level: SiteState["level"], ratio: number | null = 90): SiteState => ({
    site: { id, name, sido: "서울", sigungu: "중구", address: `${name} 주소 ${id}`, lon, lat, stacks: [] },
    ratio, level, worstStack: "1",
  });
  /** 이 좌표 둘레의 지도 범위(월드 좌표) */
  const around = (lon: number, lat: number, d = 0.05): MapBounds => {
    const [x0, y0] = project(lon - d, lat + d), [x1, y1] = project(lon + d, lat - d);
    return { minX: x0, minY: y0, maxX: x1, maxY: y1 };
  };
  const base = { statuses: [] as LevelKey[], search: "", favorites: [] as string[], bounds: null, mapLevels: null };
  const A = at("A", "안쪽위험", 127.0, 37.5, "risk", 95); // 지도 안
  const B = at("B", "안쪽초과", 127.01, 37.51, "exceed", 120); // 지도 안
  const C = at("C", "바깥경고", 129.0, 35.1, "warn", 82); // 지도 밖(부산 쪽)
  const D = at("D", "안쪽정상", 127.0, 37.49, "ok", 20); // 지도 안, 정상
  const E = at("E", "안쪽공백", 127.02, 37.5, null, null); // 지도 안, 공백
  const all = [A, B, C, D, E];
  const view = around(127.0, 37.5);

  it("검색어가 없으면 지도 안에 있는 경고(주의 이상)만 나온다", () => {
    expect(listAlerts(all, { ...base, bounds: view }).map((s) => s.site.id)).toEqual(["B", "A"]); // 초과 → 위험
  });
  it("검색어가 없을 때 지도 밖 경고, 정상, 공백은 나오지 않는다", () => {
    const ids = listAlerts(all, { ...base, bounds: view }).map((s) => s.site.id);
    expect(ids).not.toContain("C");
    expect(ids).not.toContain("D");
    expect(ids).not.toContain("E");
  });
  it("지도 범위를 아직 모르면(null) 범위로는 거르지 않는다", () => {
    expect(listAlerts(all, base).map((s) => s.site.id)).toEqual(["B", "A", "C"]);
  });
  it("지도를 옮기면 목록이 바뀐다(부산 쪽으로 가면 바깥경고가 나온다)", () => {
    expect(listAlerts(all, { ...base, bounds: around(129.0, 35.1) }).map((s) => s.site.id)).toEqual(["C"]);
  });
  it("범위 경계 위의 점도 보인다(경계 포함)", () => {
    const [x, y] = project(A.site.lon, A.site.lat);
    expect(listAlerts([A], { ...base, bounds: { minX: x, minY: y, maxX: x, maxY: y } })).toHaveLength(1);
    expect(listAlerts([A], { ...base, bounds: { minX: x + 1e-6, minY: y, maxX: x + 1, maxY: y + 1 } })).toHaveLength(0);
  });
  it("지도에서 꺼 둔 상태는 목록에도 없다(지도에 안 보이니까)", () => {
    const ids = listAlerts(all, { ...base, bounds: view, mapLevels: ["ok", "caution", "warn", "risk", "gap"] }).map((s) => s.site.id);
    expect(ids).toEqual(["A"]); // 초과(B)를 끄면 빠진다
  });
  it("검색어가 있으면 지도 범위와 상관없이 전국에서 찾는다", () => {
    const ids = listAlerts(all, { ...base, bounds: view, search: "바깥" }).map((s) => s.site.id);
    expect(ids).toEqual(["C"]); // 지도 밖이지만 찾아진다
  });
  it("검색어가 있으면 정상·공백 사업장도 찾는다(경고가 아니어도)", () => {
    expect(listAlerts(all, { ...base, bounds: view, search: "안쪽정상" }).map((s) => s.site.id)).toEqual(["D"]);
    expect(listAlerts(all, { ...base, bounds: view, search: "안쪽공백" }).map((s) => s.site.id)).toEqual(["E"]);
  });
  it("검색어가 있으면 지도에서 꺼 둔 상태와도 상관없다", () => {
    const ids = listAlerts(all, { ...base, bounds: view, mapLevels: [], search: "안쪽" }).map((s) => s.site.id);
    expect(ids.sort()).toEqual(["A", "B", "D", "E"]);
  });
  it("이름·주소·코드로 찾고 대소문자를 가리지 않는다", () => {
    const s = [at("KR-01", "Alpha공장", 127, 37.5, "risk")];
    expect(listAlerts(s, { ...base, search: "alpha" })).toHaveLength(1);
    expect(listAlerts(s, { ...base, search: "주소 KR-01" })).toHaveLength(1);
    expect(listAlerts(s, { ...base, search: "kr-01" })).toHaveLength(1);
    expect(listAlerts(s, { ...base, search: "없는이름" })).toHaveLength(0);
  });
  it("공백뿐인 검색어는 검색이 아니다(지도에 보이는 경고 모드)", () => {
    expect(listAlerts(all, { ...base, bounds: view, search: "   " }).map((s) => s.site.id)).toEqual(["B", "A"]);
  });
  it("목록 자체의 단계 필터는 두 모드 모두에 적용된다", () => {
    expect(listAlerts(all, { ...base, bounds: view, statuses: ["risk"] }).map((s) => s.site.id)).toEqual(["A"]);
    expect(listAlerts(all, { ...base, statuses: ["warn"], search: "공장" }).map((s) => s.site.id)).toEqual([]); // 이름에 '공장'이 없다
    expect(listAlerts(all, { ...base, statuses: ["warn"], search: "바깥" }).map((s) => s.site.id)).toEqual(["C"]);
  });
  it("즐겨찾기가 먼저, 그다음 단계 높은 순, 같은 단계는 비율 높은 순", () => {
    const x = [at("1", "가", 127, 37.5, "warn", 85), at("2", "나", 127, 37.5, "warn", 90), at("3", "다", 127, 37.5, "exceed", 110), at("4", "라", 127, 37.5, "caution", 75)];
    expect(listAlerts(x, base).map((s) => s.site.id)).toEqual(["3", "2", "1", "4"]);
    expect(listAlerts(x, { ...base, favorites: ["4"] }).map((s) => s.site.id)).toEqual(["4", "3", "2", "1"]);
  });
  it("검색 결과에서도 경고가 위, 정상·공백이 아래에 온다", () => {
    expect(listAlerts(all, { ...base, search: "안쪽" }).map((s) => s.site.id)).toEqual(["B", "A", "D", "E"]);
  });
  it("지도 범위 판정 함수", () => {
    expect(inBounds(A, view)).toBe(true);
    expect(inBounds(C, view)).toBe(false);
  });
});

describe("경고 목록 화면: 지도에 보이는 사업장 / 전국 검색", () => {
  // 경도가 서로 다른 사업장들: 서울 쪽 둘, 부산 쪽 하나
  const geoSite = (id: string, name: string, lon: number, lat: number): Site => ({
    id, name, sido: "서울", sigungu: "중구", address: `${name} 주소`, lon, lat, stacks: [{ key: `${id}:1`, code: "1" }],
  });
  const mapSites = [geoSite("N1", "서울위험공장", 127.0, 37.5), geoSite("N2", "서울경고공장", 127.02, 37.52), geoSite("P1", "부산초과공장", 129.0, 35.1), geoSite("Z1", "서울정상공장", 127.01, 37.49)];
  const series = (v: string) => ({ nox: fill(() => v), sox: fill(() => null), noxLimit: "100", soxLimit: null });
  const mapDay: DayData = { times, stacks: { "N1:1": series("95"), "N2:1": series("82"), "P1:1": series("110"), "Z1:1": series("20") } };
  const mapData: DashboardData = { sites: mapSites, day: mapDay, geo: [] };
  const aroundSeoul = (): MapBounds => {
    const [x0, y0] = project(126.9, 37.6), [x1, y1] = project(127.1, 37.4);
    return { minX: x0, minY: y0, maxX: x1, maxY: y1 };
  };
  const names = () => within(screen.getByRole("list", { name: "경고 목록" })).getAllByRole("listitem").map((r) => r.querySelector("button")!.textContent);

  function setupMap() {
    render(
      <ThemeProvider>
        <DashboardApp email="a@b.c" onLogout={() => {}} load={() => Promise.resolve(mapData)} />
      </ThemeProvider>,
    );
  }

  it("검색어가 없으면 지금 지도에 보이는 경고만 나온다(지도 밖 경고, 정상은 안 나온다)", async () => {
    setupMap();
    await screen.findByRole("list", { name: "경고 목록" });
    act(() => useSelection.getState().setMapBounds(aroundSeoul()));
    const rows = names();
    expect(rows).toHaveLength(2);
    expect(rows[0]).toContain("서울위험공장");
    expect(rows[1]).toContain("서울경고공장");
    expect(screen.getByText(/지금 지도에 보이는 경고/)).toBeInTheDocument();
  });

  it("지도를 부산 쪽으로 옮기면 목록도 따라 바뀐다", async () => {
    setupMap();
    await screen.findByRole("list", { name: "경고 목록" });
    act(() => useSelection.getState().setMapBounds(aroundSeoul()));
    expect(names()).toHaveLength(2);
    const [x0, y0] = project(128.9, 35.2), [x1, y1] = project(129.1, 35.0);
    act(() => useSelection.getState().setMapBounds({ minX: x0, minY: y0, maxX: x1, maxY: y1 }));
    const rows = names();
    expect(rows).toHaveLength(1);
    expect(rows[0]).toContain("부산초과공장");
  });

  it("지도에 보이는 경고가 없으면 안내와 함께 검색을 권한다", async () => {
    setupMap();
    await screen.findByRole("list", { name: "경고 목록" });
    const [x0, y0] = project(131, 36), [x1, y1] = project(132, 35); // 바다 한가운데
    act(() => useSelection.getState().setMapBounds({ minX: x0, minY: y0, maxX: x1, maxY: y1 }));
    expect(screen.getByText(/지금 지도에 보이는 경고가 없습니다/)).toBeInTheDocument();
  });

  it("검색어를 넣으면 지도 밖 사업장도 전국에서 찾고, 정상 사업장도 나온다", async () => {
    setupMap();
    await screen.findByRole("list", { name: "경고 목록" });
    act(() => useSelection.getState().setMapBounds(aroundSeoul()));
    await userEvent.type(screen.getByLabelText("경고 목록 검색"), "부산");
    expect(names()).toHaveLength(1);
    expect(names()[0]).toContain("부산초과공장"); // 지도(서울) 밖이지만 찾아진다
    expect(screen.getByText(/전국 검색 결과/)).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("경고 목록 검색"));
    await userEvent.type(screen.getByLabelText("경고 목록 검색"), "정상");
    expect(names()[0]).toContain("서울정상공장"); // 경고가 아니어도 검색된다
  });

  it("검색어를 지우면 다시 지도에 보이는 경고로 돌아온다", async () => {
    setupMap();
    await screen.findByRole("list", { name: "경고 목록" });
    act(() => useSelection.getState().setMapBounds(aroundSeoul()));
    await userEvent.type(screen.getByLabelText("경고 목록 검색"), "공장");
    expect(names().length).toBeGreaterThan(2); // 전국
    await userEvent.clear(screen.getByLabelText("경고 목록 검색"));
    expect(names()).toHaveLength(2); // 지도에 보이는 것만
  });

  it("지도에서 끈 상태(초과)는 목록에서도 빠지고, 검색하면 다시 찾을 수 있다", async () => {
    setupMap();
    await screen.findByRole("list", { name: "경고 목록" });
    const [x0, y0] = project(126.9, 37.6), [x1, y1] = project(129.2, 35.0); // 서울~부산이 다 보이는 범위
    act(() => useSelection.getState().setMapBounds({ minX: x0, minY: y0, maxX: x1, maxY: y1 }));
    expect(names()).toHaveLength(3);
    act(() => useSelection.getState().toggleMapLevel("exceed")); // 지도에서 초과를 끈다
    expect(names().some((n) => n?.includes("부산초과공장"))).toBe(false);
    await userEvent.type(screen.getByLabelText("경고 목록 검색"), "부산");
    expect(names()[0]).toContain("부산초과공장");
  });

  it("검색으로 찾은 사업장을 고르면 선택된다(지도는 그곳으로 이동한다)", async () => {
    setupMap();
    await screen.findByRole("list", { name: "경고 목록" });
    act(() => useSelection.getState().setMapBounds(aroundSeoul()));
    await userEvent.type(screen.getByLabelText("경고 목록 검색"), "부산");
    await userEvent.click(within(screen.getByRole("list", { name: "경고 목록" })).getByText("부산초과공장"));
    expect(useSelection.getState().selectedSiteId).toBe("P1");
  });

  it("공백 사업장은 검색하면 '공백'으로 나온다", async () => {
    const gapSites = [geoSite("G1", "공백시험공장", 127, 37.5)];
    const gapDay: DayData = { times, stacks: { "G1:1": { nox: fill(() => "미수신"), sox: fill(() => null), noxLimit: "100", soxLimit: null } } };
    render(
      <ThemeProvider>
        <DashboardApp email="a@b.c" onLogout={() => {}} load={() => Promise.resolve({ sites: gapSites, day: gapDay, geo: [] })} />
      </ThemeProvider>,
    );
    await screen.findByRole("list", { name: "경고 목록" }).catch(() => null);
    await userEvent.type(screen.getByLabelText("경고 목록 검색"), "공백시험");
    const row = within(screen.getByRole("list", { name: "경고 목록" })).getAllByRole("listitem")[0];
    expect(row).toHaveTextContent("공백");
    expect(row).toHaveTextContent("—");
  });
});

describe("차트 점 만들기(순수)", () => {
  it("기간만큼 뒤에서 자르고, 문구는 값 없음으로 둔다", () => {
    const raws = fill((i) => (i === 47 ? "보수중" : String(i)));
    const pts = pointsOf(raws, 6);
    expect(pts).toHaveLength(12);
    expect(pts[11]).toMatchObject({ slot: 47, value: null, raw: "보수중" });
  });
  it("값 구간은 공백에서 끊긴다", () => {
    const pts = pointsOf(["1", "2", null, "기기점검", "5"], 24);
    const runs = runsOf(pts);
    expect(runs.map((r) => r.length)).toEqual([2, 1]);
  });
});

describe("굴뚝이 많은 사업장", () => {
  const many: Site = mk("M", "굴뚝많은공장", "전남", "광양시", Array.from({ length: 23 }, (_, i) => String(i + 1)));
  const manyDay: DayData = {
    times,
    stacks: Object.fromEntries(
      many.stacks.map((s, i) => [s.key, { nox: fill(() => String(60 + i)), sox: fill(() => null), noxLimit: "100", soxLimit: null }]),
    ),
  };
  const load = () => Promise.resolve({ sites: [many], day: manyDay, geo: [] });

  it("10개를 넘으면 줄 대신 번호 검색으로 고른다", async () => {
    render(
      <ThemeProvider>
        <DashboardApp email="a@b.c" onLogout={() => {}} load={load} />
      </ThemeProvider>,
    );
    await userEvent.click(await screen.findByText("굴뚝많은공장"));
    expect(await screen.findByLabelText("굴뚝 번호 검색")).toBeInTheDocument();
    // 23개 버튼이 줄지어 나오지 않는다(선택된 굴뚝 하나만)
    expect(screen.getAllByRole("button", { name: /^굴뚝 \d+$/ })).toHaveLength(1);
    await userEvent.type(screen.getByLabelText("굴뚝 번호 검색"), "17");
    await userEvent.click(screen.getByRole("button", { name: "굴뚝 17" }));
    expect(await within(await screen.findByRole("region", { name: "추세 차트" })).findByText("76%")).toBeInTheDocument(); // 17번 = 60+16
    expect(screen.getByRole("button", { name: "굴뚝 17", pressed: true })).toBeInTheDocument();
  });

  it("없는 번호는 없다고 알려 준다", async () => {
    render(
      <ThemeProvider>
        <DashboardApp email="a@b.c" onLogout={() => {}} load={load} />
      </ThemeProvider>,
    );
    await userEvent.click(await screen.findByText("굴뚝많은공장"));
    await userEvent.type(await screen.findByLabelText("굴뚝 번호 검색"), "99");
    expect(screen.getByText("해당 번호의 굴뚝이 없습니다.")).toBeInTheDocument();
  });
});

describe("굴뚝 번호 찾기(순수)", () => {
  const stacks = ["1", "2", "10", "11", "A-3"].map((c) => ({ key: `X:${c}`, code: c }));
  it("포함 검색이고 숫자 순으로 나온다", () => {
    expect(findStacks(stacks, "1").map((s) => s.code)).toEqual(["1", "10", "11"]);
  });
  it("빈 검색어는 아무것도 보여 주지 않는다", () => {
    expect(findStacks(stacks, "  ")).toEqual([]);
  });
  it("대소문자를 가리지 않는다", () => {
    expect(findStacks(stacks, "a-").map((s) => s.code)).toEqual(["A-3"]);
  });
});

describe("즐겨찾기 화면", () => {
  it("차트 머리의 별로 켜고 끌 수 있고, 목록의 별과 같은 상태를 본다", async () => {
    setup();
    await screen.findByRole("list", { name: "경고 목록" });
    act(() => useSelection.getState().selectSite("S1", "1"));
    const stars = await screen.findAllByRole("button", { name: "가나다공장 즐겨찾기" }); // 목록 한 줄 + 차트 머리
    expect(stars).toHaveLength(2);
    await userEvent.click(stars[stars.length - 1]);
    expect(useSelection.getState().favorites).toEqual(["S1"]);
    for (const b of screen.getAllByRole("button", { name: "가나다공장 즐겨찾기" })) expect(b).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getAllByRole("button", { name: "가나다공장 즐겨찾기" })[0]);
    expect(useSelection.getState().favorites).toEqual([]);
  });

  it("'즐겨찾기만 보기'를 켜면 목록은 내 사업장만(정상·공백 포함), 지도 칩과 같은 상태를 쓴다", async () => {
    setup();
    await screen.findByRole("list", { name: "경고 목록" });
    act(() => useSelection.setState({ favorites: ["S3", "S4"] })); // S3는 최신 공백, S4는 전부 공백
    const chips = screen.getAllByRole("button", { name: "즐겨찾기만 보기" }); // 지도 상단 + 목록 칩
    expect(chips).toHaveLength(2);
    await userEvent.click(chips[1]);
    expect(useSelection.getState().favoritesOnly).toBe(true);
    for (const c of screen.getAllByRole("button", { name: "즐겨찾기만 보기" })) expect(c).toHaveAttribute("aria-pressed", "true");
    const list = screen.getByRole("list", { name: "경고 목록" });
    const names = within(list).getAllByRole("listitem").map((r) => r.textContent);
    expect(names).toHaveLength(2);
    expect(names.join(" ")).toContain("사아자공장");
    expect(names.join(" ")).toContain("공백공장");
    expect(screen.getByText(/내 즐겨찾기/)).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "즐겨찾기만 보기" })[0]); // 지도 쪽 칩으로 끈다
    expect(useSelection.getState().favoritesOnly).toBe(false);
  });
});

describe("공지: 롤링 배너와 스티커(최신 데이터 기준)", () => {
  it("롤링 배너에는 지금 초과인 사업장만 오르고, 위험은 오르지 않는다", async () => {
    setup();
    const banner = await screen.findByRole("region", { name: "초과 공지" });
    expect(within(banner).getByRole("button", { name: /라마바공장/ })).toBeInTheDocument(); // 105% 초과
    expect(within(banner).queryByRole("button", { name: /가나다공장/ })).toBeNull(); // 95% 위험
  });

  it("배너를 누르면 그 사업장·굴뚝이 선택되고 차트가 열린다", async () => {
    setup();
    const banner = await screen.findByRole("region", { name: "초과 공지" });
    await userEvent.click(within(banner).getByRole("button", { name: /라마바공장/ }));
    expect(useSelection.getState().selectedSiteId).toBe("S2");
    expect(useSelection.getState().selectedStackCode).toBe("2"); // 초과인 굴뚝
  });

  it("스티커는 즐겨찾기한 사업장만(경고 이상) 보이고, 즐겨찾기가 없으면 없다", async () => {
    setup();
    await screen.findByRole("region", { name: "초과 공지" });
    expect(screen.queryByRole("region", { name: "내 즐겨찾기 알림" })).toBeNull();
    act(() => useSelection.setState({ favorites: ["S1", "S3"] })); // S1 위험, S3는 최신이 공백(직전 72%라 주의 → 공지 아님)
    const sticker = await screen.findByRole("region", { name: "내 즐겨찾기 알림" });
    expect(within(sticker).getByRole("button", { name: /가나다공장/ })).toBeInTheDocument();
    expect(within(sticker).queryByRole("button", { name: /사아자공장/ })).toBeNull();
  });

  it("스티커의 X로 닫으면 사라진다", async () => {
    setup();
    act(() => useSelection.setState({ favorites: ["S1"] }));
    await userEvent.click(await screen.findByRole("button", { name: "즐겨찾기 알림 닫기" }));
    expect(screen.queryByRole("region", { name: "내 즐겨찾기 알림" })).toBeNull();
  });

  it("지도 시각 슬라이더를 옛 시각으로 옮겨도 공지는 최신 데이터 기준이다", async () => {
    setup();
    const banner = await screen.findByRole("region", { name: "초과 공지" });
    expect(banner).toBeInTheDocument();
    // 지도 시각이 첫 칸으로 가도(앞 칸에도 같은 값이라 결과는 같지만) 공지는 마지막 칸으로 계산한다: 배너가 그대로 있다
    const slider = screen.getByRole("slider");
    fireEvent.change(slider, { target: { value: "0" } });
    expect(screen.getByRole("region", { name: "초과 공지" })).toBeInTheDocument();
  });
});

describe("톱니바퀴 → 그래프 설정", () => {
  it("레일의 톱니바퀴로 패널을 열고 닫고, 예시 사업장을 열면 그래프가 나온다", async () => {
    setup();
    await screen.findByRole("list", { name: "경고 목록" });
    expect(screen.queryByRole("dialog", { name: "그래프 설정" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "그래프 설정" }));
    expect(screen.getByRole("dialog", { name: "그래프 설정" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "추세 차트" })).toBeNull(); // 사업장을 아직 안 골랐다
    await userEvent.click(screen.getByRole("button", { name: "예시 사업장 열기" }));
    expect(useSelection.getState().selectedSiteId).toBe("S2"); // 지금 초과인 첫 사업장
    expect(await screen.findByRole("region", { name: "추세 차트" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "그래프 설정 닫기" }));
    expect(screen.queryByRole("dialog", { name: "그래프 설정" })).toBeNull();
  });
});

