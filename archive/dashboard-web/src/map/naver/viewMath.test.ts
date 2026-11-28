import { describe, expect, it } from "vitest";
import { centerOf, centeredOn, project, toScreen } from "../geometry";
import {
  NAVER_BOUNDS, NAVER_ZOOM, clampZoom, focusTarget, needsNaverFocus, targetOfView, unproject, viewFromProjection, zoomForScale,
} from "./viewMath";

describe("네이버 ↔ 우리 좌표(웹 메르카토르)", () => {
  it("옛 지도 어댑터와 같은 한도: 확대 6~18, 사업장 포커스 15, 한국 범위", () => {
    expect(NAVER_ZOOM).toEqual({ min: 7, max: 18, focus: 15 });
    expect(NAVER_BOUNDS).toEqual({ sw: { lat: 31.5, lng: 123 }, ne: { lat: 40, lng: 133 } });
  });

  it("세계 좌표 ↔ 경위도가 왕복해도 같다(서울·부산·제주)", () => {
    for (const [lng, lat] of [[126.98, 37.57], [129.07, 35.18], [126.53, 33.5]]) {
      const [x, y] = project(lng, lat);
      const [lng2, lat2] = unproject(x, y);
      expect(lng2).toBeCloseTo(lng, 9);
      expect(lat2).toBeCloseTo(lat, 9);
    }
  });

  it("확대 수준은 정수로 환산하고 한도(6~18) 안으로 자른다", () => {
    expect(zoomForScale(2 ** 10)).toBe(10);
    expect(zoomForScale(2 ** 10.4)).toBe(10);
    expect(zoomForScale(2 ** 10.6)).toBe(11);
    expect(zoomForScale(1)).toBe(7); // 너무 줄인 배율도 한도(7)까지만
    expect(zoomForScale(1e12)).toBe(18);
    expect(clampZoom(3)).toBe(7);
    expect(clampZoom(40)).toBe(18);
  });

  it("전국 맞춤은 내림(다 보이게), 묶음 확대는 올림(확실히 더 들어가게)", () => {
    expect(zoomForScale(2 ** 7.4, "floor")).toBe(7);
    expect(zoomForScale(2 ** 7.4, "ceil")).toBe(8);
    expect(zoomForScale(2 ** 8, "ceil")).toBe(8); // 정확히 정수면 그대로
    expect(zoomForScale(2 ** 8, "floor")).toBe(8);
  });

  it("우리 보기 → 네이버가 갈 곳: 화면 중앙의 경위도와 확대 수준", () => {
    const [x, y] = project(127, 37.5);
    const view = centeredOn(x, y, 2 ** 11, 800, 500);
    const t = targetOfView(view, 800, 500);
    expect(t.lng).toBeCloseTo(127, 9);
    expect(t.lat).toBeCloseTo(37.5, 9);
    expect(t.zoom).toBe(11);
  });

  it("네이버 투영에서 보정한 보기는 우리 계산과 같다(같은 웹 메르카토르일 때)", () => {
    const zoom = 11, w = 800, h = 500;
    const center = project(127, 37.5);
    const scale = 2 ** zoom;
    // 가짜 네이버 투영: 세계 폭 256×2^줌, 화면 중앙이 지도 중심
    const toScr = (lng: number, lat: number) => {
      const [x, y] = project(lng, lat);
      return { x: (x - center[0]) * scale + w / 2, y: (y - center[1]) * scale + h / 2 };
    };
    const v = viewFromProjection(toScr);
    const expected = centeredOn(center[0], center[1], scale, w, h);
    expect(v.scale).toBeCloseTo(expected.scale, 6);
    expect(v.ox).toBeCloseTo(expected.ox, 3);
    expect(v.oy).toBeCloseTo(expected.oy, 3);
    expect(centerOf(v, w, h)[0]).toBeCloseTo(center[0], 9);
  });

  it("타일 기준이 다른 SDK(세계 폭 512)여도 핀이 어긋나지 않는다(투영에서 보정하므로)", () => {
    const w = 700, h = 400;
    const center = project(128, 36);
    const base = 512, zoom = 9;
    const k = base * 2 ** zoom / 256; // 우리 세계 1칸이 몇 px인가
    const toScr = (lng: number, lat: number) => {
      const [x, y] = project(lng, lat);
      return { x: (x - center[0]) * k + w / 2, y: (y - center[1]) * k + h / 2 };
    };
    const v = viewFromProjection(toScr);
    expect(v.scale).toBeCloseTo(k, 6); // 줌 수식(2^9)이 아니라 실제 투영의 축척
    // 이 보기로 계산한 임의 사업장의 화면 위치가 SDK가 알려 주는 위치와 같다
    for (const [lng, lat] of [[126.98, 37.57], [129.07, 35.18], [126.53, 33.5]]) {
      const [x, y] = project(lng, lat);
      const mine = toScreen(v, x, y);
      const theirs = toScr(lng, lat);
      expect(mine[0]).toBeCloseTo(theirs.x, 3);
      expect(mine[1]).toBeCloseTo(theirs.y, 3);
    }
  });

  it("확대 도중(소수 줌)에도 보정이 맞는다", () => {
    const w = 600, h = 400, center = project(127.5, 36.5), scale = 2 ** 9.37;
    const toScr = (lng: number, lat: number) => {
      const [x, y] = project(lng, lat);
      return { x: (x - center[0]) * scale + w / 2, y: (y - center[1]) * scale + h / 2 };
    };
    expect(viewFromProjection(toScr).scale).toBeCloseTo(scale, 6);
  });
});

describe("사업장 포커스(옛 규칙: 확대 15)", () => {
  it("낮은 확대에서 고르면 15까지 들어가고, 이미 더 깊으면 그대로", () => {
    expect(focusTarget(127, 37.5, 9).zoom).toBe(15);
    expect(focusTarget(127, 37.5, 15).zoom).toBe(15);
    expect(focusTarget(127, 37.5, 17).zoom).toBe(17);
    expect(focusTarget(127, 37.5, 25).zoom).toBe(18); // 한도
    expect(focusTarget(127.1, 37.6, 9)).toMatchObject({ lng: 127.1, lat: 37.6 });
  });

  it("15 미만이면 움직이고, 15 이상이면 화면 여백 안에서는 움직이지 않는다", () => {
    expect(needsNaverFocus(14, 400, 300, 800, 500)).toBe(true);
    expect(needsNaverFocus(15, 400, 250, 800, 500)).toBe(false);
    expect(needsNaverFocus(16, 20, 250, 800, 500)).toBe(true); // 왼쪽 가장자리
    expect(needsNaverFocus(16, 400, 20, 800, 500)).toBe(true); // 위쪽
    expect(needsNaverFocus(16, 400, 480, 800, 500)).toBe(true); // 아래쪽
    expect(needsNaverFocus(16, 780, 250, 800, 500)).toBe(true); // 오른쪽
  });
});
