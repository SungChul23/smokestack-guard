// 지도 종류 전환(관제 / 네이버 일반 / 네이버 위성) 시험. 실제 네이버 SDK는 부를 수 없어 가짜 SDK(src/test/fakeNaver.ts)를 쓴다.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SiteState } from "../../data/model";
import { initialSelection, MAP_SHOW_ORDER, useSelection } from "../../state/selection";
import { installFakeNaver } from "../../test/fakeNaver";
import { ThemeProvider } from "../../theme/theme";
import * as geometry from "../geometry";
import MapPanel from "../MapPanel";
import { NAVER_NOTES, NAVER_TIMEOUT_MS, resetNaverLoader } from "./loader";
import { MODE_KEY } from "./mode";

const times = Array.from({ length: 48 }, (_, i) => Date.UTC(2026, 10, 9, 15, 0) + i * 1800000);
const geoSeoul = [{
  name: "서울", type: "Polygon" as const,
  coordinates: [[[126.8, 37.4], [127.2, 37.4], [127.2, 37.7], [126.8, 37.7], [126.8, 37.4]]],
}];
const at = (id: string, lon: number, lat: number, level: SiteState["level"] = "risk", ratio = 95): SiteState => ({
  site: { id, name: `공장${id}`, sido: "서울", sigungu: "중구", address: "", lon, lat, stacks: [] }, ratio, level, worstStack: "1",
});
const scripts = () => [...document.head.querySelectorAll<HTMLScriptElement>('script[src*="oapi.map.naver.com"]')];

/** 아무 호출이나 받아 주는 가짜 그리기 도구(jsdom에는 캔버스 그리기가 없다) */
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

let fake: ReturnType<typeof installFakeNaver>;
const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 60)); });
const emit = (...a: Parameters<typeof fake.emit>) => act(() => { fake.emit(...a); });

function renderPanel(states: SiteState[] = [at("A", 127, 37.5)]) {
  return render(
    <ThemeProvider>
      <MapPanel states={states} geo={geoSeoul} times={times} slot={47} onSlot={() => {}} />
    </ThemeProvider>,
  );
}
const kind = (name: string) => within(screen.getByRole("group", { name: "지도 종류" })).getByRole("button", { name });
async function enter(name: "네이버 일반" | "네이버 위성") {
  await userEvent.click(kind(name));
  await waitFor(() => expect(fake.maps).toHaveLength(1));
  await waitFor(() => expect(kind(name)).toHaveAttribute("aria-pressed", "true"));
  await settle();
}
/** 가짜 지도를 (경도, 위도, 확대)로 옮기고 멈춤(idle)을 알린다 */
function park(lng: number, lat: number, zoom: number) {
  const m = fake.maps[0];
  m.center = new fake.LatLng(lat, lng);
  m.zoom = zoom;
  return emit(m, "idle");
}

beforeEach(() => {
  window.localStorage.clear();
  useSelection.setState({ ...initialSelection, mapLevels: [...MAP_SHOW_ORDER] });
  resetNaverLoader();
  Reflect.deleteProperty(window, "naver");
  for (const s of scripts()) s.remove();
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 800 });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => 500 });
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(fakeContext() as never);
  globalThis.fetch = vi.fn().mockRejectedValue(new Error("no network")) as unknown as typeof fetch;
  fake = installFakeNaver();
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  resetNaverLoader();
  Reflect.deleteProperty(window, "naver");
  for (const s of scripts()) s.remove();
  window.localStorage.clear();
});

