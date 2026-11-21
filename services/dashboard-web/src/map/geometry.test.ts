import { describe, expect, it } from "vitest";
import {
  boundsOf, carryClusters, clusterGrid, clusterRadius, clusterRadiusMerge, fitView, nearestCluster, pointInRings, project, rankOf,
  stageOf, toScreen, zoomAt, zoomGrade, GRADE_SCALES, WORLD,
  centerOf, centeredOn, easeOutCubic, interpolateView, needsFocus, beamHeight, pinBox, pinHit, FOCUS_SCALE, stepZoomView, flightDuration, canSeparate, MAX_SCALE, MIN_SEPARATION_PX, clampView, minScaleFor,
} from "./geometry";

describe("보기 맞추기", () => {
  it("경계 상자가 화면 안에 여백을 두고 들어온다", () => {
    const b = { minX: 0, minY: 0, maxX: 10, maxY: 5 };
    const v = fitView(b, 200, 100, 10);
    const [x0, y0] = toScreen(v, b.minX, b.minY);
    const [x1, y1] = toScreen(v, b.maxX, b.maxY);
    expect(x0).toBeGreaterThanOrEqual(10 - 1e-6);
    expect(y0).toBeGreaterThanOrEqual(10 - 1e-6);
    expect(x1).toBeLessThanOrEqual(190 + 1e-6);
    expect(y1).toBeLessThanOrEqual(90 + 1e-6);
  });
  it("점이 하나뿐이어도 무한대가 되지 않는다", () => {
    const v = fitView({ minX: 5, minY: 5, maxX: 5, maxY: 5 }, 200, 100);
    expect(Number.isFinite(v.scale)).toBe(true);
  });
  it("확대는 가리킨 점을 고정하고 범위를 넘지 않는다", () => {
    const v = { scale: 10, ox: 0, oy: 0 };
    const z = zoomAt(v, 50, 50, 2, 1, 100);
    expect(z.scale).toBe(20);
    expect(50 * z.scale / v.scale * 0 + (50 - z.ox) / z.scale).toBeCloseTo((50 - v.ox) / v.scale);
    expect(zoomAt(v, 0, 0, 1000, 1, 100).scale).toBe(100);
    expect(zoomAt(v, 0, 0, 0.0001, 1, 100).scale).toBe(1);
  });
  it("투영은 북쪽이 위(작은 y)다", () => {
    expect(project(127, 38)[1]).toBeLessThan(project(127, 35)[1]);
  });
  it("투영은 옛 지도와 같은 웹 메르카토르(세계 폭 256)다", () => {
    const [x, y] = project(126.98, 37.57); // 서울: 옛 등고선 개요 파일 좌표(약 218~219, 98~99) 안
    expect(x).toBeCloseTo(218.3, 1);
    expect(y).toBeCloseTo(99.13, 1);
    expect(project(-180, 0)[0]).toBe(0);
    expect(project(180, 0)[0]).toBeCloseTo(WORLD);
    expect(project(0, 0)[1]).toBeCloseTo(WORLD / 2);
  });
  it("지도 단계와 묶기 반경은 옛 지도와 같다", () => {
    expect(stageOf(179)).toBe("national");
    expect(stageOf(180)).toBe("region");
    expect(stageOf(699)).toBe("region");
    expect(stageOf(700)).toBe("site");
  });
  it("확대 등급은 4단계이고 경계값에서 한 단계씩 올라간다", () => {
    expect(GRADE_SCALES).toEqual([180, 450, 1400]);
    expect([100, 179.9, 180, 449, 450, 1399, 1400, 4096].map(zoomGrade)).toEqual([0, 0, 1, 1, 2, 2, 3, 3]);
  });
  it("확대할수록 묶음 반경이 작아진다(전국은 옛 지도와 같은 100px)", () => {
    expect([100, 300, 800].map(clusterRadius)).toEqual([100, 86, 72]);
    expect(clusterRadius(1400)).toBeCloseTo(60); // 최대 상세 시작
  });
  it("더 깊이 확대하면 반경이 계속 줄다가 26px에서 멈춘다(붙어 있는 사업장이 풀리게)", () => {
    const r = [1400, 3000, 8000, 20000, 32768].map(clusterRadius);
    for (let i = 1; i < r.length; i++) expect(r[i]).toBeLessThanOrEqual(r[i - 1]);
    expect(clusterRadius(1e9)).toBe(MIN_SEPARATION_PX);
    expect(r[r.length - 1]).toBeGreaterThanOrEqual(MIN_SEPARATION_PX);
  });
  it("빈 점 목록의 경계는 null", () => {
    expect(boundsOf([])).toBeNull();
  });
});

