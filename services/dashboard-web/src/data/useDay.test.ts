import { afterEach, describe, expect, it, vi } from "vitest";
import { loadApiData, makeLoader, MAP_DATA, usesApi } from "./useDay";

const json = (body: unknown, ok = true, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status: ok ? status : 500, headers: { "content-type": "application/json" } }));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("데이터 출처", () => {
  it("개발(시험)은 기본이 dev-data, VITE_DATA_SOURCE=api면 서버", () => {
    expect(usesApi()).toBe(false);
    vi.stubEnv("VITE_DATA_SOURCE", "api");
    expect(usesApi()).toBe(true);
    vi.stubEnv("VITE_DATA_SOURCE", "dev");
    expect(usesApi()).toBe(false);
  });
});

describe("서버에서 읽기", () => {
  it("/api/sites, /api/day를 로그인 토큰으로 부르고 경계는 정적 파일에서 읽는다", async () => {
    const calls: { url: string; auth: string | null }[] = [];
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      calls.push({ url, auth: new Headers(init?.headers).get("Authorization") });
      if (url.endsWith("/api/sites")) return json([{ id: "1" }]);
      if (url.endsWith("/api/day")) return json({ times: [1], stacks: {} });
      return json([{ name: "서울" }]);
    });
    const data = await loadApiData(() => "TOKEN");
    expect(data.sites).toEqual([{ id: "1" }]);
    expect(data.day.times).toEqual([1]);
    expect(data.geo).toEqual([{ name: "서울" }]);
    const api = calls.filter((c) => c.url.includes("/api/"));
    expect(api).toHaveLength(2);
    expect(api.every((c) => c.auth === "Bearer TOKEN")).toBe(true);
    expect(calls.some((c) => c.url === `${MAP_DATA}/geo.json` && c.auth === null)).toBe(true); // 정적 파일엔 토큰을 보내지 않는다
  });

  it("토큰이 없으면 읽지 않고 이유를 알린다", async () => {
    const f = vi.fn();
    vi.stubGlobal("fetch", f);
    await expect(loadApiData(() => undefined)).rejects.toThrow("로그인 정보가 없다");
    expect(f).not.toHaveBeenCalled();
  });

  it("지역 경계 파일을 못 읽어도(배포 누락 등) 사업장·측정값은 그대로 보인다", async () => {
    vi.stubGlobal("fetch", (url: string) => {
      if (url.endsWith("/api/sites")) return json([{ id: "1" }]);
      if (url.endsWith("/api/day")) return json({ times: [1], stacks: {} });
      return Promise.resolve(new Response("<html>없음</html>", { status: 404, headers: { "content-type": "text/html" } }));
    });
    const data = await loadApiData(() => "T");
    expect(data.sites).toEqual([{ id: "1" }]);
    expect(data.geo).toEqual([]); // 땅 없이도 핀·네이버 지도·목록·차트는 쓴다
  });

  it("서버 오류(예: DB 꺼짐 503)는 오류로 올린다", async () => {
    vi.stubGlobal("fetch", (url: string) => (url.includes("/api/") ? Promise.resolve(new Response("{}", { status: 503 })) : json([])));
    await expect(loadApiData(() => "T")).rejects.toThrow();
  });

  it("makeLoader는 호출할 때의 최신 토큰을 쓴다", async () => {
    vi.stubEnv("VITE_DATA_SOURCE", "api");
    const seen: (string | null)[] = [];
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      if (url.includes("/api/")) seen.push(new Headers(init?.headers).get("Authorization"));
      return json(url.includes("/api/day") ? { times: [], stacks: {} } : []);
    });
    let token = "A";
    const load = makeLoader(() => token);
    await load();
    token = "B"; // 토큰이 갱신돼도 로더는 그대로, 다음 호출부터 새 토큰
    await load();
    expect(seen).toEqual(["Bearer A", "Bearer A", "Bearer B", "Bearer B"]);
  });
});

import { act, renderHook } from "@testing-library/react";
import { nextRefreshDelay, useDashboardData } from "./useDay";
import type { DashboardData, DataState } from "./useDay";

describe("적재 직후 새로 읽기", () => {
  const at = (h: number, m: number, s = 0) => new Date(Date.UTC(2026, 10, 20, h, m, s));
  it("다음 :17 또는 :47까지 남은 시간", () => {
    expect(nextRefreshDelay(at(1, 0))).toBe(17 * 60000);
    expect(nextRefreshDelay(at(1, 17))).toBe(30 * 60000); // 막 지났으면 다음(:47)
    expect(nextRefreshDelay(at(1, 20))).toBe(27 * 60000);
    expect(nextRefreshDelay(at(1, 50))).toBe(27 * 60000); // 다음 시각 :17
    expect(nextRefreshDelay(at(1, 46, 30))).toBe(30000);
  });

  const lastOf = (st: DataState) => (st.status === "ready" ? st.data.day.times[st.data.day.times.length - 1] : undefined);
  const data = (last: number): DashboardData => ({ sites: [], geo: [], day: { times: [last - 1000, last], stacks: {} } });

  it("refresh가 켜져 있으면 때가 되어 새 시각이 오면 조용히 바꾼다(그동안 화면 유지)", async () => {
    vi.useFakeTimers({ now: at(1, 0) });
    const load = vi.fn().mockResolvedValueOnce(data(100)).mockResolvedValue(data(200));
    const { result } = renderHook(() => useDashboardData(load, true));
    await act(async () => { await Promise.resolve(); });
    expect(lastOf(result.current)).toBe(100);
    await act(async () => { await vi.advanceTimersByTimeAsync(17 * 60000); });
    expect(load).toHaveBeenCalledTimes(2);
    expect(lastOf(result.current)).toBe(200);
    vi.useRealTimers();
  });

  it("아직 새 시각이 없으면(같은 최신 시각) 2분 뒤 다시 확인한다", async () => {
    vi.useFakeTimers({ now: at(1, 0) });
    const load = vi.fn().mockResolvedValueOnce(data(100)).mockResolvedValueOnce(data(100)).mockResolvedValue(data(200));
    const { result } = renderHook(() => useDashboardData(load, true));
    await act(async () => { await Promise.resolve(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(17 * 60000); });
    expect(lastOf(result.current)).toBe(100); // 변화 없음
    await act(async () => { await vi.advanceTimersByTimeAsync(2 * 60000); });
    expect(lastOf(result.current)).toBe(200);
    vi.useRealTimers();
  });

  it("읽기에 실패해도 지금 데이터를 지우지 않는다", async () => {
    vi.useFakeTimers({ now: at(1, 0) });
    const load = vi.fn().mockResolvedValueOnce(data(100)).mockRejectedValueOnce(new Error("503")).mockResolvedValue(data(200));
    const { result } = renderHook(() => useDashboardData(load, true));
    await act(async () => { await Promise.resolve(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(17 * 60000); });
    expect(result.current.status).toBe("ready");
    await act(async () => { await vi.advanceTimersByTimeAsync(2 * 60000); });
    expect(lastOf(result.current)).toBe(200);
    vi.useRealTimers();
  });

  it("refresh가 꺼져 있으면(개발·시험) 다시 읽지 않는다", async () => {
    vi.useFakeTimers({ now: at(1, 0) });
    const load = vi.fn().mockResolvedValue(data(100));
    renderHook(() => useDashboardData(load, false));
    await act(async () => { await vi.advanceTimersByTimeAsync(60 * 60000); });
    expect(load).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});
