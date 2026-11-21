// 경고 목록. 두 가지 모드다(결정 2026-11-20, D):
//  - 검색어가 없을 때: 지금 지도에 보이는 사업장 중 주의 이상만(지도 화면 안에 있고, 지도에서 켜 둔 상태인 것). 사람이 지도와 비교해 알기 쉽다.
//  - 검색어가 있을 때: 지도와 상관없이 전국에서 찾는다(정상·공백 사업장도 찾는다). 골라 보면 지도가 그 사업장으로 이동한다.
// 즐겨찾기가 위로, 그다음 단계 높은 순·비율 높은 순. 보이는 줄만 그린다(가상 스크롤).
import { useMemo, useRef, useState } from "react";
import type { SiteState } from "../data/model";
import { ALERT_LEVELS, labelOf, type LevelKey } from "../logic/status";
import { project, rankOf } from "../map/geometry";
import { showKeyOf } from "../map/mapFilter";
import { useSelection, type MapBounds, type MapShowKey } from "../state/selection";
import styles from "./AlertList.module.css";
import LevelMark from "./LevelMark";
import { formatPct } from "./TrendChart";

const ROW = 72;
const OVERSCAN = 4;

export interface ListOptions {
  /** 목록 자체의 단계 필터(비어 있으면 모두) */
  statuses: LevelKey[];
  search: string;
  favorites: string[];
  /** 지도에 지금 보이는 범위(월드 좌표). 검색어가 없을 때만 쓴다. null이면 거르지 않는다(지도가 아직 없음) */
  bounds: MapBounds | null;
  /** 지도에서 켜 둔 상태(칩). 검색어가 없을 때만 쓴다. null이면 거르지 않는다 */
  mapLevels: readonly MapShowKey[] | null;
  /** 즐겨찾기 사업장만(내 사업장 목록): 정상·공백도 포함하고 지도 범위·지도 상태 칩과 상관없이 전국에서 모은다 */
  favoritesOnly?: boolean;
}

/** 사업장이 지도 범위 안에 있는지 */
export function inBounds(s: SiteState, b: MapBounds): boolean {
  const [x, y] = project(s.site.lon, s.site.lat);
  return x >= b.minX && x <= b.maxX && y >= b.minY && y <= b.maxY;
}

/** 목록에 보일 사업장을 고른다(순수 함수). 검색어가 없으면 지도에 보이는 경고만, 있으면 전국 검색 */
export function listAlerts(states: SiteState[], opts: ListOptions): SiteState[] {
  const q = opts.search.trim().toLowerCase();
  const fav = new Set(opts.favorites);
  const shown = opts.mapLevels ? new Set<string>(opts.mapLevels) : null;
  const out = states.filter((s) => {
    if (opts.favoritesOnly && !fav.has(s.site.id)) return false;
    if (opts.statuses.length && !(s.level && opts.statuses.includes(s.level))) return false;
    if (opts.favoritesOnly && !q) return true; // 내 사업장은 상태와 위치에 상관없이 모두 보인다(검색어가 있으면 그 안에서 찾는다)
    if (q) { // 전국 검색: 지도 범위·지도 상태 칩과 상관없이 이름·주소·코드로 찾는다
      return `${s.site.name} ${s.site.address} ${s.site.id}`.toLowerCase().includes(q);
    }
    if (!s.level || s.level === "ok") return false; // 경고 목록은 주의 이상만
    if (shown && !shown.has(showKeyOf(s))) return false; // 지도에서 꺼 둔 상태는 지도에 없으니 목록에도 없다
    if (opts.bounds && !inBounds(s, opts.bounds)) return false; // 지도 화면 밖
    return true;
  });
  return out.sort((a, b) => {
    const fa = fav.has(a.site.id) ? 1 : 0, fb = fav.has(b.site.id) ? 1 : 0;
    if (fa !== fb) return fb - fa;
    return rankOf(b.level) - rankOf(a.level) || (b.ratio ?? 0) - (a.ratio ?? 0);
  });
}