describe("묶기", () => {
  const f = (a: number[]) => Float32Array.from(a);
  it("같은 칸의 점은 하나로 묶이고 대표 단계는 가장 높은 것이다", () => {
    const cs = clusterGrid(f([1, 2, 100]), f([1, 2, 100]), Int8Array.from([0, 3, 1]), 20, 300, 300);
    expect(cs).toHaveLength(2);
    const big = cs.find((c) => c.count === 2)!;
    expect(big.maxRank).toBe(3);
    expect(big.members).toEqual([0, 1]);
  });
  it("공백(-1)만 있는 묶음의 순번은 -1이다", () => {
    const cs = clusterGrid(f([1, 2]), f([1, 2]), Int8Array.from([-1, -1]), 20, 100, 100);
    expect(cs[0].maxRank).toBe(-1);
  });
  it("화면 밖 점은 건너뛴다", () => {
    const cs = clusterGrid(f([-500, 10]), f([10, 10]), Int8Array.from([4, 0]), 20, 100, 100);
    expect(cs).toHaveLength(1);
    expect(cs[0].members).toEqual([1]);
  });
  it("모든 점이 정확히 한 묶음에 들어간다(만 개)", () => {
    const n = 10000;
    const xs = new Float32Array(n), ys = new Float32Array(n);
    for (let i = 0; i < n; i++) { xs[i] = (i * 37) % 800; ys[i] = (i * 91) % 600; }
    const cs = clusterGrid(xs, ys, new Int8Array(n), 26, 800, 600);
    expect(cs.reduce((s, c) => s + c.count, 0)).toBe(n);
  });
  it("가장 가까운 묶음을 반경 안에서 찾는다", () => {
    const cs = clusterGrid(f([10, 100]), f([10, 100]), Int8Array.from([0, 0]), 20, 300, 300);
    expect(nearestCluster(cs, 12, 12, 10)).toBeGreaterThanOrEqual(0);
    expect(nearestCluster(cs, 200, 200, 10)).toBe(-1);
  });
});

describe("줌에 따른 묶기", () => {
  const f = (a: number[]) => Float32Array.from(a);
  it("반경 안의 이웃은 합쳐지고 먼 점은 남는다", () => {
    const cs = clusterRadiusMerge(f([0, 60, 400]), f([0, 0, 0]), Int8Array.from([0, 3, 1]), 86, 800, 600);
    expect(cs).toHaveLength(2);
    expect(cs.find((c) => c.count === 2)!.maxRank).toBe(3);
  });
  it("확대(반경 안에서 멀어짐)하면 묶음이 풀린다", () => {
    const near = clusterRadiusMerge(f([100, 150]), f([100, 100]), new Int8Array(2), 86, 800, 600);
    const far = clusterRadiusMerge(f([100, 350]), f([100, 100]), new Int8Array(2), 86, 800, 600);
    expect(near).toHaveLength(1);
    expect(far).toHaveLength(2);
  });
  it("합친 뒤 남은 묶음끼리는 서로 반경 이상 떨어져 있다", () => {
    const n = 900;
    const xs = new Float32Array(n), ys = new Float32Array(n);
    for (let i = 0; i < n; i++) { xs[i] = (i * 37) % 800; ys[i] = (i * 91) % 600; }
    const cs = clusterRadiusMerge(xs, ys, new Int8Array(n), 100, 800, 600);
    expect(cs.reduce((s, c) => s + c.count, 0)).toBe(n);
    for (let i = 0; i < cs.length; i++) for (let j = i + 1; j < cs.length; j++) {
      expect(Math.hypot(cs[i].x - cs[j].x, cs[i].y - cs[j].y)).toBeGreaterThanOrEqual(99.99);
    }
  });
});

