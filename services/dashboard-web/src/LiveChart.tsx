// 첫 화면 오른쪽의 "살아 있는" 예시 그래프 (013). 실제 데이터가 아니라 흐름을 보여 주는 연출이다.
// 값이 오르다 주의선(90%)을 넘으면 AI 사전 경고가 뜨고, 기준(100%)을 넘으면 사이렌이 울린 뒤
// 대응(감소)으로 내려가는 과정을 반복한다. 점선은 최근 기울기로 그린 "예측" 구간이다.
import { useEffect, useRef, useState } from "react";

const N = 36; // 화면에 보이는 칸 수 (30분 × 36 = 18시간)
const W = 360;
const H = 190;
const PAD_X = 8;
const PAD_Y = 10;
const Y_MIN = 60; // 아래를 얕게: 초록 구간이 깊게 내려가지 않게
const Y_MAX = 114;
const TICK_MS = 380;
const FORECAST = 5;

type Phase = "rise" | "alarm" | "recover";
export type Level = "ok" | "warn" | "alarm";

const yOf = (v: number) => H - PAD_Y - ((v - Y_MIN) / (Y_MAX - Y_MIN)) * (H - PAD_Y * 2);
const xOf = (i: number) => PAD_X + (i / (N - 1 + FORECAST)) * (W - PAD_X * 2);
const clamp = (v: number) => Math.max(Y_MIN + 2, Math.min(Y_MAX - 2, v));

function seed(): number[] {
  const out: number[] = [];
  let v = 70;
  for (let i = 0; i < N; i++) {
    v = clamp(v + 0.4 + (Math.random() - 0.5) * 2.4); // 끝이 약 85% → 첫 빨강까지 약 3초
    out.push(v);
  }
  return out;
}

function slope(series: number[]): number {
  const k = 6;
  const tail = series.slice(-k);
  return (tail[tail.length - 1] - tail[0]) / (k - 1);
}

export function levelOf(v: number): Level {
  return v >= 100 ? "alarm" : v >= 90 ? "warn" : "ok";
}

export default function LiveChart({ onLevel }: { onLevel?: (level: Level, value: number, eta: number | null) => void }) {
  const [series, setSeries] = useState<number[]>(seed);
  const phase = useRef<Phase>("rise");
  const hold = useRef(0);
  // 값 갱신은 내용이라 "움직임 줄이기" 설정에서도 계속한다(번쩍임만 CSS에서 끈다)
  useEffect(() => {
    const id = window.setInterval(() => {
      setSeries((prev) => {
        const last = prev[prev.length - 1];
        let next: number;
        if (phase.current === "rise") {
          next = last + 2.6 + (Math.random() - 0.4) * 2.8; // 칸당 약 2.8 ↑ → 78%에서 빨강까지 약 4초
          if (next >= 104) {
            phase.current = "alarm";
            hold.current = 11; // 사이렌·마스코트가 보일 시간 (약 4초)
          }
        } else if (phase.current === "alarm") {
          next = last + (Math.random() - 0.5) * 2.4;
          if (--hold.current <= 0) phase.current = "recover";
        } else {
          next = last - 4.2 + (Math.random() - 0.5) * 2.4;
          if (next <= 78) phase.current = "rise";
        }
        return [...prev.slice(1), clamp(next)];
      });
    }, TICK_MS);
    return () => window.clearInterval(id);
  }, []);

  const last = series[series.length - 1];
  const s = slope(series);
  const forecast = Array.from({ length: FORECAST }, (_, i) => clamp(last + s * (i + 1)));
  const steps = last < 100 && s > 0.3 ? Math.ceil((100 - last) / s) : null; // 몇 칸(30분) 뒤 100%
  const eta = steps !== null && steps <= 8 ? steps : null; // 4시간 안일 때만 알린다

  const level = levelOf(last);
  useEffect(() => {
    onLevel?.(level, last, eta);
  }, [level, last, eta, onLevel]);

  const line = series.map((v, i) => `${i ? "L" : "M"}${xOf(i).toFixed(1)},${yOf(v).toFixed(1)}`).join(" ");
  const area = `${line} L${xOf(N - 1).toFixed(1)},${H - PAD_Y} L${PAD_X},${H - PAD_Y} Z`;
  const fc = [last, ...forecast].map((v, i) => `${i ? "L" : "M"}${xOf(N - 1 + i).toFixed(1)},${yOf(v).toFixed(1)}`).join(" ");
  const color = level === "alarm" ? "#ef5a43" : level === "warn" ? "#f0a14a" : "#3fbf93";

  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="기준 대비 비율이 오르다 주의선과 기준선을 넘고 다시 내려가는 예시 그래프">
      <defs>
        <linearGradient id="lc-fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.38" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
        <linearGradient id="lc-alarm-zone" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#ef5a43" stopOpacity="0.22" />
          <stop offset="100%" stopColor="#ef5a43" stopOpacity="0.04" />
        </linearGradient>
      </defs>

      <rect x={PAD_X} y={PAD_Y} width={W - PAD_X * 2} height={yOf(100) - PAD_Y} fill="url(#lc-alarm-zone)" className="lc-zone" />
      <rect x={xOf(N - 1)} y={PAD_Y} width={W - PAD_X - xOf(N - 1)} height={H - PAD_Y * 2} fill="rgba(255,255,255,0.03)" />
      <text x={xOf(N - 1) + 4} y={H - PAD_Y - 4} fontSize="9" fill="#7f9690">AI 예측</text>

      {[70, 80].map((g) => (
        <line key={g} x1={PAD_X} x2={W - PAD_X} y1={yOf(g)} y2={yOf(g)} stroke="var(--chart-grid)" strokeWidth="1" />
      ))}
      <line x1={PAD_X} x2={W - PAD_X} y1={yOf(100)} y2={yOf(100)} stroke="#ef5a43" strokeWidth="1.5" strokeDasharray="5 4" />
      <text x={PAD_X + 2} y={yOf(100) - 5} fontSize="10" fill="#f08a78">배출허용기준 100%</text>
      <line x1={PAD_X} x2={W - PAD_X} y1={yOf(90)} y2={yOf(90)} stroke="#f0a14a" strokeWidth="1" strokeDasharray="2 4" />
      <text x={PAD_X + 2} y={yOf(90) + 12} fontSize="10" fill="#f0b46e">주의 90%</text>

      <path d={area} fill="url(#lc-fill)" className="lc-area" />
      <path d={line} fill="none" stroke={color} strokeWidth="2.2" strokeLinejoin="round" className="lc-line" />
      <path d={fc} fill="none" stroke={color} strokeWidth="1.8" strokeDasharray="3 4" opacity="0.75" />

      <circle cx={xOf(N - 1)} cy={yOf(last)} r="10" fill={color} className="lc-ping" />
      <circle cx={xOf(N - 1)} cy={yOf(last)} r="4.5" fill={color} stroke="#0a110f" strokeWidth="1.5" />
    </svg>
  );
}
