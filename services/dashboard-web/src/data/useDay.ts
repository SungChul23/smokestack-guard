// 데이터 훅. 운영은 서버 API(/api/sites, /api/day), 개발은 로컬 정적 JSON(/dev-data/)을 읽는다.
// 화면은 이 훅의 반환값만 본다.
import { useEffect, useState } from "react";
import { apiGet } from "../api";
import type { DayData, GeoRegion, Site } from "./model";

export interface DashboardData {
  sites: Site[];
  day: DayData;
  geo: GeoRegion[];
}
export type DataState =
  | { status: "loading" }
  | { status: "unavailable"; reason: string }
  | { status: "ready"; data: DashboardData };

/** 지역 경계·등고선은 사업장 정보가 없는 정적 파일이라 개발·운영 모두 public/map-data/에서 읽는다(CDN 캐시) */
export const MAP_DATA = "/map-data";
/** 로컬 전용 데이터(실제 사업장명·측정값). 개발 서버만 내준다 */
const DEV_DATA = "/dev-data";

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  const type = res.headers.get("content-type") ?? "";
  if (!res.ok || !type.includes("json")) throw new Error(`${url} 없음 (${res.status})`);
  return (await res.json()) as T;
}

/** 운영(빌드)은 서버 API, 개발은 dev-data. VITE_DATA_SOURCE=api|dev 로 바꿀 수 있다 */
export function usesApi(): boolean {
  const pick = import.meta.env.VITE_DATA_SOURCE;
  return pick === "api" || (pick !== "dev" && import.meta.env.PROD);
}

/**
 * 지역 경계는 지도에 땅을 그리는 용도뿐이다. 못 읽어도(배포 누락·네트워크) 사업장·목록·차트는 그대로 보이게 빈 목록으로 둔다.
 * 네이버 지도 모드는 경계 없이도 쓴다.
 */
async function loadGeo(): Promise<GeoRegion[]> {
  try {
    return await getJson<GeoRegion[]>(`${MAP_DATA}/geo.json`);
  } catch {
    return [];
  }
}

export async function loadDevData(): Promise<DashboardData> {
  const [sites, day, geo] = await Promise.all([
    getJson<Site[]>(`${DEV_DATA}/sites.json`),
    getJson<DayData>(`${DEV_DATA}/day.json`),
    loadGeo(),
  ]);
  return { sites, day, geo };
}

/** 서버(/api/sites, /api/day)에서 읽는다. 로그인 토큰은 읽는 순간의 값을 쓴다(갱신돼도 다시 읽지 않는다) */
export async function loadApiData(getToken: () => string | undefined): Promise<DashboardData> {
  const token = getToken();
  if (!token) throw new Error("로그인 정보가 없다");
  const [sites, day, geo] = await Promise.all([
    apiGet<Site[]>(token, "/api/sites"),
    apiGet<DayData>(token, "/api/day"),
    loadGeo(),
  ]);
  return { sites, day, geo };
}

export function makeLoader(getToken: () => string | undefined): () => Promise<DashboardData> {
  return () => (usesApi() ? loadApiData(getToken) : loadDevData());
}

/** 적재가 매시 :15·:45에 돈다(012). 그보다 조금 늦은 :17·:47에 새 값을 받으러 가기까지 남은 시간(ms) */
export function nextRefreshDelay(now: Date = new Date()): number {
  const min = now.getUTCMinutes(); // KST는 정시 단위 차이라 분은 같다
  const ms = (min * 60 + now.getUTCSeconds()) * 1000 + now.getUTCMilliseconds();
  const targets = [17, 47, 77].map((m) => m * 60000); // 77 = 다음 시각의 :17
  const next = targets.find((t) => t > ms) ?? targets[0];
  return next - ms;
}

const RETRY_MS = 2 * 60 * 1000; // 새 시각이 아직 안 들어왔거나 읽기에 실패하면 2분 뒤 다시
const MAX_RETRY = 5;

/** 최신 시각이 다른가(같으면 아직 새 적재가 없다) */
const stampOf = (d: DashboardData) => d.day.times[d.day.times.length - 1];

/**
 * 데이터를 읽는다. refresh가 켜져 있으면(운영) 열어 둔 화면도 30분 적재 직후에 조용히 새 값으로 바꾼다.
 * 새로 읽는 동안 지금 화면은 그대로 두고, 실패해도 지금 데이터를 지우지 않는다.
 */
export function useDashboardData(load: () => Promise<DashboardData>, refresh = false): DataState {
  // load 함수가 바뀔 때만 다시 읽는다(화면이 다시 그려질 때마다 읽지 않는다)
  const [state, setState] = useState<DataState>({ status: "loading" });
  useEffect(() => {
    let alive = true;
    let timer = 0;
    let last: number | undefined;
    let retries = 0;

    const schedule = (ms: number) => {
      if (!refresh) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(() => void again(), ms);
    };
    const again = async () => {
      try {
        const data = await load();
        if (!alive) return;
        if (stampOf(data) === last && retries < MAX_RETRY) { // 새 적재가 아직 없다
          retries++;
          schedule(RETRY_MS);
          return;
        }
        retries = 0;
        last = stampOf(data);
        setState({ status: "ready", data });
        schedule(nextRefreshDelay());
      } catch {
        if (!alive) return;
        schedule(RETRY_MS); // 지금 화면은 그대로 둔다
      }
    };

    load()
      .then((data) => {
        if (!alive) return;
        last = stampOf(data);
        setState({ status: "ready", data });
        schedule(nextRefreshDelay());
      })
      .catch((e: Error) => alive && setState({ status: "unavailable", reason: e.message }));

    const onVisible = () => {
      if (document.visibilityState === "visible" && refresh && last !== undefined) {
        // 탭이 숨어 있는 동안 타이머가 밀렸을 수 있다: 보이면 한 번 확인한다
        retries = 0;
        window.clearTimeout(timer);
        void again();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      alive = false;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [load, refresh]);
  return state;
}
