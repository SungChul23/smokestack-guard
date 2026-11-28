import { describe, expect, it } from "vitest";
import { centeredOn } from "./geometry";
import { regionAtCenter, type RegionPoly, type SitePos } from "./regionAtCenter";

const W = 800, H = 500;
// 월드 좌표의 네모 두 개: 서울(0~10), 경기(10~20)
const sq = (x0: number, x1: number): Array<[number, number]> => [[x0, 0], [x1, 0], [x1, 10], [x0, 10], [x0, 0]];
const regions: RegionPoly[] = [{ name: "서울", polys: [[sq(0, 10)]] }, { name: "경기", polys: [[sq(10, 20)]] }];
const site = (sido: string, sigungu: string, x: number, y: number): SitePos => ({ sido, sigungu, x, y });
const sites = [site("서울", "중구", 4, 5), site("서울", "종로구", 7, 5), site("경기", "수원시", 15, 5)];

describe("지도 중앙으로 지역 판단", () => {
  it("넓게 볼 때(광역)는 지역을 특정하지 않는다", () => {
    expect(regionAtCenter(centeredOn(5, 5, 100, W, H), W, H, regions, sites)).toEqual({ sido: null, sigungu: null });
  });
  it("간략 등급(180~450)에서는 시도까지만 판단한다", () => {
    expect(regionAtCenter(centeredOn(5, 5, 300, W, H), W, H, regions, sites)).toEqual({ sido: "서울", sigungu: null });
    expect(regionAtCenter(centeredOn(15, 5, 300, W, H), W, H, regions, sites)).toEqual({ sido: "경기", sigungu: null });
  });
  it("상세 등급(450 이상)에서는 중앙에 가장 가까운 사업장의 시군까지 판단한다", () => {
    expect(regionAtCenter(centeredOn(4.1, 5, 800, W, H), W, H, regions, sites)).toEqual({ sido: "서울", sigungu: "중구" });
    expect(regionAtCenter(centeredOn(6.9, 5, 800, W, H), W, H, regions, sites)).toEqual({ sido: "서울", sigungu: "종로구" });
  });
  it("중앙에서 너무 먼 곳의 시군은 짐작하지 않는다", () => {
    // 서울 안이지만 가장 가까운 사업장이 120px보다 멀다(800배율에서 월드 0.15 이상)
    expect(regionAtCenter(centeredOn(1, 9, 800, W, H), W, H, regions, sites)).toEqual({ sido: "서울", sigungu: null });
  });
  it("바다에서 사업장이 150px 안이면 그 시도로, 밖이면 비운다", () => {
    const inside = regionAtCenter(centeredOn(20.3, 5, 300, W, H), W, H, regions, [site("경기", "수원시", 20, 5)]); // 90px
    expect(inside.sido).toBe("경기");
    const outside = regionAtCenter(centeredOn(25, 5, 300, W, H), W, H, regions, [site("경기", "수원시", 20, 5)]); // 1500px
    expect(outside).toEqual({ sido: null, sigungu: null });
  });
  it("사업장이 없어도 경계 안이면 시도는 판단한다", () => {
    expect(regionAtCenter(centeredOn(5, 5, 300, W, H), W, H, regions, [])).toEqual({ sido: "서울", sigungu: null });
  });
});
