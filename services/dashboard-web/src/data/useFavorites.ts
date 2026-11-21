// 즐겨찾기 서버 연결(운영만): Cognito sub 기준으로 서버(app.user_favorite)에 저장한다.
// 별표는 눌렀을 때 화면에 먼저 반영하고(낙관적), 저장이 실패하면 되돌리고 잠깐 안내한다.
import { useEffect, useRef } from "react";
import { apiGet, apiSend } from "../api";
import { favoriteSync, useSelection } from "../state/selection";

interface FavoritesResponse { targets: string[] }

const NOTICE_MS = 4000;
export const NOTICE = {
  load: "즐겨찾기를 불러오지 못했습니다. 이 화면에서만 바뀌고 저장되지 않습니다.",
  save: "즐겨찾기를 저장하지 못했습니다. 잠시 뒤 다시 눌러 주세요.",
};

export const favoritePath = (siteId: string) => `/api/favorites/${encodeURIComponent(siteId)}`;

/** enabled(운영)일 때만 서버와 맞춘다. 토큰은 갱신돼도 다시 읽지 않도록 ref로 건다 */
export function useFavoritesSync(accessToken: string | undefined, enabled: boolean) {
  const tokenRef = useRef(accessToken);
  tokenRef.current = accessToken;
  const hasToken = !!accessToken;

  useEffect(() => {
    if (!enabled || !hasToken) return;
    let alive = true;
    let timer = 0;
    const store = useSelection.getState;
    const tell = (message: string) => {
      store().setFavoriteNotice(message);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => store().setFavoriteNotice(null), NOTICE_MS);
    };

    apiGet<FavoritesResponse>(tokenRef.current!, "/api/favorites")
      .then((r) => alive && store().setFavorites(r.targets))
      .catch(() => alive && tell(NOTICE.load));

    favoriteSync.onChange = (siteId, on) => {
      const token = tokenRef.current;
      if (!token) { store().applyFavorite(siteId, !on); tell(NOTICE.save); return; }
      apiSend<FavoritesResponse>(token, favoritePath(siteId), on ? "PUT" : "DELETE").catch(() => {
        store().applyFavorite(siteId, !on); // 저장하지 못했으니 원래대로
        tell(NOTICE.save);
      });
    };
    return () => {
      alive = false;
      window.clearTimeout(timer);
      favoriteSync.onChange = undefined;
    };
  }, [enabled, hasToken]);
}
