// 서버(api.smokestack-guard.store) 호출 도우미: 로그인 토큰을 자동으로 붙인다.
// 사용: const data = await apiGet<T>(token, "/api/...")
// 오류는 ApiError로 던진다. code는 서버의 이유 코드(예: not_member, invalid_code) (013 contracts/auth-api.md)
import { API_BASE } from "./auth";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string | undefined,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(accessToken: string, path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${accessToken}`, ...(init.body ? { "Content-Type": "application/json" } : {}) },
  });
  if (!res.ok) {
    let code: string | undefined;
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail && typeof body.detail === "object") {
        code = body.detail.code;
        message = body.detail.message ?? message;
      }
    } catch {
      // 본문이 JSON이 아니면 상태 코드만
    }
    throw new ApiError(res.status, code, message);
  }
  return (await res.json()) as T;
}

export function apiGet<T>(accessToken: string, path: string): Promise<T> {
  return request<T>(accessToken, path);
}

/** 본문 없는 쓰기(PUT·DELETE). 즐겨찾기처럼 경로만으로 뜻이 정해지는 요청에 쓴다 */
export function apiSend<T>(accessToken: string, path: string, method: "PUT" | "DELETE"): Promise<T> {
  return request<T>(accessToken, path, { method });
}

export function apiPost<T>(accessToken: string, path: string, body: unknown): Promise<T> {
  return request<T>(accessToken, path, { method: "POST", body: JSON.stringify(body) });
}
