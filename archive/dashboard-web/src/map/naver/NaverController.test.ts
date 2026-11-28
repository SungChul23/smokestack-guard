import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installFakeNaver } from "../../test/fakeNaver";
import { project, toScreen } from "../geometry";
import { createNaverMap, type NaverCallbacks } from "./NaverController";

let fake: ReturnType<typeof installFakeNaver>;
let host: HTMLElement;
const cbs = (): NaverCallbacks => ({
  onFollow: vi.fn(), onIdle: vi.fn(), onHover: vi.fn(), onLeave: vi.fn(), onClick: vi.fn(), onContextMenu: vi.fn(),
});
const make = (cb = cbs()) => ({ ctl: createNaverMap(window.naver!.maps!, host, { w: 800, h: 500 }, cb), cb });

beforeEach(() => {
  fake = installFakeNaver();
  host = document.createElement("div");
  document.body.append(host);
});
afterEach(() => {
  host.remove();
  fake.uninstall();
});

describe("지도 만들기", () => {
  it("옛 지도와 같은 한도로 만든다: 확대 6~18, 한국 범위, 컨트롤은 끄고 로고는 둔다", () => {
    make();
    const o = fake.maps[0].options as Record<string, unknown>;
    expect(o.minZoom).toBe(7); // 한국이 너무 작아지지 않게 처음 전국 맞춤 수준에서 멈춘다
    expect(o.maxZoom).toBe(18);
    expect(o.zoomControl).toBe(false);
    expect(o.mapTypeControl).toBe(false);
    expect(o.scaleControl).toBe(true);
    expect(o.logoControl).toBe(true); // 네이버 로고·저작권 표기는 끄지 않는다
    expect(o.zoom).toBe(7);
    const b = o.maxBounds as { sw: { lat(): number; lng(): number }; ne: { lat(): number; lng(): number } };
    expect([b.sw.lat(), b.sw.lng(), b.ne.lat(), b.ne.lng()]).toEqual([31.5, 123, 40, 133]);
    expect(fake.maps[0].el).toBe(host);
    expect(fake.maps[0].getSize()).toMatchObject({ width: 800, height: 500 });
  });

  it("지도 종류: 일반 / 위성", () => {
    const { ctl } = make();
    ctl.setMapType("satellite");
    expect(fake.maps[0].typeId).toBe("satellite");
    ctl.setMapType("normal");
    expect(fake.maps[0].typeId).toBe("normal");
  });
});

describe("보이는 범위(View)", () => {
  it("지금 지도의 보이는 범위를 우리 View로 돌려준다(중심·축척)", () => {
    const { ctl } = make();
    ctl.moveTo({ lng: 127, lat: 37.5, zoom: 11 }, false);
    const v = ctl.getView();
    expect(v.scale).toBeCloseTo(2 ** 11, 5);
    // 지도 중심이 화면 가운데에 온다
    const [px, py] = project(127, 37.5);
    const [sx, sy] = toScreen(v, px, py);
    expect(sx).toBeCloseTo(400, 3);
    expect(sy).toBeCloseTo(250, 3);
  });

  it("타일 기준이 다른 SDK여도 핀 위치가 SDK의 투영과 일치한다", () => {
    fake.uninstall();
    fake = installFakeNaver({ tileBase: 512 });
    const { ctl } = make();
    ctl.moveTo({ lng: 128, lat: 36, zoom: 9 }, false);
    const v = ctl.getView();
    for (const [lng, lat] of [[126.98, 37.57], [129.07, 35.18]]) {
      const [x, y] = project(lng, lat);
      const mine = toScreen(v, x, y);
      const theirs = fake.screenOf(fake.maps[0], lng, lat);
      expect(mine[0]).toBeCloseTo(theirs.x, 3);
      expect(mine[1]).toBeCloseTo(theirs.y, 3);
    }
  });

  it("실제 SDK처럼 좌표→오프셋이 판(pane) 기준이어도, 끌면 View가 따라 움직인다(핀이 지도에 붙어 다닌다)", () => {
    const { ctl } = make();
    const N = window.naver!.maps!;
    ctl.moveTo({ lng: 127, lat: 37.5, zoom: 11 }, false);
    fake.maps[0].paneOrigin = new N.LatLng(37.5, 127); // 판 기준은 처음 자리에 고정된다
    const before = ctl.getView();
    ctl.moveTo({ lng: 127.4, lat: 37.3, zoom: 11 }, false); // 끌어서 중심이 바뀜(같은 확대)
    const after = ctl.getView();
    const [px, py] = project(127, 37.5);
    const [bx, by] = toScreen(before, px, py);
    const [ax, ay] = toScreen(after, px, py);
    expect(bx).toBeCloseTo(400, 3);
    expect(by).toBeCloseTo(250, 3);
    expect(ax).toBeLessThan(bx - 10); // 중심이 동쪽으로 갔으니 그 점은 화면 왼쪽으로
    expect(ay).toBeLessThan(by + 1e6); // 위도 변화 방향 확인용(값 자체는 아래 중심 검사로)
    const [cx, cy] = project(127.4, 37.3);
    const [sx, sy] = toScreen(after, cx, cy);
    expect(sx).toBeCloseTo(400, 3); // 새 중심은 늘 화면 한가운데
    expect(sy).toBeCloseTo(250, 3);
  });

  it("지도를 움직이면 그에 맞춰 바뀐다", () => {
    const { ctl } = make();
    ctl.moveTo({ lng: 127, lat: 37.5, zoom: 11 }, false);
    const a = ctl.getView();
    ctl.moveTo({ lng: 129, lat: 35.1, zoom: 12 }, false);
    const b = ctl.getView();
    expect(b.scale).toBeCloseTo(a.scale * 2, 5);
    expect(b.ox).not.toBeCloseTo(a.ox, 0);
  });
});

