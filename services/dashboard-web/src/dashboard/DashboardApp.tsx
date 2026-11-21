// 관제 화면 진입점. 데이터를 읽어 지도·목록·차트·지표 카드에 나눠 준다. 테마 공급자는 main.tsx(루트)에 있다.
import { useEffect, useMemo, useRef, useState } from "react";
import { allSiteStates, countByLevel, formatSlot } from "../data/model";
import { makeLoader, useDashboardData, usesApi, type DashboardData } from "../data/useDay";
import { useFavoritesSync } from "../data/useFavorites";
import MapPanel from "../map/MapPanel";
import { useSelection } from "../state/selection";
import AlertList from "./AlertList";
import ChartStylePanel from "./ChartStylePanel";
import NoticeBanner from "./NoticeBanner";
import NoticeSticker from "./NoticeSticker";
import { buildNotices, type Notice } from "./notices";
import Shell, { type ShellProps } from "./Shell";
import TrendChart from "./TrendChart";

type Props = Pick<ShellProps, "email" | "onLogout"> & {
  /** 데이터 읽는 방법. 시험에서 가짜 데이터를 넣을 때만 쓴다. */
  load?: () => Promise<DashboardData>;
  /** 서버 API를 부를 로그인 토큰(운영) */
  accessToken?: string;
};

export default function DashboardApp({ load, accessToken, ...props }: Props) {
  // 토큰은 갱신돼도 데이터를 다시 읽지 않도록 ref로 건다
  const tokenRef = useRef(accessToken);
  tokenRef.current = accessToken;
  const loader = useMemo(() => load ?? makeLoader(() => tokenRef.current), [load]);
  const live = !load && usesApi(); // 운영: 서버 데이터
  const state = useDashboardData(loader, live); // 30분 적재 직후 새 값으로 바꾼다
  useFavoritesSync(accessToken, live); // 즐겨찾기는 Cognito sub 기준으로 서버에 저장한다
  const favoriteNotice = useSelection((s) => s.favoriteNotice);
  const [slotPick, setSlotPick] = useState<number | null>(null); // null = 최신
  const [settingsOpen, setSettingsOpen] = useState(false); // 톱니바퀴: 그래프 설정 패널
  const selectedSiteId = useSelection((s) => s.selectedSiteId);

  // 사업장을 고르면(노란 화살표가 뜨면) 바로 아래 굴뚝 그래프로 화면을 밀어 준다.
  // 해제하거나 같은 선택이면 움직이지 않는다. 그래프가 그려진 뒤(다음 프레임)에 맞춘다.
  useEffect(() => {
    if (!selectedSiteId) return;
    const id = requestAnimationFrame(() => {
      const reduced = !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      document.getElementById("trend")?.scrollIntoView?.({ behavior: reduced ? "auto" : "smooth", block: "start" });
    });
    return () => cancelAnimationFrame(id);
  }, [selectedSiteId]);

  const ready = state.status === "ready" ? state.data : null;

  // 새 값이 들어와 시점 목록이 한 칸씩 밀리면, 고른 시점이 같은 시각을 가리키도록 맞춘다(밀려 나가면 최신으로)
  const firstTime = useRef<number | null>(null);
  useEffect(() => {
    const first = ready?.day.times[0] ?? null;
    const prev = firstTime.current;
    firstTime.current = first;
    if (prev === null || first === null || prev === first) return;
    const shift = Math.round((first - prev) / (30 * 60 * 1000));
    setSlotPick((p) => (p === null || p - shift < 0 ? null : p - shift));
  }, [ready]);
  const slot = ready ? Math.min(slotPick ?? ready.day.times.length - 1, ready.day.times.length - 1) : 0;

  const states = useMemo(() => (ready ? allSiteStates(ready.sites, ready.day, slot) : []), [ready, slot]);
  const counts = useMemo(() => (ready ? countByLevel(states) : null), [ready, states]);
  const selected = ready?.sites.find((s) => s.id === selectedSiteId) ?? null;

  // 공지는 지도 시간대 슬라이더가 아니라 최신 데이터(마지막 칸)를 현재 상태로 본다.
  // 롤링 배너: 지금 초과인 사업장 전체 / 스티커: 내가 즐겨찾기한 사업장 중 경고 이상
  const favorites = useSelection((s) => s.favorites);
  const selectSite = useSelection((s) => s.selectSite);
  const rolling = useMemo(() => (ready ? buildNotices(ready.sites, ready.day, { levels: ["exceed"] }) : []), [ready]);
  const sticker = useMemo(
    () => (ready ? buildNotices(ready.sites, ready.day, { levels: ["warn", "risk", "exceed"], only: new Set(favorites) }) : []),
    [ready, favorites],
  );
  const pick = (n: Notice) => selectSite(n.siteId, n.stackCode);
  // 그래프 설정을 만져 볼 예시: 지금 초과인 사업장 중 첫 곳(없으면 첫 사업장)
  const sample = rolling[0] ?? (ready?.sites[0] ? { siteId: ready.sites[0].id, stackCode: ready.sites[0].stacks[0]?.code ?? null } : null);

  if (!ready) {
    const note = state.status === "unavailable" ? `데이터 연결 전 (${state.reason})` : "데이터를 불러오는 중…";
    // 준비된 화면과 같은 구조로 둔다(데이터가 들어올 때 Shell이 새로 만들어지지 않게)
    return (
      <>
        {null}
        {null}
        <Shell {...props} map={<p style={{ color: "var(--muted)" }}>{note}</p>} list={<p style={{ color: "var(--muted)" }}>{note}</p>} />
      </>
    );
  }

  const times = ready.day.times;
  const notice = favoriteNotice && (
    <p role="status" style={{ position: "fixed", left: "50%", bottom: 24, transform: "translateX(-50%)", zIndex: 95, margin: 0, padding: "10px 16px", borderRadius: 10, background: "var(--panel)", color: "var(--ink)", border: "1px solid var(--lv-warn)", fontSize: 15 }}>
      {favoriteNotice}
    </p>
  );
  const alertCount = counts ? counts.warn + counts.risk + counts.exceed : null;
  return (
    <>
    {notice}
    <ChartStylePanel
      open={settingsOpen}
      onClose={() => setSettingsOpen(false)}
      onPickSample={sample ? () => selectSite(sample.siteId, sample.stackCode) : undefined}
    />
    <Shell
      {...props}
      onOpenSettings={() => setSettingsOpen((v) => !v)}
      settingsOpen={settingsOpen}
      alertCount={alertCount}
      asOf={formatSlot(times[slot])}
      counts={counts}
      notices={
        rolling.length || sticker.length ? (
          <div style={{ display: "grid", gap: 10, marginBottom: 14 }}>
            <NoticeBanner items={rolling} onPick={pick} />
            <NoticeSticker items={sticker} onPick={pick} />
          </div>
        ) : undefined
      }
      map={
        <MapPanel
          states={states}
          geo={ready.geo}
          times={times}
          slot={slot}
          onSlot={setSlotPick}
        />
      }
      list={<AlertList states={states} />}
      trend={selected ? <TrendChart site={selected} day={ready.day} /> : undefined}
    />
    </>
  );
}
