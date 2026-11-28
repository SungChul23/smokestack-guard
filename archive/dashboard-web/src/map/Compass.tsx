// 방위 표시(옛 웹의 지도 오른쪽 아래 십자 별을 옮김). 지도는 늘 위가 북쪽이다.
import styles from "./Compass.module.css";

export default function Compass() {
  return (
    <div className={styles.compass} role="img" aria-label="방위: 위 북 N, 오른쪽 동 E, 왼쪽 서 W, 아래 남 S">
      <span className={styles.n} aria-hidden="true">N</span>
      <span className={styles.e} aria-hidden="true">E</span>
      <span className={styles.w} aria-hidden="true">W</span>
      <span className={styles.s} aria-hidden="true">S</span>
      <svg className={styles.cross} viewBox="0 0 24 24" aria-hidden="true">
        <path className={styles.points} d="M12 1L14.5 9.5L23 12L14.5 14.5L12 23L9.5 14.5L1 12L9.5 9.5Z" />
        <path className={styles.north} d="M12 1L14.5 9.5L12 12L9.5 9.5Z" />
      </svg>
    </div>
  );
}