describe("움직이는 동안 묶음 따라가기", () => {
  const cs = [{ x: 100, y: 50, count: 7, maxRank: 3, members: [0, 1, 2, 3, 4, 5, 6] }];
  it("이동(드래그)하면 위치만 같은 만큼 옮겨지고 구성은 그대로다", () => {
    const out = carryClusters(cs, { scale: 100, ox: 0, oy: 0 }, { scale: 100, ox: 30, oy: -20 });
    expect(out[0]).toMatchObject({ x: 130, y: 30, count: 7, maxRank: 3 });
    expect(out[0].members).toEqual(cs[0].members);
  });
  it("확대하면 월드 좌표가 같은 위치로 간다", () => {
    const from = { scale: 100, ox: 10, oy: 10 };
    const to = { scale: 200, ox: -5, oy: 0 };
    const [c] = carryClusters(cs, from, to);
    // 월드 좌표 = (화면 - ox) / scale 이 두 보기에서 같아야 한다
    expect((c.x - to.ox) / to.scale).toBeCloseTo((100 - from.ox) / from.scale);
    expect((c.y - to.oy) / to.scale).toBeCloseTo((50 - from.oy) / from.scale);
  });
  it("원본 묶음은 바꾸지 않는다(놓은 뒤 새로 계산하므로 캐시가 오염되면 안 된다)", () => {
    carryClusters(cs, { scale: 1, ox: 0, oy: 0 }, { scale: 2, ox: 9, oy: 9 });
    expect(cs[0].x).toBe(100);
  });
});

describe("다각형 안 판정과 단계 순번", () => {
  const square: Array<[number, number]> = [[0, 0], [10, 0], [10, 10], [0, 10]];
  const hole: Array<[number, number]> = [[4, 4], [6, 4], [6, 6], [4, 6]];
  it("안·밖·구멍", () => {
    expect(pointInRings(5, 2, [square, hole])).toBe(true);
    expect(pointInRings(5, 5, [square, hole])).toBe(false);
    expect(pointInRings(20, 5, [square, hole])).toBe(false);
  });
  it("공백은 모든 단계보다 낮다", () => {
    expect(rankOf(null)).toBeLessThan(rankOf("ok"));
    expect(rankOf("exceed")).toBe(4);
  });
});

describe("부드러운 이동", () => {
  const W = 800, H = 600;
  const a = { scale: 100, ox: 10, oy: 20 };
  const b = { scale: 1600, ox: -3000, oy: -900 };
  it("처음엔 출발 보기, 끝엔 도착 보기와 같다", () => {
    const s = interpolateView(a, b, 0, W, H), e = interpolateView(a, b, 1, W, H);
    expect(s.scale).toBeCloseTo(a.scale); expect(s.ox).toBeCloseTo(a.ox); expect(s.oy).toBeCloseTo(a.oy);
    expect(e.scale).toBeCloseTo(b.scale); expect(e.ox).toBeCloseTo(b.ox); expect(e.oy).toBeCloseTo(b.oy);
  });
  it("배율은 비율로 섞인다(절반 지점이 기하평균)", () => {
    expect(interpolateView(a, b, 0.5, W, H).scale).toBeCloseTo(Math.sqrt(100 * 1600));
  });
  it("화면 중심의 세계 좌표는 직선으로 움직인다", () => {
    const [fx, fy] = centerOf(a, W, H), [tx, ty] = centerOf(b, W, H);
    const [mx, my] = centerOf(interpolateView(a, b, 0.5, W, H), W, H);
    expect(mx).toBeCloseTo((fx + tx) / 2); expect(my).toBeCloseTo((fy + ty) / 2);
  });
  it("가속은 처음 빠르고 끝에서 느려진다(0~1, 단조 증가)", () => {
    expect(easeOutCubic(0)).toBe(0); expect(easeOutCubic(1)).toBe(1);
    expect(easeOutCubic(0.5)).toBeGreaterThan(0.5);
    expect(easeOutCubic(-1)).toBe(0); expect(easeOutCubic(2)).toBe(1);
  });
  it("세계 좌표를 화면 가운데에 둔다", () => {
    const v = centeredOn(218.3, 99.1, 900, W, H);
    expect(centerOf(v, W, H)[0]).toBeCloseTo(218.3);
    expect(centerOf(v, W, H)[1]).toBeCloseTo(99.1);
    expect(toScreen(v, 218.3, 99.1)).toEqual([W / 2, H / 2]);
  });
  it("이미 최대 상세로 확대돼 있고 여백 안이면 움직이지 않고, 아니면 움직인다", () => {
    const v = { scale: FOCUS_SCALE + 100, ox: 0, oy: 0 };
    expect(needsFocus(v, 400, 300, W, H)).toBe(false);
    expect(needsFocus(v, 20, 300, W, H)).toBe(true); // 왼쪽 가장자리
    expect(needsFocus(v, 400, 20, W, H)).toBe(true); // 위쪽 가장자리
    expect(needsFocus(v, 400, H - 30, W, H)).toBe(true); // 아래쪽 가장자리
    expect(needsFocus({ scale: 900, ox: 0, oy: 0 }, 400, 300, W, H)).toBe(true); // 아직 덜 확대(예전엔 충분하다고 봤다)
  });
});