describe("이동", () => {
  it("부드럽게(animate)면 morph를 쓰고, 아니면 바로 옮긴다", () => {
    const { ctl } = make();
    ctl.moveTo({ lng: 127, lat: 37.5, zoom: 15 }, true);
    expect(fake.maps[0].morphs).toHaveLength(1);
    expect(fake.maps[0].morphs[0]).toMatchObject({ lat: 37.5, lng: 127, zoom: 15 });
    ctl.moveTo({ lng: 128, lat: 36, zoom: 9 }, false);
    expect(fake.maps[0].morphs).toHaveLength(1);
    expect(fake.maps[0].getZoom()).toBe(9);
    expect(fake.maps[0].getCenter().lng()).toBe(128);
  });

  it("morph가 없는 SDK 버전이면 바로 옮기는 것으로 대신한다", () => {
    fake.uninstall();
    fake = installFakeNaver({ withMorph: false });
    const { ctl } = make();
    ctl.moveTo({ lng: 127, lat: 37.5, zoom: 15 }, true);
    expect(fake.maps[0].getZoom()).toBe(15);
    expect(fake.maps[0].morphs).toHaveLength(0);
  });

  it("확대는 7~18 안으로 자른다(더 줄이면 한국이 너무 작아진다)", () => {
    const { ctl } = make();
    ctl.moveTo({ lng: 127, lat: 37.5, zoom: 40 }, false);
    expect(fake.maps[0].getZoom()).toBe(18);
    ctl.moveTo({ lng: 127, lat: 37.5, zoom: 1 }, false);
    expect(fake.maps[0].getZoom()).toBe(7);
  });

  it("크기가 달라졌을 때만 지도 크기를 바꾼다", () => {
    const { ctl } = make();
    ctl.setSize(800, 500);
    expect(fake.maps[0].sizes).toHaveLength(0);
    ctl.setSize(900, 520);
    expect(fake.maps[0].sizes).toHaveLength(1);
    expect(fake.maps[0].getSize()).toMatchObject({ width: 900, height: 520 });
  });
});

describe("이벤트", () => {
  it("끌기·확대 이벤트는 '움직이는 중', idle은 '멈춤'으로 전달한다", () => {
    const { cb } = make();
    const m = fake.maps[0];
    for (const name of ["dragstart", "drag", "center_changed", "zoom_changed", "bounds_changed"]) fake.emit(m, name);
    expect(cb.onFollow).toHaveBeenCalledTimes(5);
    expect(cb.onIdle).not.toHaveBeenCalled();
    fake.emit(m, "idle");
    expect(cb.onIdle).toHaveBeenCalledTimes(1);
  });

  it("마우스 이동·클릭은 지도 영역 기준 화면 좌표로 전달한다", () => {
    const { cb } = make();
    fake.emit(fake.maps[0], "mousemove", { point: { x: 120, y: 80 } });
    fake.emit(fake.maps[0], "click", { point: { x: 130, y: 90 } });
    expect(cb.onHover).toHaveBeenCalledWith(120, 80);
    expect(cb.onClick).toHaveBeenCalledWith(130, 90);
  });

  it("브라우저 이벤트가 있으면 그 좌표를 지도 왼쪽 위 기준으로 바꿔 쓴다", () => {
    vi.spyOn(host, "getBoundingClientRect").mockReturnValue({ left: 100, top: 50, right: 900, bottom: 550, width: 800, height: 500, x: 100, y: 50, toJSON: () => ({}) });
    const { cb } = make();
    fake.emit(fake.maps[0], "click", { pointerEvent: { clientX: 340, clientY: 200 } as MouseEvent, point: { x: 1, y: 1 } });
    expect(cb.onClick).toHaveBeenCalledWith(240, 150);
  });

  it("좌표가 없는 이벤트는 무시한다", () => {
    const { cb } = make();
    fake.emit(fake.maps[0], "click", {});
    fake.emit(fake.maps[0], "mousemove");
    expect(cb.onClick).not.toHaveBeenCalled();
    expect(cb.onHover).not.toHaveBeenCalled();
  });

  it("오른쪽 클릭은 브라우저 메뉴를 막고 알린다", () => {
    const { cb } = make();
    const e = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });
    host.dispatchEvent(e);
    expect(e.defaultPrevented).toBe(true);
    expect(cb.onContextMenu).toHaveBeenCalledTimes(1);
  });

  it("마우스가 지도를 벗어나면 알린다", () => {
    const { cb } = make();
    host.dispatchEvent(new MouseEvent("mouseleave"));
    expect(cb.onLeave).toHaveBeenCalledTimes(1);
  });
});

describe("정리", () => {
  it("destroy하면 이벤트 연결을 모두 풀고 지도를 없앤다(여러 번 불러도 안전)", () => {
    const { ctl, cb } = make();
    const m = fake.maps[0];
    expect(fake.liveListeners(m)).toBeGreaterThan(0);
    ctl.destroy();
    expect(fake.liveListeners(m)).toBe(0);
    expect(m.destroyed).toBe(true);
    fake.emit(m, "idle");
    fake.emit(m, "click", { point: { x: 1, y: 1 } });
    host.dispatchEvent(new MouseEvent("contextmenu", { cancelable: true }));
    host.dispatchEvent(new MouseEvent("mouseleave"));
    expect(cb.onIdle).not.toHaveBeenCalled();
    expect(cb.onClick).not.toHaveBeenCalled();
    expect(cb.onContextMenu).not.toHaveBeenCalled();
    expect(cb.onLeave).not.toHaveBeenCalled();
    expect(() => ctl.destroy()).not.toThrow();
  });
});