describe("지도 종류 선택 막대", () => {
  it("기본은 관제 지도이고, 같은 윗줄 오른쪽 묶음 안에 있으며 SDK는 읽지 않는다", () => {
    Reflect.deleteProperty(window, "naver");
    renderPanel();
    const group = screen.getByRole("group", { name: "지도 종류" });
    const names = within(group).getAllByRole("button").map((b) => b.getAttribute("aria-label"));
    expect(names).toEqual(["관제 지도", "네이버 일반", "네이버 위성"]);
    expect(kind("관제 지도")).toHaveAttribute("aria-pressed", "true");
    expect(kind("네이버 일반")).toHaveAttribute("aria-pressed", "false");
    // 윗줄을 늘리지 않는다: 상태 칩과 같은 오른쪽 묶음
    expect(group.parentElement).toBe(screen.getByRole("group", { name: "지도에 표시할 상태" }).parentElement);
    expect(scripts()).toHaveLength(0); // 네이버를 고르기 전에는 SDK를 읽지 않는다
    expect(screen.getByRole("button", { name: /등고선/ })).toBeInTheDocument();
  });

  it("네이버 일반을 고르면 지도가 한 번 만들어지고 관제 지도의 땅·등고선 버튼은 숨는다", async () => {
    renderPanel();
    await enter("네이버 일반");
    expect(fake.maps).toHaveLength(1);
    expect(fake.maps[0].typeId).toBe("normal");
    expect(kind("관제 지도")).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByRole("button", { name: /등고선/ })).toBeNull();
    expect(screen.getByRole("button", { name: "전국 보기" })).toBeInTheDocument();
    expect(window.localStorage.getItem(MODE_KEY)).toBe("normal");
    expect(screen.queryByRole("status")).toBeNull(); // 불러오는 중 안내는 끝나면 사라진다
    expect(fake.maps[0].el.className).not.toMatch(/hostHidden/);
    // 핀을 얹은 캔버스는 지도 조작을 가로막지 않는다
    expect(screen.getByRole("img", { name: /굴뚝 .*곳을 보여 주는 지도/ }).className).toMatch(/overlay/);
  });

  it("일반 ↔ 위성은 지도를 다시 만들지 않고 종류만 바꾼다", async () => {
    renderPanel();
    await enter("네이버 일반");
    await userEvent.click(kind("네이버 위성"));
    expect(fake.maps).toHaveLength(1);
    expect(fake.maps[0].typeId).toBe("satellite");
    expect(kind("네이버 위성")).toHaveAttribute("aria-pressed", "true");
    expect(window.localStorage.getItem(MODE_KEY)).toBe("satellite");
    await userEvent.click(kind("네이버 일반"));
    expect(fake.maps[0].typeId).toBe("normal");
    expect(fake.maps).toHaveLength(1);
  });

  it("관제 지도로 돌아오면 네이버 지도를 없애고 등고선 버튼이 돌아오며 저장값을 지운다", async () => {
    renderPanel();
    await enter("네이버 일반");
    const map = fake.maps[0];
    await userEvent.click(kind("관제 지도"));
    expect(map.destroyed).toBe(true);
    expect(fake.liveListeners(map)).toBe(0);
    expect(kind("관제 지도")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /등고선/ })).toBeInTheDocument();
    expect(window.localStorage.getItem(MODE_KEY)).toBeNull();
    expect(screen.getByRole("img", { name: /굴뚝 .*곳을 보여 주는 지도/ }).className).not.toMatch(/overlay/);
  });

  it("선택·시각·상태 칩은 지도를 바꿔도 그대로다", async () => {
    renderPanel();
    act(() => useSelection.getState().selectSite("A", "1"));
    await userEvent.click(within(screen.getByRole("group", { name: "지도에 표시할 상태" })).getByRole("button", { name: /초과/ }));
    const levels = [...useSelection.getState().mapLevels];
    await enter("네이버 위성");
    expect(useSelection.getState().selectedSiteId).toBe("A");
    expect(useSelection.getState().mapLevels).toEqual(levels);
    expect(screen.getByLabelText("지도 시각")).toHaveValue("47");
    await userEvent.click(kind("관제 지도"));
    expect(useSelection.getState().selectedSiteId).toBe("A");
    expect(useSelection.getState().mapLevels).toEqual(levels);
  });
});

