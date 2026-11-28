// 네이버 지도 SDK 읽기(지연 로딩). 사용자가 네이버 지도를 고를 때 처음 한 번만 읽는다(처음 화면 로딩을 늘리지 않는다).
// 규칙(옛 지도 map-engine-switchable.js에서 옮김): 주소는 maps.js?ncpKeyId=<키>, 20초 안에 안 되면 시간 초과, 스크립트 오류·SDK가 비어 있으면 실패,
// 인증 실패는 SDK가 전역 함수 navermap_authFailure를 부르는 것으로 안다(읽는 도중이든 읽은 뒤든). 어느 경우든 관제 지도는 계속 쓴다.
// 키는 공개용 앱 ID라 config.ts에 기본값으로 두고, 환경 변수 VITE_NAVER_MAP_KEY_ID로 덮어쓸 수 있다.
// 인증이 통과하려면 네이버 클라우드 콘솔의 Web 서비스 URL에 이 화면의 주소(개발 http://localhost:5173, 운영 도메인)가 등록돼 있어야 한다.
import { NAVER_DEFAULT_KEY_ID } from "./config";
import type { NaverMaps } from "./types";

export const NAVER_SDK_URL = "https://oapi.map.naver.com/openapi/v3/maps.js";
export const NAVER_TIMEOUT_MS = 20000;

export const NAVER_NOTES = {
  loading: "네이버 지도를 불러오는 중입니다. 관제 지도는 계속 사용할 수 있습니다.",
  timeout: "지도 연결 시간이 초과되었습니다. 다시 선택해 주세요.",
  script: "지도 연결을 확인하고 다시 선택해 주세요.",
  noMap: "네이버 지도 연결을 확인해 주세요.",
  auth: "네이버 지도 인증을 확인해 주세요(허용된 도메인인지 확인). 관제 지도는 계속 사용할 수 있습니다.",
  noKey: "네이버 지도 키가 비어 있어 사용할 수 없습니다.",
} as const;
export type NaverNoteKind = keyof typeof NAVER_NOTES;

export class NaverLoadError extends Error {
  readonly kind: NaverNoteKind;
  constructor(kind: NaverNoteKind) {
    super(NAVER_NOTES[kind]);
    this.name = "NaverLoadError";
    this.kind = kind;
  }
}

/** 쓸 키: 환경 변수 VITE_NAVER_MAP_KEY_ID(덮어쓰기용)가 있으면 그 값, 없으면 config.ts의 공개 기본값 */
export function naverKeyId(): string {
  const override = String(import.meta.env.VITE_NAVER_MAP_KEY_ID ?? "").trim();
  return override || NAVER_DEFAULT_KEY_ID;
}

export const sdkSrc = (key: string) => `${NAVER_SDK_URL}?ncpKeyId=${encodeURIComponent(key)}`;

let promise: Promise<NaverMaps> | null = null;
let authFailed = false;
let rejectPending: ((e: Error) => void) | null = null;
const authListeners = new Set<() => void>();

/** 인증 실패(읽는 도중이든 읽은 뒤든)를 알려 받는다. 돌려주는 함수로 해제한다 */
export function onNaverAuthFailure(cb: () => void): () => void {
  authListeners.add(cb);
  return () => { authListeners.delete(cb); };
}

function installAuthHook(): void {
  window.navermap_authFailure = () => {
    authFailed = true; // 같은 화면에서 다시 읽어도 소용없다(키·도메인을 고친 뒤 새로 고침)
    promise = null;
    rejectPending?.(new NaverLoadError("auth"));
    authListeners.forEach((l) => l());
  };
}

/** SDK를 읽는다. 이미 읽었으면 그대로 돌려주고, 동시에 여러 번 불러도 한 번만 읽는다 */
export function loadNaverSdk(key: string = naverKeyId(), opts: { timeoutMs?: number } = {}): Promise<NaverMaps> {
  if (authFailed) return Promise.reject(new NaverLoadError("auth"));
  if (promise) return promise;
  const existing = window.naver?.maps;
  if (existing?.Map) { // 이미 페이지에 있다(다른 곳에서 읽었거나 시험)
    installAuthHook();
    promise = Promise.resolve(existing);
    return promise;
  }
  if (!key) return Promise.reject(new NaverLoadError("noKey"));
  installAuthHook();
  const p = new Promise<NaverMaps>((resolve, reject) => {
    const tag = document.createElement("script");
    const timer = window.setTimeout(() => { tag.remove(); reject(new NaverLoadError("timeout")); }, opts.timeoutMs ?? NAVER_TIMEOUT_MS);
    rejectPending = (e) => { window.clearTimeout(timer); tag.remove(); reject(e); };
    tag.async = true;
    tag.src = sdkSrc(key);
    tag.onload = () => {
      window.clearTimeout(timer);
      const maps = window.naver?.maps;
      if (maps?.Map) resolve(maps); else reject(new NaverLoadError("noMap"));
    };
    tag.onerror = () => { window.clearTimeout(timer); tag.remove(); reject(new NaverLoadError("script")); };
    document.head.append(tag);
  }).finally(() => { rejectPending = null; });
  promise = p.catch((e) => { promise = null; throw e; }); // 실패하면 다음 선택 때 다시 읽을 수 있게 비운다
  return promise;
}

/** 시험에서 읽기 상태를 처음으로 되돌린다 */
export function resetNaverLoader(): void {
  promise = null;
  authFailed = false;
  rejectPending = null;
  authListeners.clear();
  Reflect.deleteProperty(window, "navermap_authFailure");
}
