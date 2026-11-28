// 관제 화면의 공통 틀: 왼쪽 레일 · 머리 · 본문 · 푸터. 본문 내용은 단계별로 채운다(지도·목록·차트).
import type { ReactNode } from "react";
import AgentDock from "../agent/AgentDock";
import { ALERT_LEVELS, thresholdText } from "../logic/status";
import { useTheme } from "../theme/theme";
import { AlertIcon, GearIcon, LogoutIcon, MoonIcon, OverviewIcon, StackMark, SunIcon, TrendIcon } from "./icons";
import LevelMark from "./LevelMark";
import styles from "./Shell.module.css";

export interface ShellProps {
  email?: string;
  onLogout: () => void;
  /** 경고 이상 굴뚝 수(레일 배지). 데이터가 붙기 전에는 없음. */
  alertCount?: number | null;
  /** 화면 기준 시각(표시용 문자열). 데이터가 붙기 전에는 없음. */
  asOf?: string | null;
  /** 단계별 사업장 수. 데이터가 붙기 전에는 없음(— 로 표시). */
  counts?: Record<"caution" | "warn" | "risk" | "exceed", number> | null;
  /** 각 자리에 들어갈 내용. 없으면 "준비 중". */
  map?: ReactNode;
  list?: ReactNode;
  trend?: ReactNode;
  /** 맨 윗줄 공지(롤링 배너·스티커). 없으면 아무것도 그리지 않는다. */
  notices?: ReactNode;
  /** 톱니바퀴(그래프 설정) 버튼. 주지 않으면 버튼을 그리지 않는다 */
  onOpenSettings?: () => void;
  settingsOpen?: boolean;
}

export default function Shell({ email, onLogout, alertCount = null, asOf = null, counts = null, map, list, trend, notices, onOpenSettings, settingsOpen = false }: ShellProps) {
  const { theme, toggle } = useTheme();
  const nextLabel = theme === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환";

  return (
    <div className={styles.app}>
      <a className={styles.skip} href="#main">본문으로 건너뛰기</a>

      <nav className={styles.rail} aria-label="주 메뉴">
        <div className={styles.brand}><StackMark /></div>
        <div className={styles.nav}>
          <button
            type="button"
            className={styles.railBtn}
            aria-label="통합 관제 (맨 위로)"
            title="통합 관제 · 맨 위로"
            onClick={() => window.scrollTo?.({ top: 0, behavior: "smooth" })}
          >
            <OverviewIcon />
          </button>
          <a
            className={styles.railBtn}
            href="#alerts"
            aria-label={alertCount ? `경고 목록, ${alertCount}건` : "경고 목록"}
            title="경고 목록"
          >
            <AlertIcon />
            {alertCount ? <span className={styles.badge} aria-hidden="true">{alertCount}</span> : null}
          </a>
          <a className={styles.railBtn} href="#trend" aria-label="측정 추세" title="측정 추세"><TrendIcon /></a>
        </div>
        <div className={styles.spacer} />
        {onOpenSettings && (
          <button
            type="button"
            className={styles.railBtn}
            onClick={onOpenSettings}
            aria-label="그래프 설정"
            title="그래프 설정"
            aria-haspopup="dialog"
            aria-expanded={settingsOpen}
            data-active={settingsOpen || undefined}
          >
            <GearIcon />
          </button>
        )}
        <button type="button" className={styles.railBtn} onClick={toggle} aria-label={nextLabel} title={nextLabel}>
          {theme === "dark" ? <SunIcon /> : <MoonIcon />}
        </button>
        <button type="button" className={styles.railBtn} onClick={onLogout} aria-label="로그아웃" title="로그아웃">
          <LogoutIcon />
        </button>
      </nav>

      <div className={styles.main}>
        <header className={styles.header}>
          <h1 className={styles.title}>굴뚝 통합 관제</h1>
          <span className={styles.asof} aria-live="polite">{asOf ? `기준 ${asOf}` : "기준 시각 — (데이터 연결 전)"}</span>
          {email && <span className={styles.account}>{email}</span>}
        </header>

        <main id="main" className={styles.content}>
          {notices}
          <section className={styles.cards} aria-label="단계별 굴뚝 수">
            {ALERT_LEVELS.map((lv) => (
              <div className={styles.card} key={lv.key} data-level={lv.key}>
                <div className={styles.cardLabel}>
                  <LevelMark level={lv.key} />
                  <span>{lv.label}</span>
                </div>
                <div className={styles.cardValue}>{counts ? counts[lv.key as keyof typeof counts] : "—"}</div>
                <div className={styles.cardNote}>{counts ? "사업장 · " : ""}기준 ≥{lv.min}%</div>
              </div>
            ))}
          </section>

          <div className={styles.split}>
            <section id="overview" className={`${styles.section} ${styles.mapPane}`} aria-labelledby="h-overview">
              <h2 id="h-overview" className={styles.srOnly}>지도</h2>
              {map ?? <p className={styles.placeholder}>준비 중 — 최신 1일치 흐름 지도가 들어갑니다.</p>}
            </section>
            <section id="alerts" className={`${styles.section} ${styles.listPane}`} aria-labelledby="h-alerts">
              <h2 id="h-alerts">경고 목록</h2>
              {list ?? <p className={styles.placeholder}>준비 중</p>}
            </section>
          </div>
          <section id="trend" className={styles.section} aria-labelledby="h-trend">
            <h2 id="h-trend">측정 추세</h2>
            {trend ?? <p className={styles.placeholder}>준비 중 — 굴뚝을 고르면 이력·예측 그래프가 들어갑니다.</p>}
          </section>
        </main>

        <footer className={styles.footer}>
          <span>{thresholdText()}</span>
          <span>보관 기록 · 실시간/법적 판정 아님</span>
        </footer>
      </div>

      {/* 에이전트: 열기 버튼 · 마스코트 · 창(이동·크기 조절). 채팅 연결은 ⑤단계 */}
      <AgentDock />
    </div>
  );
}