describe("실패하면 관제 지도를 계속 쓴다", () => {
  it("읽는 중에는 안내하고 버튼을 잠그며, 스크립트 오류면 이유를 알리고 다시 시도할 수 있다", async () => {
    Reflect.deleteProperty(window, "naver");
    renderPanel();
    await userEvent.click(kind("네이버 일반"));
    expect(scripts()).toHaveLength(1);
    expect(screen.getByRole("status")).toHaveTextContent(NAVER_NOTES.loading);
    expect(kind("네이버 위성")).toBeDisabled();
    act(() => { scripts()[0].onerror?.(new Event("error")); });
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(NAVER_NOTES.script));
    expect(kind("관제 지도")).toHaveAttribute("aria-pressed", "true");
    expect(kind("네이버 일반")).toBeEnabled();
    expect(window.localStorage.getItem(MODE_KEY)).toBeNull();
    // 다시 시도 → 이번에는 성공
    await userEvent.click(kind("네이버 일반"));
    expect(scripts()).toHaveLength(1);
    const again = installFakeNaver();
    act(() => { scripts()[0].onload?.(new Event("load")); });
    await waitFor(() => expect(again.maps).toHaveLength(1));
    await waitFor(() => expect(kind("네이버 일반")).toHaveAttribute("aria-pressed", "true"));
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("시간 초과면 안내하고 관제 지도에 머문다", async () => {
    Reflect.deleteProperty(window, "naver");
    renderPanel();
    vi.useFakeTimers();
    fireEvent.click(kind("네이버 위성"));
    await act(async () => { await vi.advanceTimersByTimeAsync(NAVER_TIMEOUT_MS + 10); });
    expect(screen.getByRole("status")).toHaveTextContent(NAVER_NOTES.timeout);
    expect(kind("관제 지도")).toHaveAttribute("aria-pressed", "true");
  });

  it("읽는 도중 인증 실패면 인증 안내(허용된 도메인)를 보이고 관제 지도에 머문다", async () => {
    Reflect.deleteProperty(window, "naver");
    renderPanel();
    await userEvent.click(kind("네이버 일반"));
    act(() => { window.navermap_authFailure?.(); });
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("허용된 도메인"));
    expect(kind("관제 지도")).toHaveAttribute("aria-pressed", "true");
  });

  it("지도를 쓰던 중 인증 실패가 오면 관제 지도로 돌아가고 이유를 알린다", async () => {
    renderPanel();
    await enter("네이버 일반");
    const map = fake.maps[0];
    act(() => { window.navermap_authFailure?.(); });
    expect(map.destroyed).toBe(true);
    expect(kind("관제 지도")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("status")).toHaveTextContent("허용된 도메인");
    expect(screen.getByRole("button", { name: /등고선/ })).toBeInTheDocument();
    // 같은 화면에서는 다시 골라도 소용없으니 지도를 만들지 않는다
    await userEvent.click(kind("네이버 위성"));
    await settle();
    expect(fake.maps).toHaveLength(1);
    expect(kind("관제 지도")).toHaveAttribute("aria-pressed", "true");
  });
});

describe("저장·복원·정리", () => {
  it("저장해 둔 지도 종류로 시작한다", async () => {
    window.localStorage.setItem(MODE_KEY, "satellite");
    renderPanel();
    await waitFor(() => expect(fake.maps).toHaveLength(1));
    await waitFor(() => expect(kind("네이버 위성")).toHaveAttribute("aria-pressed", "true"));
    expect(fake.maps[0].typeId).toBe("satellite");
  });

  it("저장소를 못 써도 선택은 동작한다", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    renderPanel();
    await enter("네이버 일반");
    expect(kind("네이버 일반")).toHaveAttribute("aria-pressed", "true");
  });

  it("화면이 사라지면 지도와 이벤트 연결을 모두 정리한다", async () => {
    const { unmount } = renderPanel();
    await enter("네이버 일반");
    const map = fake.maps[0];
    expect(fake.liveListeners(map)).toBeGreaterThan(0);
    unmount();
    expect(map.destroyed).toBe(true);
    expect(fake.liveListeners()).toBe(0);
  });

  it("읽는 도중 화면이 사라지면 나중에 읽혀도 지도를 만들지 않는다", async () => {
    Reflect.deleteProperty(window, "naver");
    const { unmount } = renderPanel();
    await userEvent.click(kind("네이버 일반"));
    unmount();
    const late = installFakeNaver();
    act(() => { scripts()[0]?.onload?.(new Event("load")); });
    await settle();
    expect(late.maps).toHaveLength(0);
  });
});

