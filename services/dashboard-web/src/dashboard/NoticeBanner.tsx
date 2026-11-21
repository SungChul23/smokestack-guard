// 공지 롤링 배너: 관제 화면 맨 윗줄에 초과 사업장을 세로로 굴려 보여 준다(옛 웹 notice-banner를 옮김).
// 마우스를 올리거나 키보드로 초점을 주면 멈추고, 누르면 그 사업장을 고른다. 움직임 줄이기 설정에서는 굴리지 않고 ‹ › 로 넘긴다.
import { useEffect, useState } from "react";
import { REDUCED_QUERY, useMediaQuery } from "../agent/useMediaQuery";
import { labelOf } from "../logic/status";
import { formatPct } from "./TrendChart";
import type { Notice } from "./notices";
import styles from "./NoticeBanner.module.css";

export const ROLL_MS = 3500;
const SLIDE_MS = 450;

export default function NoticeBanner({ items, onPick }: { items: readonly Notice[]; onPick: (n: Notice) => void }) {
  const n = items.length;
  const reduced = useMediaQuery(REDUCED_QUERY);
  const rolling = n > 1 && !reduced;
  const sig = items.map((i) => i.key).join(",");
  const [index, setIndex] = useState(0); // rolling이면 복제본(n번째)까지 갈 수 있다
  const [jump, setJump] = useState(false); // 복제본에서 처음으로 돌아올 때는 움직임 없이
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    setIndex(0);
    setJump(true);
  }, [sig]);

  useEffect(() => {
    if (!rolling || paused) return;
    const t = window.setInterval(() => {
      if (document.hidden) return;
      setJump(false);
      setIndex((i) => (i >= n ? 0 : i + 1));
    }, ROLL_MS);
    return () => window.clearInterval(t);
  }, [rolling, paused, n, sig]);

  useEffect(() => {
    if (!rolling || index !== n) return;
    const t = window.setTimeout(() => {
      setJump(true);
      setIndex(0);
    }, SLIDE_MS + 30); // 복제본에 닿은 뒤 끊김 없이 처음으로
    return () => window.clearTimeout(t);
  }, [index, n, rolling]);

  if (n === 0) return null;
  const at = index % n;
  const shown = items[Math.min(at, n - 1)];
  const list = rolling ? [...items, items[0]] : [items[Math.min(index, n - 1)]];
  const step = (d: number) => setIndex((i) => (((i + d) % n) + n) % n);

  return (
    <section
      className={styles.banner}
      aria-label="초과 공지"
      style={{ ["--nb-color" as string]: `var(--lv-${shown.level})` }}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setPaused(false);
      }}
    >
      <span className={styles.tag}>공지</span>
      <div className={styles.viewport}>
        <div
          className={styles.track}
          data-jump={jump || undefined}
          style={rolling ? { transform: `translateY(calc(var(--nb-h) * ${-index}))` } : undefined}
        >
          {list.map((it, i) => {
            const clone = rolling && i === n;
            return (
              <button
                key={clone ? `${it.key}#clone` : it.key}
                type="button"
                className={styles.item}
                data-level={it.level}
                tabIndex={clone ? -1 : undefined}
                aria-hidden={clone || undefined}
                aria-label={`${labelOf(it.level)}: ${it.name} 굴뚝 ${it.stackCode}, 기준 대비 ${formatPct(it.ratio)}. 누르면 이 사업장을 선택합니다`}
                onClick={() => onPick(it)}
              >
                <span className={styles.level}>{labelOf(it.level)}</span>
                <span className={styles.text}>
                  {it.name} · 굴뚝 {it.stackCode}
                </span>
                <span className={styles.ratio}>{formatPct(it.ratio)}</span>
              </button>
            );
          })}
        </div>
      </div>
      {n > 1 && (
        <span className={styles.count} aria-hidden="true">
          {at + 1}/{n}
        </span>
      )}
      {n > 1 && reduced && (
        <>
          <button type="button" className={styles.nav} aria-label="이전 공지" onClick={() => step(-1)}>
            ‹
          </button>
          <button type="button" className={styles.nav} aria-label="다음 공지" onClick={() => step(1)}>
            ›
          </button>
        </>
      )}
    </section>
  );
}
