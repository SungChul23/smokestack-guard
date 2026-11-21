// 상태 단계 표시. 색만으로 단계를 가리지 않도록 단계마다 모양이 다르다(위험과 초과는 색이 비슷하다).
// 정상 ○, 주의 ●, 경고 ▲, 위험 ◆, 초과 ■(느낌표). 뜻은 옆의 글자(라벨)가 전하고 이 표시는 장식이다.
import type { LevelKey } from "../logic/status";

/** 단계 표시에 쓰는 종류. 공백은 측정값이 없는 것(단계가 아니다) */
export type MarkKey = LevelKey | "gap";
import styles from "./LevelMark.module.css";

export default function LevelMark({ level, size = 14 }: { level: MarkKey; size?: number }) {
  return (
    <svg
      className={styles.mark}
      data-level={level}
      width={size}
      height={size}
      viewBox="0 0 16 16"
      aria-hidden="true"
      focusable="false"
    >
      {level === "gap" && <path d="M3 8h10" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />}
      {level === "ok" && <circle cx="8" cy="8" r="5.2" fill="none" stroke="currentColor" strokeWidth="2" />}
      {level === "caution" && <circle cx="8" cy="8" r="5.6" fill="currentColor" />}
      {level === "warn" && <path d="M8 1.8 15 14H1z" fill="currentColor" />}
      {level === "risk" && <path d="M8 1 15 8 8 15 1 8z" fill="currentColor" />}
      {level === "exceed" && (
        <>
          <rect x="1.5" y="1.5" width="13" height="13" rx="2.5" fill="currentColor" />
          <path d="M8 4.6v4.4M8 11.2v.4" stroke="var(--bg)" strokeWidth="1.8" strokeLinecap="round" />
        </>
      )}
    </svg>
  );
}
