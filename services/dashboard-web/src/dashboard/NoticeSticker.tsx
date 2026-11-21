// 공지 스티커(옛 웹의 공지 티커): 내가 즐겨찾기한 사업장이 경고 이상일 때 맨 위에 붙는다. X로 닫고, 새 공지가 생기면 다시 나온다.
import { useState } from "react";
import { labelOf } from "../logic/status";
import { formatPct } from "./TrendChart";
import LevelMark from "./LevelMark";
import { readDismissed, visibleNotices, writeDismissed, type Notice } from "./notices";
import styles from "./NoticeSticker.module.css";

export default function NoticeSticker({ items, onPick }: { items: readonly Notice[]; onPick: (n: Notice) => void }) {
  const [dismissed, setDismissed] = useState<string[]>(() => readDismissed());
  const shown = visibleNotices(items, dismissed);
  if (shown.length === 0) return null;
  const close = () => {
    const next = [...new Set([...dismissed, ...shown.map((i) => i.key)])];
    writeDismissed(next);
    setDismissed(next);
  };
  return (
    <section className={styles.sticker} aria-label="내 즐겨찾기 알림">
      <strong className={styles.title}>★ 내 즐겨찾기</strong>
      <ul className={styles.list}>
        {shown.map((it) => (
          <li key={it.key}>
            <button
              type="button"
              className={styles.chip}
              data-level={it.level}
              aria-label={`${labelOf(it.level)}: ${it.name} 굴뚝 ${it.stackCode}, 기준 대비 ${formatPct(it.ratio)}. 누르면 이 사업장을 선택합니다`}
              onClick={() => onPick(it)}
            >
              <LevelMark level={it.level} size={14} />
              <span className={styles.name}>{it.name}</span>
              <span className={styles.ratio}>{formatPct(it.ratio)}</span>
            </button>
          </li>
        ))}
      </ul>
      <button type="button" className={styles.close} aria-label="즐겨찾기 알림 닫기" onClick={close}>
        ×
      </button>
    </section>
  );
}