describe("지도 보기 연결(범위·선택·전국 보기)", () => {
  it("멈추면(idle) 네이버가 보여 주는 범위를 목록에 알린다", async () => {
    renderPanel();
    await enter("네이버 일반");
    await park(127.5, 36.5, 12);
    const b = useSelection.getState().mapBounds!;
    expect(b.maxX - b.minX).toBeCloseTo(800 / 2 ** 12, 6);
    expect(b.maxY - b.minY).toBeCloseTo(500 / 2 ** 12, 6);
    const [cx, cy] = geometry.project(127.5, 36.5);
    expect((b.minX + b.maxX) / 2).toBeCloseTo(cx, 6);
    expect((b.minY + b.maxY) / 2).toBeCloseTo(cy, 6);
    await park(129, 35, 9);
    const b2 = useSelection.getState().mapBounds!;
    expect(b2.maxX - b2.minX).toBeCloseTo(800 / 2 ** 9, 6);
  });

  it("움직이는 동안에는 범위를 갱신하지 않고 멈추면 갱신한다", async () => {
    renderPanel();
    await enter("네이버 일반");
    await park(127.5, 36.5, 12);
    const before = useSelection.getState().mapBounds;
    fake.maps[0].zoom = 13;
    await emit(fake.maps[0], "zoom_changed");
    expect(useSelection.getState().mapBounds).toBe(before);
    await emit(fake.maps[0], "idle");
    expect(useSelection.getState().mapBounds).not.toBe(before);
  });

  it("사업장을 고르면 네이버 지도가 그리로 부드럽게 들어간다(확대 15)", async () => {
    renderPanel([at("A", 127, 37.5), at("B", 127.0001, 37.5001)]);
    await enter("네이버 일반");
    await park(127.7, 36, 8);
    act(() => useSelection.getState().selectSite("A", "1"));
    expect(fake.maps[0].morphs).toHaveLength(1);
    expect(fake.maps[0].morphs[0]).toMatchObject({ lng: 127, lat: 37.5, zoom: 15 });
    // 이미 확대 15이고 화면 안이면 다른 사업장을 골라도 움직이지 않는다
    await emit(fake.maps[0], "idle");
    act(() => useSelection.getState().selectSite("B", "1"));
    expect(fake.maps[0].morphs).toHaveLength(1);
  });

  it("확대 15 이상이어도 화면 밖의 사업장을 고르면 이동한다(현재 확대는 유지)", async () => {
    renderPanel([at("A", 127, 37.5), at("C", 128.5, 35.5)]);
    await enter("네이버 일반");
    await park(127, 37.5, 17);
    act(() => useSelection.getState().selectSite("C", "1"));
    expect(fake.maps[0].morphs).toHaveLength(1);
    expect(fake.maps[0].morphs[0]).toMatchObject({ lng: 128.5, lat: 35.5, zoom: 17 });
  });

  it("전국 보기는 네이버 확대(정수)로 내림해 다 보이게 간다", async () => {
    renderPanel();
    await enter("네이버 일반");
    await park(127.7, 36, 15);
    const b = geometry.boundsOf(geoSeoul[0].coordinates[0].map(([x, y]) => geometry.project(x, y)))!;
    const scale = geometry.fitView(b, 800, 500, 28).scale;
    const want = Math.min(18, Math.max(6, Math.floor(Math.log2(scale) + 1e-9)));
    await userEvent.click(screen.getByRole("button", { name: "전국 보기" }));
    const morphs = fake.maps[0].morphs;
    const last = morphs[morphs.length - 1];
    expect(last.zoom).toBe(want);
    expect(Number.isInteger(last.zoom)).toBe(true);
  });
});