describe("묶음을 눌러 쭉쭉 확대", () => {
  const W = 800, H = 500;
  const tight = { minX: 100, minY: 50, maxX: 100.02, maxY: 50.02 }; // 한곳에 모인 묶음
  const wide = { minX: 90, minY: 45, maxX: 110, maxY: 55 }; // 넓게 퍼진 묶음
  it("구성원이 한곳에 모여 있으면 그곳으로 크게 확대된다(확대 한도까지)", () => {
    const v = stepZoomView(tight, { scale: 100, ox: 0, oy: 0 }, W, H);
    expect(v.scale).toBeGreaterThan(200);
    expect(v.scale).toBeLessThanOrEqual(MAX_SCALE);
    expect(centerOf(v, W, H)[0]).toBeCloseTo(100.01);
  });
  it("넓게 퍼져 있어도 한 번 누를 때마다 최소 2배는 확대돼 계속 파고든다", () => {
    const v = stepZoomView(wide, { scale: 100, ox: 0, oy: 0 }, W, H);
    expect(v.scale).toBeGreaterThanOrEqual(200 - 1e-6);
    const v2 = stepZoomView(wide, v, W, H);
    expect(v2.scale).toBeGreaterThanOrEqual(v.scale * 2 - 1e-6);
  });
  it("확대 한도를 넘지 않는다", () => {
    expect(stepZoomView(tight, { scale: MAX_SCALE - 100, ox: 0, oy: 0 }, W, H).scale).toBe(MAX_SCALE);
  });
  it("이동 시간은 배율 차이가 클수록 길고 450~900ms 안이다", () => {
    expect(flightDuration(100, 100)).toBe(450);
    expect(flightDuration(100, 1600)).toBeGreaterThan(flightDuration(100, 200));
    expect(flightDuration(20, MAX_SCALE)).toBeLessThanOrEqual(900);
    expect(flightDuration(1600, 100)).toBe(flightDuration(100, 1600)); // 방향과 무관
  });
});

describe("핀 클릭 범위(후광·빛기둥·배지 전체)", () => {
  const cl = (x: number, y: number, maxRank: number, count = 1) => ({ x, y, count, maxRank, members: [] as number[] });
  it("단계별 빛기둥 높이", () => {
    expect([-1, 0, 1, 2, 3, 4].map(beamHeight)).toEqual([0, 0, 26, 33, 40, 48]);
  });
  it("받침뿐 아니라 빛기둥 위쪽과 후광 가장자리도 맞는다", () => {
    const c = [cl(100, 100, 4)]; // 초과: 기둥 48px
    expect(pinHit(c, 100, 100)).toBe(0); // 받침
    expect(pinHit(c, 100, 60)).toBe(0); // 기둥 위쪽(받침에서 40px 위)
    expect(pinHit(c, 120, 100)).toBe(0); // 후광 가장자리
    expect(pinHit(c, 100, 53)).toBe(0); // 기둥 끝 근처(여유 포함)
  });
  it("여유(8px)를 넘어서면 맞지 않는다(빈 땅을 눌러도 선택되지 않는다)", () => {
    const c = [cl(100, 100, 4)];
    expect(pinHit(c, 100, 30)).toBe(-1); // 기둥 끝에서 한참 위
    expect(pinHit(c, 160, 100)).toBe(-1); // 옆으로 멀리
    expect(pinHit(c, 100, 130)).toBe(-1); // 아래로 멀리
  });
  it("개수 배지도 누를 수 있다", () => {
    const c = [cl(100, 100, 3, 13)];
    const b = pinBox(c[0]);
    expect(pinHit(c, b.x1 - 3, b.y0 + 8)).toBe(0); // 배지 안
  });
  it("정상·공백 핀은 작지만 받침 주변은 넉넉하게 맞는다", () => {
    const c = [cl(100, 100, 0), cl(300, 100, -1)];
    expect(pinHit(c, 108, 100)).toBe(0);
    expect(pinHit(c, 300, 96)).toBe(1);
  });
  it("가까운 핀이 겹치면 받침이 더 가까운 쪽을 고른다", () => {
    const c = [cl(100, 100, 2), cl(112, 100, 2)];
    expect(pinHit(c, 109, 100)).toBe(1);
    expect(pinHit(c, 101, 100)).toBe(0);
  });
});

