// 지도 시계: 보여 주기만 한다(조작은 지도 아래 슬라이더). 12시간 아날로그(막대 바늘, 시침·분침은 길이로 구분) + 플립 숫자판.
// 접으면 작은 버튼(시각 표시)이 된다. 시점은 30분 간격 보관본이며 예측값은 만들지 않는다.
// 지도 시각은 지도만 바꾼다(차트에서 고른 시점과 공유하지 않는다, spec 318 §7).
import { useEffect, useRef, useState } from "react";
import { hourAngle, isPm, minuteAngle, nextUnwrapped, partsOf, spinFor } from "./clockMath";
import styles from "./MapClock.module.css";

interface Props {
  times: number[];
  slot: number;
  /** 재생 중이면 바늘이 한 칸 간격(stepMs) 동안 일정한 속도로 돈다. 아니면 짧게 옮겨 간다 */
  playing?: boolean;
  stepMs?: number;
}

/**
 * 바늘의 누적 각도를 기억한다(0도를 넘을 때 거꾸로 한 바퀴 돌지 않게).
 * 같은 목표 칸이면 다시 계산하지 않는다(렌더가 여러 번 불려도 같은 값).
 */
function useHandAngles(targetIndex: number, hour: number, minute: number) {
  const ref = useRef({ index: targetIndex, hour, minute });
  if (ref.current.index !== targetIndex) {
    const spin = spinFor(ref.current.index, targetIndex);
    ref.current = {
      index: targetIndex,
      hour: nextUnwrapped(ref.current.hour, hour, spin),
      minute: nextUnwrapped(ref.current.minute, minute, spin),
    };
  }
  return ref.current;
}

/** 바늘: 끝이 둥근 선 하나. 시침은 짧고 굵게, 분침은 길고 가늘게(길이로 구분되므로 화살촉은 없다) */
function Hand({ angle, unwrapped, ease, length, width, hand }: {
  angle: number; unwrapped: number; ease: string; length: number; width: number; hand: "hour" | "minute";
}) {
  return (
    <g
      style={{ transform: `rotate(${unwrapped}deg)`, transformOrigin: "100px 100px", transition: ease }}
      data-hand={hand}
      data-angle={angle}
      className={styles.hand}
    >
      <path d={`M100 112V${100 - length}`} stroke="var(--accent)" strokeWidth={width} strokeLinecap="round" />
    </g>
  );
}

