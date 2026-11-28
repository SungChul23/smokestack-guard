// 로그인 전 첫 화면 (013). 버튼을 누르면 Cognito 화면을 건너뛰고 바로 Google로 간다.
// 오른쪽 그래프는 연출용 예시다(실제 데이터 아님). D가 디자인을 맞춰 바꿔도 된다.
import { useCallback, useEffect, useState } from "react";
import LiveChart, { type Level } from "./LiveChart";
import "./landing.css";

const LEVEL_TEXT: Record<Level, string> = { ok: "정상", warn: "주의", alarm: "기준 초과" };

type Theme = "dark" | "light";
const THEME_KEY = "tms-theme"; // 화면 전체에서 같이 쓸 수 있게 이름을 고정한다

function readTheme(): Theme {
  try {
    return window.localStorage.getItem(THEME_KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

function useKstClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return now.toLocaleTimeString("en-GB", { timeZone: "Asia/Seoul", hourCycle: "h23" });
}

export default function Landing({ onLogin }: { onLogin: () => void }) {
  const [busy, setBusy] = useState(false);
  const [level, setLevel] = useState<Level>("ok");
  const [value, setValue] = useState(0);
  const [eta, setEta] = useState<number | null>(null);
  const clock = useKstClock();
  const [theme, setTheme] = useState<Theme>(readTheme);
  const toggleTheme = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    try {
      window.localStorage.setItem(THEME_KEY, next);
    } catch {
      // 저장이 막혀도 이번 화면에서는 바뀐다
    }
  };

  const onLevel = useCallback((l: Level, v: number, e: number | null) => {
    setLevel(l);
    setValue(v);
    setEta(e);
  }, []);

  return (
    <div className={`landing level-${level}${theme === "light" ? " theme-light" : ""}`}>
      <div className="siren-bar" aria-hidden="true" />

      <header className="landing-top">
        <StackMark />
        <span>smokestack-guard</span>
        <span className="live-pill" aria-label={`실시간, 한국 시각 ${clock}`}>
          <i className="live-dot" />
          <b>LIVE</b>
          <span className="live-clock">{clock}</span>
          <span className="live-tz">KST</span>
        </span>
        <button
          className="theme-toggle"
          onClick={toggleTheme}
          aria-label={theme === "dark" ? "라이트 모드로 바꾸기" : "다크 모드로 바꾸기"}
          title={theme === "dark" ? "라이트 모드" : "다크 모드"}
        >
          {theme === "dark" ? <SunIcon /> : <MoonIcon />}
        </button>
      </header>

      <main className="landing-main">
        <section className="hero">
          <span className="landing-eyebrow reveal" style={{ ["--d" as string]: "0ms" }}>
            <Beacon /> 굴뚝 TMS 모니터링 · AI 사전 경고
          </span>
          <h1 className="reveal" style={{ ["--d" as string]: "80ms" }}>
            굴뚝 배출을 30분마다 보고,
            <br />
            <em className="heartbeat">넘기 전에</em> 알립니다
          </h1>
          <p className="landing-lead reveal" style={{ ["--d" as string]: "160ms" }}>
            전국 굴뚝자동측정기기(TMS)의 질소산화물·황산화물 측정값을 지도와 시계열로 보여 주고,
            배출허용기준에 다가가는 굴뚝을 미리 알려 줍니다. 궁금한 점은 에이전트에게 물어보세요.
          </p>
          <ul className="landing-facts reveal" style={{ ["--d" as string]: "240ms" }}>
            <li><strong>2,925</strong>굴뚝</li>
            <li><strong>30분</strong>측정 주기</li>
            <li><strong>NOx · SOx</strong>배출허용기준 대비</li>
          </ul>

          <div className="reveal" style={{ ["--d" as string]: "320ms" }}>
            <button
              className="google-btn"
              disabled={busy}
              onClick={() => {
                setBusy(true);
                onLogin();
              }}
            >
              <GoogleG />
              {busy ? "Google로 이동 중…" : "Google 계정으로 로그인"}
              <span className="btn-arrow" aria-hidden="true">→</span>
            </button>
            <p className="landing-note">처음 로그인하면 초대 코드를 한 번 입력합니다.</p>
          </div>
        </section>

        <aside className={`preview reveal level-${level}`} style={{ ["--d" as string]: "200ms" }} aria-label="실시간 모니터링 예시">
          <div className="preview-head">
            <div>
              <span className="preview-title">
                <span className="card-live"><i className="live-dot" />LIVE</span>
                NOx · 기준 대비 %
              </span>
              <span className="preview-sub">예시 굴뚝 A-03 · 연출용</span>
            </div>
            <div className="preview-value">
              <span className={`state-chip ${level}`}>
                {level === "alarm" && <Beacon />}
                {LEVEL_TEXT[level]}
              </span>
              <strong>{value.toFixed(1)}<small>%</small></strong>
            </div>
          </div>

          <div className="preview-chart">
            <LiveChart onLevel={onLevel} />
          </div>

          <div className={`alert-strip ${level}`} role="status" aria-live="polite">
            {level === "ok" && <>정상 범위 · {eta ? `현재 추세면 약 ${eta * 30}분 뒤 기준 도달` : "30분마다 새 측정값 반영"}</>}
            {level === "warn" && (
              <>
                <b>AI 사전 경고</b> 주의 구간 진입 · {eta ? `약 ${eta * 30}분 뒤 기준 초과 예상` : "기준에 근접"}
              </>
            )}
            {level === "alarm" && (
              <>
                <b>기준 초과</b> 담당자에게 알림 발송 · 대응 중
              </>
            )}
          </div>

          {/* 기준을 넘으면 마스코트가 카드 아래에서 튀어나와 경고한다. 주의 단계에서는 살짝 고개만 내민다 */}
          <div className={`mascot ${level}`} aria-hidden="true">
            <div className="mascot-bubble">
              {level === "alarm" ? "삐용삐용! 기준 초과!" : "어, 올라간다…"}
            </div>
            <img src="/mascot.png" alt="" width={133} height={150} />
          </div>
        </aside>
      </main>

      <section className="features" aria-label="주요 기능">
        <Feature title="전국 굴뚝 지도" icon={<MapIcon />} delay={0}>
          사업장별 굴뚝의 최근 측정값과 상태(정상·가동중지·미수신)를 지도에서 한눈에 봅니다.
        </Feature>
        <Feature title="AI 사전 경고" icon={<BellIcon />} delay={90}>
          규칙과 모델이 기준 초과 가능성을 미리 판단해, 넘기 전에 대응할 시간을 줍니다.
        </Feature>
        <Feature title="에이전트에게 질문" icon={<ChatIcon />} delay={180}>
          "어제 가장 높았던 굴뚝은?", "이 그래프는 왜 비었지?" 같은 질문에 근거와 함께 답합니다.
        </Feature>
      </section>

      <footer className="landing-foot">
        굴뚝 TMS 데이터 파이프라인 및 AI 사전 경고 시스템 · 측정 자료 출처: 한국환경공단 CleanSYS 공개 API
      </footer>
    </div>
  );
}

function Feature({ title, icon, delay, children }: { title: string; icon: React.ReactNode; delay: number; children: React.ReactNode }) {
  return (
    <div className="feature reveal" style={{ ["--d" as string]: `${400 + delay}ms` }}>
      <div className="feature-icon">{icon}</div>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}

function Beacon() {
  return (
    <span className="beacon" aria-hidden="true">
      <span className="beacon-light" />
      <span className="beacon-base" />
    </span>
  );
}

function StackMark() {
  return (
    <svg className="stack-mark" width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
      <path className="smoke s1" d="M9 8c-1-2 0-4 2-4" />
      <path className="smoke s2" d="M15 6c-1-2 0-4 2-4" />
      <path d="M6 26V13l4-2v15M12 26V9l4-2v19M18 26V15l4-2v13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M4 26h20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function GoogleG() {
  return (
    <svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" aria-hidden="true">
      <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
    </svg>
  );
}

function MapIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" aria-hidden="true">
      <path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14" />
    </svg>
  );
}

function BellIcon() {
  return (
    <svg className="bell" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <path d="M6 16V11a6 6 0 1 1 12 0v5l2 2H4l2-2zM10 21h4" />
    </svg>
  );
}

function ChatIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 5h16v11H9l-5 4V5z" />
      <path d="M8 10h8M8 13h5" strokeLinecap="round" />
    </svg>
  );
}