describe("확대해도 안 갈라지는 묶음", () => {
  it("한도까지 확대하면 갈라질 만큼 떨어져 있으면 갈라진다(산업단지에서 흔한 20~30px 간격)", () => {
    // 4096에서 20px 떨어진 두 사업장 = 월드 거리 20/4096. 한도(8배 더 깊이)에서는 160px
    const b = { minX: 100, minY: 50, maxX: 100 + 20 / 4096, maxY: 50 };
    expect(canSeparate(b)).toBe(true);
  });
  it("좌표가 같거나 사실상 같으면 아무리 확대해도 안 갈라진다", () => {
    expect(canSeparate({ minX: 100, minY: 50, maxX: 100, maxY: 50 })).toBe(false);
    expect(canSeparate({ minX: 100, minY: 50, maxX: 100 + 5 / MAX_SCALE, maxY: 50 })).toBe(false); // 한도에서 5px
  });
  it("경계: 한도에서 최소 간격(26px)이 되는 순간부터 갈라지는 것으로 본다", () => {
    expect(canSeparate({ minX: 0, minY: 0, maxX: MIN_SEPARATION_PX / MAX_SCALE, maxY: 0 })).toBe(true);
    expect(canSeparate({ minX: 0, minY: 0, maxX: (MIN_SEPARATION_PX - 1) / MAX_SCALE, maxY: 0 })).toBe(false);
  });
});

describe("축소·이동 한계", () => {
  const b = { minX: 100, minY: 60, maxX: 105, maxY: 66 }; // 지도 전체 범위(세계 좌표)
  const W = 800, H = 500;

  it("가장 줄일 수 있는 배율은 전국 보기(여백 28px)와 같다", () => {
    expect(minScaleFor(b, W, H)).toBeCloseTo(fitView(b, W, H, 28).scale, 9);
    expect(minScaleFor(b, W, H)).toBeCloseTo(Math.min((W - 56) / 5, (H - 56) / 6), 9);
  });

  it("그 배율보다 작은 보기는 그 배율로 올리고 화면 가운데에 둔다", () => {
    const min = minScaleFor(b, W, H);
    const tiny = { scale: min / 10, ox: -9999, oy: 9999 };
    const v = clampView(tiny, b, W, H, min);
    expect(v.scale).toBeCloseTo(min, 9);
    // 지도 중심이 화면 중심에 온다(지도가 화면보다 작으면 가운데)
    const cx = ((b.minX + b.maxX) / 2) * v.scale + v.ox, cy = ((b.minY + b.maxY) / 2) * v.scale + v.oy;
    expect(cx).toBeCloseTo(W / 2, 6);
    expect(cy).toBeCloseTo(H / 2, 6);
  });

  it("이미 한도 안의 보기는 그대로 둔다", () => {
    const min = minScaleFor(b, W, H);
    const view = { scale: min * 4, ox: -(b.minX * min * 4) - 300, oy: -(b.minY * min * 4) - 200 };
    expect(clampView(view, b, W, H, min)).toEqual(view);
  });

  it("지도를 화면 밖으로 너무 밀어낼 수 없다(가장자리가 화면 안쪽 25%보다 더 들어오지 못한다)", () => {
    const min = minScaleFor(b, W, H);
    const scale = min * 4;
    const far = clampView({ scale, ox: 99999, oy: 99999 }, b, W, H, min); // 오른쪽·아래로 한없이 민 보기
    expect(b.minX * scale + far.ox).toBeCloseTo(W * 0.25, 6); // 지도 왼쪽 끝은 화면 25% 지점에서 멈춘다
    expect(b.minY * scale + far.oy).toBeCloseTo(H * 0.25, 6);
    const left = clampView({ scale, ox: -99999, oy: -99999 }, b, W, H, min);
    expect(b.maxX * scale + left.ox).toBeCloseTo(W * 0.75, 6); // 오른쪽 끝은 75% 지점
    expect(b.maxY * scale + left.oy).toBeCloseTo(H * 0.75, 6);
  });

  it("배율을 올려 맞출 때는 화면 중앙을 기준으로 한다", () => {
    const min = minScaleFor(b, W, H);
    const scale = min * 2;
    const view = { scale: min * 2, ox: -(b.minX * scale) - 400, oy: -(b.minY * scale) - 250 };
    const lower = { ...view, scale: min * 0.5 }; // 한도보다 작은 배율
    const v = clampView(lower, b, W, H, min);
    expect(v.scale).toBeCloseTo(min, 9);
  });
});