export default function AlertList({ states }: { states: SiteState[] }) {
  const mapBounds = useSelection((s) => s.mapBounds);
  const mapLevels = useSelection((s) => s.mapLevels);
  const statuses = useSelection((s) => s.statusFilter);
  const search = useSelection((s) => s.search);
  const favorites = useSelection((s) => s.favorites);
  const selectedSiteId = useSelection((s) => s.selectedSiteId);
  const selectSite = useSelection((s) => s.selectSite);
  const clearSelection = useSelection((s) => s.clearSelection);
  const toggleStatus = useSelection((s) => s.toggleStatus);
  const setSearch = useSelection((s) => s.setSearch);
  const toggleFavorite = useSelection((s) => s.toggleFavorite);
  const favoritesOnly = useSelection((s) => s.favoritesOnly);
  const setFavoritesOnly = useSelection((s) => s.setFavoritesOnly);

  const searching = search.trim() !== "";
  const rows = useMemo(
    () => listAlerts(states, { statuses, search, favorites, bounds: mapBounds, mapLevels, favoritesOnly }),
    [states, statuses, search, favorites, mapBounds, mapLevels, favoritesOnly],
  );

  const boxRef = useRef<HTMLDivElement>(null);
  const [top, setTop] = useState(0);
  const height = boxRef.current?.clientHeight || 420;
  const first = Math.max(0, Math.floor(top / ROW) - OVERSCAN);
  const last = Math.min(rows.length, Math.ceil((top + height) / ROW) + OVERSCAN);
  const fav = new Set(favorites);

  return (
    <div className={styles.wrap}>
      <input
        className={styles.search}
        type="search"
        placeholder="사업장명·주소·코드 검색 (전국)"
        aria-label="경고 목록 검색"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <div className={styles.filters} role="group" aria-label="단계 필터">
        <button type="button" className={styles.filter} aria-pressed={favoritesOnly} onClick={() => setFavoritesOnly(!favoritesOnly)} aria-label="즐겨찾기만 보기" title="즐겨찾기한 사업장만 지도와 목록에 보입니다">
          ★
        </button>
        {ALERT_LEVELS.map((lv) => (
          <button
            key={lv.key}
            type="button"
            className={styles.filter}
            aria-pressed={statuses.includes(lv.key)}
            onClick={() => toggleStatus(lv.key)}
          >
            <LevelMark level={lv.key} size={14} /> {lv.label}
          </button>
        ))}
      </div>
      <div className={styles.count} aria-live="polite">
        {rows.length}곳 · {favoritesOnly ? (searching ? "즐겨찾기 안에서 검색" : "내 즐겨찾기") : searching ? "전국 검색 결과" : "지금 지도에 보이는 경고"}
      </div>
      {rows.length === 0 ? (
        <p className={styles.empty}>
          {favoritesOnly
            ? (searching ? "즐겨찾기 안에 검색 결과가 없습니다." : "즐겨찾기한 사업장이 없습니다. 목록이나 그래프 머리의 ☆를 눌러 추가하세요.")
            : searching ? "검색 결과가 없습니다." : "지금 지도에 보이는 경고가 없습니다. 지도를 움직이거나 사업장명으로 검색해 보세요."}
        </p>
      ) : (
        <div ref={boxRef} className={styles.scroll} onScroll={(e) => setTop(e.currentTarget.scrollTop)} role="list" aria-label="경고 목록">
          <div style={{ height: rows.length * ROW, position: "relative" }}>
            {rows.slice(first, last).map((s, i) => {
              const idx = first + i;
              const picked = s.site.id === selectedSiteId;
              const level = s.level ?? "gap"; // 측정값이 없으면 공백
              return (
                <div
                  key={s.site.id}
                  role="listitem"
                  className={styles.row}
                  data-picked={picked || undefined}
                  style={{ top: idx * ROW, height: ROW }}
                >
                  <button
                    type="button"
                    className={styles.main}
                    onClick={() => (picked ? clearSelection() : selectSite(s.site.id, s.worstStack))}
                    aria-current={picked ? "true" : undefined}
                  >
                    <span className={styles.level}>
                      <LevelMark level={level} />
                      <span>{s.level ? labelOf(s.level) : "공백"}</span>
                    </span>
                    <span className={styles.name}>{s.site.name}</span>
                    <span className={styles.addr}>{s.site.address}</span>
                  </button>
                  <span className={styles.ratio}>{s.ratio === null ? "—" : formatPct(s.ratio)}</span>
                  <button
                    type="button"
                    className={styles.star}
                    aria-pressed={fav.has(s.site.id)}
                    aria-label={`${s.site.name} 즐겨찾기`}
                    onClick={() => toggleFavorite(s.site.id)}
                  >
                    {fav.has(s.site.id) ? "★" : "☆"}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
