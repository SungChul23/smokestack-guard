import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { favoriteSync, initialSelection, useSelection } from "../state/selection";
import { favoritePath, NOTICE, useFavoritesSync } from "./useFavorites";

const json = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));

let calls: { url: string; method: string; auth: string | null }[];
const mockServer = (opts: { list?: string[]; failWrite?: boolean; failList?: boolean } = {}) =>
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ url, method, auth: new Headers(init?.headers).get("Authorization") });
    if (method === "GET") return opts.failList ? json({}, 503) : json({ targets: opts.list ?? [] });
    return opts.failWrite ? json({}, 503) : json({ targets: [] });
  });

beforeEach(() => {
  calls = [];
  useSelection.setState({ ...initialSelection });
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  favoriteSync.onChange = undefined;
});

describe("즐겨찾기 서버 연결", () => {
  it("켜면 서버의 즐겨찾기를 읽어 화면에 넣는다(로그인 토큰으로)", async () => {
    mockServer({ list: ["100", "200"] });
    renderHook(() => useFavoritesSync("TOKEN", true));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(useSelection.getState().favorites).toEqual(["100", "200"]);
    expect(calls[0]).toMatchObject({ url: expect.stringContaining("/api/favorites"), method: "GET", auth: "Bearer TOKEN" });
  });

  it("개발(꺼짐)이나 토큰이 없으면 서버를 부르지 않고 화면 안에서만 바뀐다", async () => {
    mockServer();
    renderHook(() => useFavoritesSync("TOKEN", false));
    renderHook(() => useFavoritesSync(undefined, true));
    act(() => useSelection.getState().toggleFavorite("100"));
    expect(useSelection.getState().favorites).toEqual(["100"]);
    expect(calls).toHaveLength(0);
  });

  it("별을 누르면 바로 반영하고 서버에 PUT, 다시 누르면 DELETE", async () => {
    mockServer();
    renderHook(() => useFavoritesSync("T", true));
    await act(async () => { await Promise.resolve(); });
    act(() => useSelection.getState().toggleFavorite("A B/1"));
    expect(useSelection.getState().favorites).toEqual(["A B/1"]); // 서버 응답을 기다리지 않는다
    await act(async () => { await Promise.resolve(); });
    act(() => useSelection.getState().toggleFavorite("A B/1"));
    await act(async () => { await Promise.resolve(); });
    const writes = calls.filter((c) => c.method !== "GET");
    expect(writes.map((c) => c.method)).toEqual(["PUT", "DELETE"]);
    expect(writes[0].url).toContain(favoritePath("A B/1")); // 경로 문자는 인코딩된다
    expect(writes[0].auth).toBe("Bearer T");
  });

  it("저장에 실패하면 원래대로 되돌리고 안내한다(잠시 뒤 안내는 사라진다)", async () => {
    vi.useFakeTimers();
    mockServer({ failWrite: true });
    renderHook(() => useFavoritesSync("T", true));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    act(() => useSelection.getState().toggleFavorite("100"));
    expect(useSelection.getState().favorites).toEqual(["100"]);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(useSelection.getState().favorites).toEqual([]); // 되돌림
    expect(useSelection.getState().favoriteNotice).toBe(NOTICE.save);
    await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
    expect(useSelection.getState().favoriteNotice).toBeNull();
  });

  it("해제 저장이 실패하면 별이 다시 켜진다", async () => {
    mockServer({ list: ["100"], failWrite: true });
    renderHook(() => useFavoritesSync("T", true));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    act(() => useSelection.getState().toggleFavorite("100"));
    expect(useSelection.getState().favorites).toEqual([]);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(useSelection.getState().favorites).toEqual(["100"]);
  });

  it("불러오기에 실패하면 화면 안에서만 쓰고 안내한다", async () => {
    mockServer({ failList: true });
    renderHook(() => useFavoritesSync("T", true));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(useSelection.getState().favoriteNotice).toBe(NOTICE.load);
    expect(useSelection.getState().favorites).toEqual([]);
  });

  it("화면이 사라지면 서버 연결을 끊는다", () => {
    mockServer();
    const { unmount } = renderHook(() => useFavoritesSync("T", true));
    expect(favoriteSync.onChange).toBeTypeOf("function");
    unmount();
    expect(favoriteSync.onChange).toBeUndefined();
  });
});
