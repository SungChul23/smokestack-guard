import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installFakeNaver } from "../../test/fakeNaver";
import { NAVER_DEFAULT_KEY_ID } from "./config";
import {
  NAVER_NOTES, NAVER_SDK_URL, NAVER_TIMEOUT_MS, NaverLoadError, loadNaverSdk, naverKeyId, onNaverAuthFailure, resetNaverLoader, sdkSrc,
} from "./loader";

const KEY = "시험용-키/값 +&"; // 실제 키가 아니다(주소 인코딩 확인용)
const scripts = () => [...document.head.querySelectorAll<HTMLScriptElement>('script[src*="oapi.map.naver.com"]')];

beforeEach(() => {
  resetNaverLoader();
  Reflect.deleteProperty(window, "naver");
  for (const s of scripts()) s.remove();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  resetNaverLoader();
  Reflect.deleteProperty(window, "naver");
  for (const s of scripts()) s.remove();
});

describe("SDK 주소와 키", () => {
  it("옛 지도와 같은 주소와 ncpKeyId 매개변수를 쓴다(키는 주소용으로 인코딩)", () => {
    expect(NAVER_SDK_URL).toBe("https://oapi.map.naver.com/openapi/v3/maps.js");
    expect(sdkSrc("abc")).toBe("https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=abc");
    expect(sdkSrc(KEY)).toContain(encodeURIComponent(KEY));
    expect(NAVER_TIMEOUT_MS).toBe(20000);
  });

  it("키는 공개 기본값(config.ts)이고, 환경 변수 VITE_NAVER_MAP_KEY_ID가 있으면 그 값으로 덮어쓴다", () => {
    expect(naverKeyId()).toBe(NAVER_DEFAULT_KEY_ID);
    expect(naverKeyId()).not.toBe("");
    vi.stubEnv("VITE_NAVER_MAP_KEY_ID", "  my-key  ");
    expect(naverKeyId()).toBe("my-key"); // 앞뒤 공백은 지운다
    vi.stubEnv("VITE_NAVER_MAP_KEY_ID", "   ");
    expect(naverKeyId()).toBe(NAVER_DEFAULT_KEY_ID); // 빈 값이면 기본값
  });
});

describe("SDK 읽기: 성공", () => {
  it("스크립트를 한 번 붙이고, 읽히면 naver.maps를 돌려준다", async () => {
    const p = loadNaverSdk("k1");
    expect(scripts()).toHaveLength(1);
    expect(scripts()[0].src).toContain("ncpKeyId=k1");
    expect(scripts()[0].async).toBe(true);
    const fake = installFakeNaver(); // SDK가 읽혔다고 치고 window.naver를 채운 뒤 onload
    scripts()[0].onload?.(new Event("load"));
    await expect(p).resolves.toBe(window.naver!.maps);
    fake.uninstall();
  });

  it("동시에 여러 번 불러도 한 번만 읽는다(같은 약속을 돌려준다)", async () => {
    const a = loadNaverSdk("k1");
    const b = loadNaverSdk("k1");
    expect(a).toBe(b);
    expect(scripts()).toHaveLength(1);
    installFakeNaver();
    scripts()[0].onload?.(new Event("load"));
    await a;
  });

  it("한 번 읽은 뒤에는 다시 읽지 않는다", async () => {
    const p = loadNaverSdk("k1");
    installFakeNaver();
    scripts()[0].onload?.(new Event("load"));
    await p;
    const again = loadNaverSdk("k1");
    await expect(again).resolves.toBe(window.naver!.maps);
    expect(scripts()).toHaveLength(1);
  });

  it("이미 페이지에 SDK가 있으면 스크립트를 붙이지 않는다(키가 없어도 쓴다)", async () => {
    installFakeNaver();
    await expect(loadNaverSdk("")).resolves.toBe(window.naver!.maps);
    expect(scripts()).toHaveLength(0);
  });
});

