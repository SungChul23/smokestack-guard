// 서버(api.smokestack-guard.store) 호출 도우미: 로그인 토큰을 자동으로 붙인다.
// 사용: const data = await apiGet<T>(token, "/api/...")
import { API_BASE } from "./auth";

export async function apiGet<T>(accessToken: string, path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}
