// 선택 상태 (spec 318 §4). 사용자가 **고른 것**만 담는다. 측정값은 담지 않는다(데이터 훅이 가져온다).
// 지도·목록·차트·에이전트 창·공지 배너는 이 스토어를 읽기만 하고, 선택이 바뀌면 자동으로 다시 그려진다.
// 선택(사업장·굴뚝)과 지도 위치(시도·시군)는 서로 독립이다: 선택해도 지도가 한 지역에 갇히지 않는다.
import { create } from "zustand";
import type { ChartRange } from "../logic/chartRange";
import type { LevelKey } from "../logic/status";

export type Pollutant = "nox" | "sox";
export type PeriodHours = 6 | 12 | 24 | 48 | 72 | 168;
/** 물질을 보여 줄 때의 늘 같은 순서 */
export const POLLUTANT_ORDER: readonly Pollutant[] = ["nox", "sox"];
export type MapLevel = "nation" | "sido" | "sigungu";
/** 지도에 표시할 수 있는 상태: 정상·주의·경고·위험·초과, 그리고 측정값이 없는 공백(미수신·점검·가동중지 등) */
export type MapShowKey = LevelKey | "gap";
export const MAP_SHOW_ORDER: readonly MapShowKey[] = ["ok", "caution", "warn", "risk", "exceed", "gap"];

/** 지도가 지금 보여 주는 범위(월드 좌표). 경고 목록이 "지도에 보이는 사업장"을 고르는 데 쓴다 */
export interface MapBounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export interface MapPath {
  sido: string | null;
  sigungu: string | null;
}

export interface SelectionData {
  selectedSiteId: string | null;
  selectedStackCode: string | null;
  /** 차트에 함께 보여 줄 물질(0~2개, 늘 NOx → SOx 순서). 비어 있으면 그래프를 그리지 않는다 */
  pollutants: Pollutant[];
  periodHours: PeriodHours;
  /** 사용자가 지정한 조회 범위(한국 시각 기준 ms). null이면 자료 기준 기본 범위(마지막에서 periodHours시간) */
  chartRange: ChartRange | null;
  mapPath: MapPath;
  /** 보고 싶은 상태 단계. 비어 있으면 모두 */
  statusFilter: LevelKey[];
  /** 지도에 표시할 상태. 목록 필터와는 따로다. 처음에는 모두 켠다 */
  mapLevels: MapShowKey[];
  /** 지도가 지금 보여 주는 범위(이동·확대를 멈춘 뒤 갱신). 지도가 아직 없으면 null */
  mapBounds: MapBounds | null;
  search: string;
  /** 즐겨찾기한 사업장 id(서버에는 Cognito sub 기준으로 저장한다) */
  favorites: string[];
  /** 즐겨찾기 사업장만 보기: 지도와 목록 모두에 적용된다 */
  favoritesOnly: boolean;
  /** 즐겨찾기 저장·불러오기 실패 안내(잠깐 띄우고 지운다) */
  favoriteNotice: string | null;
}

export interface SelectionActions {
  selectSite: (siteId: string, stackCode?: string | null) => void;
  selectStack: (stackCode: string | null) => void;
  clearSelection: () => void;
  /** 물질을 켜고 끈다. 둘 다 켤 수 있고 둘 다 끌 수도 있다(옛 웹과 같음) */
  togglePollutant: (pollutant: Pollutant) => void;
  /** 기간 버튼: 사용자가 지정한 범위가 있으면 지우고 자료 기준 기본 범위로 돌아간다 */
  setPeriodHours: (hours: PeriodHours) => void;
  /** 조회 범위를 지정한다(null이면 자료 기준으로 되돌린다) */
  setChartRange: (range: ChartRange | null) => void;
  enterSido: (sido: string) => void;
  enterSigungu: (sigungu: string) => void;
  goUp: () => void;
  goNation: () => void;
  /** 지도가 지금 보여 주는 범위를 알린다(같으면 아무 것도 바꾸지 않는다) */
  setMapBounds: (bounds: MapBounds | null) => void;
  /** 지도 중앙이 가리키는 지역을 한 번에 정한다(같으면 아무 것도 바꾸지 않는다) */
  setMapPath: (path: MapPath) => void;
  toggleStatus: (level: LevelKey) => void;
  /** 지도에 표시할 상태를 켜고 끈다 */
  toggleMapLevel: (level: MapShowKey) => void;
  setSearch: (text: string) => void;
  /** 별표를 누른다: 화면에 먼저 반영하고 favoriteSync가 서버에 저장한다 */
  toggleFavorite: (siteId: string) => void;
  /** 서버 값으로 바꾸거나 저장 실패를 되돌린다(서버 저장을 다시 부르지 않는다) */
  setFavorites: (ids: string[]) => void;
  applyFavorite: (siteId: string, on: boolean) => void;
  setFavoritesOnly: (on: boolean) => void;
  setFavoriteNotice: (message: string | null) => void;
}

/** 즐겨찾기 서버 저장 연결: 운영에서만 DashboardApp이 넣는다(개발·시험은 화면 안에서만 바뀐다) */
export const favoriteSync: { onChange?: (siteId: string, on: boolean) => void } = {};

