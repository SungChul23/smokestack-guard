// 로그인 전 첫 화면 (013). 버튼을 누르면 Cognito 화면을 건너뛰고 바로 Google로 간다.
// 오른쪽 그래프는 장식용 예시 그림이다(실제 데이터 아님). D가 디자인을 맞춰 바꿔도 된다.
import { useState } from "react";
import "./landing.css";

// 30분 측정값 48칸 모양의 예시 곡선 (기준 대비 %)
const SERIES = [52, 55, 54, 58, 61, 60, 63, 66, 64, 68, 71, 70, 74, 77, 75, 79, 83, 81, 84, 88, 86, 91, 94, 92];
const W = 360;
const H = 170;
const PAD = 8;
const yOf = (pct: number) => H - PAD - ((pct - 40) / (110 - 40)) * (H - PAD * 2);
const xOf = (i: number) => PAD + (i / (SERIES.length - 1)) * (W - PAD * 2);
const LINE = SERIES.map((v, i) => `${i ? "L" : "M"}${xOf(i).toFixed(1)},${yOf(v).toFixed(1)}`).join(" ");
const AREA = `${LINE} L${xOf(SERIES.length - 1).toFixed(1)},${H - PAD} L${PAD},${H - PAD} Z`;
const LAST = SERIES.length - 1;

export default function Landing({ onLogin }: { onLogin: () => void }) {
  const [busy, setBusy] = useState(false);

  return (
    <div className="landing">
      <header className="landing-top">
        <StackMark />
        <span>smokestack-guard</span>
      </header>

      <main className="landing-main">
        <section>
          <span className="landing-eyebrow">굴뚝 TMS 모니터링 · AI 사전 경고</span>
          <h1>
            굴뚝 배출을 30분마다 보고,
            <br />
            <em>넘기 전에</em> 알립니다
          </h1>
          <p className="landing-lead">
            전국 굴뚝자동측정기기(TMS)의 질소산화물·황산화물 측정값을 지도와 시계열로 보여 주고,
            배출허용기준에 다가가는 굴뚝을 미리 알려 줍니다. 궁금한 점은 에이전트에게 물어보세요.
          </p>
          <ul className="landing-facts">
            <li><strong>2,925</strong>굴뚝</li>
            <li><strong>30분</strong>측정 주기</li>
            <li><strong>NOx · SOx</strong>배출허용기준 대비</li>
          </ul>

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
          </button>
          <p className="landing-note">처음 로그인하면 초대 코드를 한 번 입력합니다.</p>
        </section>

        <aside className="preview" aria-label="대시보드 미리보기 (예시 그림)">
          <div className="preview-head">
            <span className="preview-title">NOx · 기준 대비 %</span>
            <span className="preview-sub">최근 12시간 · 예시</span>
          </div>
          <div className="preview-chart">
            <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="기준 대비 비율이 90%를 넘어 100%에 다가가는 예시 곡선">
              <defs>
                <linearGradient id="fill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="#3fbf93" stopOpacity="0.35" />
                  <stop offset="100%" stopColor="#3fbf93" stopOpacity="0" />
                </linearGradient>
              </defs>
              {[50, 70, 90].map((g) => (
                <line key={g} x1={PAD} x2={W - PAD} y1={yOf(g)} y2={yOf(g)} stroke="var(--chart-grid)" strokeWidth="1" />
              ))}
              <line x1={PAD} x2={W - PAD} y1={yOf(100)} y2={yOf(100)} stroke="#c2412d" strokeWidth="1.5" strokeDasharray="5 4" />
              <text x={W - PAD} y={yOf(100) - 5} textAnchor="end" fontSize="10" fill="#e8806f">배출허용기준 100%</text>
              <line x1={PAD} x2={W - PAD} y1={yOf(90)} y2={yOf(90)} stroke="#d9822b" strokeWidth="1" strokeDasharray="2 4" />
              <text x={PAD + 2} y={yOf(90) - 5} fontSize="10" fill="#e3a35f">주의 90%</text>
              <path d={AREA} fill="url(#fill)" />
              <path d={LINE} fill="none" stroke="#3fbf93" strokeWidth="2.2" strokeLinejoin="round" />
              <circle cx={xOf(LAST)} cy={yOf(SERIES[LAST])} r="9" fill="#d9822b" opacity="0.25" />
              <circle cx={xOf(LAST)} cy={yOf(SERIES[LAST])} r="4" fill="#d9822b" />
            </svg>
          </div>
          <div className="preview-legend">
            <span><i className="dot" style={{ background: "#3fbf93" }} />측정값</span>
            <span><i className="dot" style={{ background: "#d9822b" }} />주의 진입</span>
            <span><i className="dot" style={{ background: "#c2412d" }} />기준 초과</span>
          </div>
        </aside>
      </main>

      <section className="features" aria-label="주요 기능">
        <Feature title="전국 굴뚝 지도" icon={<MapIcon />}>
          사업장별 굴뚝의 최근 측정값과 상태(정상·가동중지·미수신)를 지도에서 한눈에 봅니다.
        </Feature>
        <Feature title="AI 사전 경고" icon={<BellIcon />}>
          규칙과 모델이 기준 초과 가능성을 미리 판단해, 넘기 전에 대응할 시간을 줍니다.
        </Feature>
        <Feature title="에이전트에게 질문" icon={<ChatIcon />}>
          "어제 가장 높았던 굴뚝은?", "이 그래프는 왜 비었지?" 같은 질문에 근거와 함께 답합니다.
        </Feature>
      </section>

      <footer className="landing-foot">
        굴뚝 TMS 데이터 파이프라인 및 AI 사전 경고 시스템 · 측정 자료 출처: 한국환경공단 CleanSYS 공개 API
      </footer>
    </div>
  );
}

function Feature({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="feature">
      <div className="feature-icon">{icon}</div>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}

function StackMark() {
  return (
    <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
      <path d="M5 24V12l4-2v14M11 24V8l4-2v18M17 24V14l4-2v12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M13 4c1-2 3-2 4-1s3 1 4-1" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" opacity="0.6" />
      <path d="M3 24h20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
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

function MapIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" aria-hidden="true">
      <path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14" />
    </svg>
  );
}

function BellIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
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
