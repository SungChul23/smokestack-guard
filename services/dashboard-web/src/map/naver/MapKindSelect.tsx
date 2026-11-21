// 지도 종류 선택: 관제 지도(Canvas) / 네이버 일반 / 네이버 위성. 위쪽 막대 안에 한 줄로 들어간다.
import { MAP_MODES, type MapMode } from "./mode";
import styles from "./NaverMap.module.css";

interface Props {
  mode: MapMode;
  /** 네이버 SDK를 읽는 중 */
  busy: boolean;
  onChange: (mode: MapMode) => void;
}

export default function MapKindSelect({ mode, busy, onChange }: Props) {
  return (
    <div className={styles.kinds} role="group" aria-label="지도 종류">
      {MAP_MODES.map((m) => (
        <button
          key={m.key}
          type="button"
          className={styles.kind}
          aria-pressed={mode === m.key}
          aria-label={m.aria}
          title={m.title}
          disabled={busy}
          onClick={() => onChange(m.key)}
        >
          {m.label}
        </button>
      ))}
    </div>
  );
}