export type SelectionState = SelectionData & SelectionActions;

export const initialSelection: SelectionData = {
  selectedSiteId: null,
  selectedStackCode: null,
  pollutants: ["nox"],
  periodHours: 24,
  chartRange: null,
  mapPath: { sido: null, sigungu: null },
  statusFilter: [],
  mapLevels: ["risk", "exceed"], // 처음에는 위험·초과만 보인다(웹 기본). 나머지 상태는 칩으로 켠다
  mapBounds: null,
  search: "",
  favorites: [],
  favoritesOnly: false,
  favoriteNotice: null,
};

export const useSelection = create<SelectionState>()((set) => ({
  ...initialSelection,

  selectSite: (siteId, stackCode = null) => set({ selectedSiteId: siteId, selectedStackCode: stackCode }),
  // 사업장을 먼저 골라야 굴뚝을 고를 수 있다
  selectStack: (stackCode) => set((s) => (s.selectedSiteId ? { selectedStackCode: stackCode } : {})),
  clearSelection: () => set({ selectedSiteId: null, selectedStackCode: null }),

  togglePollutant: (pollutant) =>
    set((s) => {
      const on = s.pollutants.includes(pollutant);
      const next = on ? s.pollutants.filter((p) => p !== pollutant) : [...s.pollutants, pollutant];
      return { pollutants: POLLUTANT_ORDER.filter((p) => next.includes(p)) };
    }),
  setPeriodHours: (periodHours) => set({ periodHours, chartRange: null }),
  setChartRange: (chartRange) => set({ chartRange }),

  enterSido: (sido) => set({ mapPath: { sido, sigungu: null } }),
  // 시군은 시도 안에서만 들어간다
  enterSigungu: (sigungu) => set((s) => (s.mapPath.sido ? { mapPath: { sido: s.mapPath.sido, sigungu } } : {})),
  goUp: () =>
    set((s) => {
      if (s.mapPath.sigungu) return { mapPath: { sido: s.mapPath.sido, sigungu: null } };
      if (s.mapPath.sido) return { mapPath: { sido: null, sigungu: null } };
      return {};
    }),
  goNation: () => set({ mapPath: { sido: null, sigungu: null } }),
  setMapBounds: (bounds) =>
    set((s) => {
      const a = s.mapBounds;
      if (a === bounds) return s;
      if (a && bounds && a.minX === bounds.minX && a.minY === bounds.minY && a.maxX === bounds.maxX && a.maxY === bounds.maxY) return s;
      return { mapBounds: bounds };
    }),
  setMapPath: (path) =>
    set((s) => {
      const sido = path.sido ?? null;
      const sigungu = sido ? path.sigungu ?? null : null; // 시도 없이 시군만 있을 수 없다
      return s.mapPath.sido === sido && s.mapPath.sigungu === sigungu ? s : { mapPath: { sido, sigungu } };
    }),

  toggleStatus: (level) =>
    set((s) => ({
      statusFilter: s.statusFilter.includes(level)
        ? s.statusFilter.filter((l) => l !== level)
        : [...s.statusFilter, level],
    })),
  toggleMapLevel: (level) =>
    set((s) => {
      const on = s.mapLevels.includes(level);
      const next = on ? s.mapLevels.filter((l) => l !== level) : [...s.mapLevels, level];
      return { mapLevels: MAP_SHOW_ORDER.filter((l) => next.includes(l)) }; // 늘 정해진 순서로
    }),
  setSearch: (search) => set({ search }),
  toggleFavorite: (siteId) => {
    const on = !useSelection.getState().favorites.includes(siteId);
    set((s) => ({ favorites: on ? [...s.favorites, siteId] : s.favorites.filter((id) => id !== siteId) }));
    favoriteSync.onChange?.(siteId, on);
  },
  setFavorites: (ids) => set({ favorites: [...new Set(ids)] }),
  applyFavorite: (siteId, on) =>
    set((s) => ({
      favorites: on ? (s.favorites.includes(siteId) ? s.favorites : [...s.favorites, siteId]) : s.favorites.filter((id) => id !== siteId),
    })),
  setFavoritesOnly: (favoritesOnly) => set({ favoritesOnly }),
  setFavoriteNotice: (favoriteNotice) => set({ favoriteNotice }),
}));

// ── 파생값(저장하지 않고 계산한다) ─────────────────────────────────────────
/** 에이전트 계약의 selectedStackId: "{site_id}:{굴뚝번호}". 굴뚝까지 골랐을 때만 있다 */
export function selectedStackKey(s: Pick<SelectionData, "selectedSiteId" | "selectedStackCode">): string | null {
  return s.selectedSiteId && s.selectedStackCode ? `${s.selectedSiteId}:${s.selectedStackCode}` : null;
}

export function mapLevel(s: Pick<SelectionData, "mapPath">): MapLevel {
  if (s.mapPath.sigungu) return "sigungu";
  if (s.mapPath.sido) return "sido";
  return "nation";
}