export default function MapClock({ times, slot, playing = false, stepMs = 1600 }: Props) {
  const [open, setOpen] = useState(true);
  const ms = times[slot] ?? times[0];
  // 재생 중에는 바늘이 "다음 칸"을 향해 한 칸 간격 동안 일정한 속도로 돈다. 그러면 칸이 바뀌는 순간(숫자판이 넘어가는 순간)
  // 바늘이 정확히 그 시각에 닿아 있다. 멈추면 지금 칸으로 돌아온다.
  const targetIndex = playing && slot < times.length - 1 ? slot + 1 : slot;
  const tms = times[targetIndex] ?? ms;
  const angles = useHandAngles(targetIndex, tms === undefined ? 0 : hourAngle(tms), tms === undefined ? 0 : minuteAngle(tms));
  const ease = playing ? `transform ${stepMs}ms linear` : "transform 0.25s ease-out";
  const isLatest = slot === times.length - 1;
  if (ms === undefined) return null;
  const p = partsOf(ms);
  const mode = isLatest ? "최신 보관" : "지난 시각";
  const period = isPm(ms) ? "오후" : "오전";

  if (!open) {
    return (
      <button type="button" className={styles.mini} onClick={() => setOpen(true)} aria-expanded="false" aria-label="지도 시계 열기">
        <svg viewBox="0 0 40 40" width="30" height="30" aria-hidden="true">
          <circle cx="20" cy="20" r="17" fill="none" stroke="var(--accent)" strokeWidth="1.5" />
          <g transform={`rotate(${hourAngle(ms)} 20 20)`}><path d="M20 22V11" stroke="var(--accent)" strokeWidth="2.2" strokeLinecap="round" /></g>
          <g transform={`rotate(${minuteAngle(ms)} 20 20)`}><path d="M20 22V7" stroke="var(--accent)" strokeWidth="1.4" strokeLinecap="round" /></g>
          <circle cx="20" cy="20" r="2" fill="var(--accent)" />
        </svg>
        <span className={styles.miniText}>
          <strong>{p.hour}:{p.minute}</strong>
          <small>{mode}</small>
        </span>
      </button>
    );
  }

  return (
    <section className={styles.panel} aria-label="지도 시계">
      <div className={styles.head}>
        <div>
          <h3>지도 시간</h3>
          <strong className={styles.mode}>{mode}</strong>
        </div>
        <button type="button" className={styles.fold} onClick={() => setOpen(false)} aria-label="지도 시계 접기">×</button>
      </div>

      <svg
        className={styles.dial}
        viewBox="0 0 200 200"
        role="img"
        aria-label={`지도 시각 ${period} ${Number(p.hour) % 12 || 12}시 ${p.minute}분`}
      >
        <circle className={styles.face} cx="100" cy="100" r="94" />
        {Array.from({ length: 12 }, (_, i) => {
          if (i % 3 === 0) return null; // 12·3·6·9시 자리는 눈금 대신 로마 숫자가 선다
          const a = (i * 30 * Math.PI) / 180;
          return (
            <line key={i} className={styles.tick}
              x1={100 + Math.sin(a) * 80} y1={100 - Math.cos(a) * 80}
              x2={100 + Math.sin(a) * 88} y2={100 - Math.cos(a) * 88} />
          );
        })}
        {/* 12·3·6·9는 눈금 자리(원 중심에서 같은 방향)에 로마 숫자로 서고, 은은한 빛을 넣는다. 3·9는 세로 중심이 원의 중심 높이(100)와 같다.
            글자 세로 중심은 dy=0.35em으로 맞춘다(대문자 높이의 절반). 화면 낭독은 위의 시각 설명을 쓴다 */}
        <text className={styles.roman} x="100" y="22" dy="0.35em" aria-hidden="true">XII</text>
        <text className={styles.roman} x="178" y="100" dy="0.35em" aria-hidden="true">III</text>
        <text className={styles.roman} x="100" y="178" dy="0.35em" aria-hidden="true">VI</text>
        <text className={styles.roman} x="22" y="100" dy="0.35em" aria-hidden="true">IX</text>
        <text className={styles.caption} x="100" y="140">{period} · 12H</text>
        <Hand angle={hourAngle(tms)} unwrapped={angles.hour} ease={ease} length={50} width={4.5} hand="hour" />
        <Hand angle={minuteAngle(tms)} unwrapped={angles.minute} ease={ease} length={74} width={2.8} hand="minute" />
        <circle cx="100" cy="100" r="5" fill="var(--accent)" />
      </svg>

      <div className={styles.digits} role="group" aria-label="지도 선택 날짜와 시간">
        <div className={styles.row}>
          <Flip v={p.year} u="년" /><Flip v={p.month} u="월" /><Flip v={p.day} u="일" />
        </div>
        <div className={styles.row}>
          <Flip v={p.hour} u="시" big /><span aria-hidden="true" className={styles.colon}>:</span><Flip v={p.minute} u="분" big />
          <span className={styles.tz}>KST</span>
        </div>
      </div>
      <span className={styles.tag}>보관자료 · 30분 간격</span>
    </section>
  );
}

/** 값이 바뀌면 넘어가는 플립 칸. 처음 그릴 때와 모션 감소 설정에서는 움직이지 않는다 */
function Flip({ v, u, big }: { v: string; u: string; big?: boolean }) {
  const first = useRef(true);
  useEffect(() => { first.current = false; }, []);
  const animate = !first.current;
  return (
    <span className={styles.cell}>
      <span className={big ? styles.valBig : styles.val} data-flip>
        <span key={v} className={animate ? styles.flip : undefined}>{v}</span>
      </span>
      <span className={styles.unit}>{u}</span>
    </span>
  );
}