describe("SDK 읽기: 실패 경로(모두 관제 지도를 계속 쓸 수 있게 오류로 알린다)", () => {
  it("키가 없으면 스크립트를 붙이지 않고 '키 없음'으로 실패한다", async () => {
    await expect(loadNaverSdk("")).rejects.toMatchObject({ kind: "noKey", message: NAVER_NOTES.noKey });
    expect(scripts()).toHaveLength(0);
  });

  it("스크립트 오류면 안내하고, 다음 선택 때 다시 읽을 수 있다", async () => {
    const p = loadNaverSdk("k1");
    scripts()[0].onerror?.(new Event("error"));
    await expect(p).rejects.toMatchObject({ kind: "script", message: NAVER_NOTES.script });
    expect(scripts()).toHaveLength(0); // 실패한 스크립트 태그는 치운다
    loadNaverSdk("k1").catch(() => {});
    expect(scripts()).toHaveLength(1); // 다시 시도
  });

  it("스크립트는 읽혔는데 SDK가 비어 있으면 연결 확인 안내로 실패한다", async () => {
    const p = loadNaverSdk("k1");
    scripts()[0].onload?.(new Event("load")); // window.naver 없음
    await expect(p).rejects.toMatchObject({ kind: "noMap", message: NAVER_NOTES.noMap });
  });

  it("20초 안에 안 되면 시간 초과로 실패하고 태그를 치운다", async () => {
    vi.useFakeTimers();
    const p = loadNaverSdk("k1");
    const assertion = expect(p).rejects.toMatchObject({ kind: "timeout", message: NAVER_NOTES.timeout });
    await vi.advanceTimersByTimeAsync(NAVER_TIMEOUT_MS - 1);
    expect(scripts()).toHaveLength(1); // 아직 기다리는 중
    await vi.advanceTimersByTimeAsync(2);
    await assertion;
    expect(scripts()).toHaveLength(0);
  });

  it("읽히면 시간 초과 타이머는 취소된다(나중에 실패로 바뀌지 않는다)", async () => {
    vi.useFakeTimers();
    const p = loadNaverSdk("k1");
    installFakeNaver();
    scripts()[0].onload?.(new Event("load"));
    await p;
    await vi.advanceTimersByTimeAsync(NAVER_TIMEOUT_MS * 2);
    await expect(loadNaverSdk("k1")).resolves.toBeTruthy();
  });

  it("읽는 도중 인증 실패(navermap_authFailure)면 인증 안내로 실패한다", async () => {
    const p = loadNaverSdk("k1");
    window.navermap_authFailure?.();
    await expect(p).rejects.toMatchObject({ kind: "auth" });
    expect(NAVER_NOTES.auth).toContain("허용된 도메인");
    expect(scripts()).toHaveLength(0);
  });

  it("읽은 뒤에 인증 실패가 와도 알려 받고, 같은 화면에서는 다시 시도하지 않는다", async () => {
    const p = loadNaverSdk("k1");
    installFakeNaver();
    scripts()[0].onload?.(new Event("load"));
    await p;
    const seen = vi.fn();
    const off = onNaverAuthFailure(seen);
    window.navermap_authFailure?.();
    expect(seen).toHaveBeenCalledTimes(1);
    await expect(loadNaverSdk("k1")).rejects.toMatchObject({ kind: "auth" }); // 소용없는 재시도를 막는다
    off();
    window.navermap_authFailure?.();
    expect(seen).toHaveBeenCalledTimes(1); // 해제한 뒤에는 알리지 않는다
  });

  it("오류는 NaverLoadError이고 안내 문구를 메시지로 가진다", async () => {
    const e = new NaverLoadError("timeout");
    expect(e).toBeInstanceOf(Error);
    expect(e.message).toBe(NAVER_NOTES.timeout);
    for (const note of Object.values(NAVER_NOTES)) expect(note.length).toBeGreaterThan(5);
  });

  it("인증 안내에는 키와 허용된 도메인을 확인하라는 말이 있다", () => {
    expect(NAVER_NOTES.auth).toMatch(/허용된 도메인/);
    expect(NAVER_NOTES.auth).toMatch(/관제 지도는 계속/);
  });
});