describe("핀 조작(관제 지도와 같은 동작)", () => {
  it("네이버 지도 위의 핀을 누르면 선택되고, 다시 누르면 해제된다", async () => {
    renderPanel();
    await enter("네이버 일반");
    await park(127, 37.5, 12);
    await settle(); // 새 보기로 묶음을 다시 계산
    const p = fake.screenOf(fake.maps[0], 127, 37.5);
    await emit(fake.maps[0], "click", { point: { x: p.x, y: p.y - 2 } });
    expect(useSelection.getState().selectedSiteId).toBe("A");
    await act(async () => { await new Promise((r) => setTimeout(r, 400)); }); // 더블클릭 판정 시간이 지난 뒤
    await emit(fake.maps[0], "click", { point: { x: p.x, y: p.y - 2 } });
    expect(useSelection.getState().selectedSiteId).toBeNull();
  });

  it("핀이 없는 곳을 눌러도 아무 일도 없다", async () => {
    renderPanel();
    await enter("네이버 일반");
    await park(127, 37.5, 12);
    await settle();
    await emit(fake.maps[0], "click", { point: { x: 20, y: 20 } });
    expect(useSelection.getState().selectedSiteId).toBeNull();
  });

  it("핀 위에 마우스를 올리면 말풍선이 뜨고, 벗어나면 사라진다", async () => {
    renderPanel();
    await enter("네이버 일반");
    await park(127, 37.5, 12);
    await settle();
    const p = fake.screenOf(fake.maps[0], 127, 37.5);
    await emit(fake.maps[0], "mousemove", { point: { x: p.x, y: p.y - 2 } });
    expect(await screen.findByText(/공장A · 95%/)).toBeInTheDocument();
    act(() => { fake.maps[0].el.dispatchEvent(new MouseEvent("mouseleave")); });
    expect(screen.queryByText(/공장A · 95%/)).toBeNull();
  });

  it("오른쪽 클릭하면 선택이 해제되고 브라우저 메뉴는 뜨지 않는다", async () => {
    renderPanel();
    await enter("네이버 일반");
    act(() => useSelection.getState().selectSite("A", "1"));
    const e = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });
    act(() => { fake.maps[0].el.dispatchEvent(e); });
    expect(e.defaultPrevented).toBe(true);
    expect(useSelection.getState().selectedSiteId).toBeNull();
  });

  it("묶음을 누르면 네이버가 더 확대해 들어가고, 좌표가 같은 묶음은 고르기 목록이 뜬다", async () => {
    renderPanel([at("A", 127.0, 37.5), at("B", 127.01, 37.5)]);
    await enter("네이버 일반");
    await park(127.005, 37.5, 8);
    await settle();
    const a = fake.screenOf(fake.maps[0], 127.0, 37.5), b = fake.screenOf(fake.maps[0], 127.01, 37.5);
    await emit(fake.maps[0], "click", { point: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 2 } });
    expect(fake.maps[0].morphs).toHaveLength(1);
    expect(fake.maps[0].morphs[0].zoom).toBeGreaterThanOrEqual(9);
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("좌표가 같은 사업장 묶음을 누르면 고르기 목록이 뜬다", async () => {
    renderPanel([at("A", 127.0, 37.5, "risk"), at("B", 127.0, 37.5, "exceed", 120)]);
    await enter("네이버 일반");
    await park(127, 37.5, 12);
    await settle();
    const p = fake.screenOf(fake.maps[0], 127, 37.5);
    await emit(fake.maps[0], "click", { point: { x: p.x, y: p.y - 2 } });
    const menu = await screen.findByRole("menu", { name: /같은 자리의 사업장 2곳/ });
    expect(within(menu).getAllByRole("menuitem")[0]).toHaveTextContent("공장B");
    expect(fake.maps[0].morphs).toHaveLength(0);
  });
});
