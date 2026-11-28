// 마스코트: 에이전트 열기 버튼 자체가 화면 가장자리를 돌아다니는 캐릭터다(옛 웹의 mascot.js를 React로 옮김).
// - 누르면(거의 안 움직이면) 에이전트 창을 연다. 끌면 잡아 옮기고, 놓으면 떨어져 바닥에 착지한다.
// - 창이 열려 있는 동안은 숨고(visible=false), 닫으면 우하단에서 다시 나타나 돌아다닌다.
// - 움직임 줄이기 설정이면 제자리에 두고 클릭만 받는다. 탭이 숨으면 멈추고 돌아오면 이어서 움직인다.
// 이동 계산은 mascotEngine.ts(순수 로직). 이 파일은 화면 표시와 입력만 맡는다.
// 위치는 React 상태가 아니라 DOM 스타일을 직접 바꾼다(매 프레임 React를 다시 그리지 않는다).
import { useEffect, useRef } from "react";
import * as E from "./mascotEngine";
import styles from "./Mascot.module.css";
import { REDUCED_QUERY, useMediaQuery } from "./useMediaQuery";

export const MASCOT_SIZE = 76;

interface Props {
  /** 보일지 여부(켜져 있고, 창이 닫혀 있고, 좁은 화면이 아닐 때) */
  visible: boolean;
  onOpen: () => void;
  size?: number;
  /** 시험에서 난수를 고정할 때만 쓴다 */
  rng?: E.Rng;
}

const envOf = (size: number): E.Env => ({
  w: document.documentElement.clientWidth || window.innerWidth,
  h: document.documentElement.clientHeight || window.innerHeight,
  size,
});

export default function Mascot({ visible, onOpen, size = MASCOT_SIZE, rng = Math.random }: Props) {
  const reduced = useMediaQuery(REDUCED_QUERY);
  const btnRef = useRef<HTMLButtonElement>(null);
  const bodyRef = useRef<HTMLSpanElement>(null);
  const stateRef = useRef<E.MascotState | null>(null);
  const rafRef = useRef(0);
  const lastRef = useRef<number | null>(null);
  const pointerRef = useRef<number | null>(null);
  const reducedRef = useRef(reduced);
  const visibleRef = useRef(visible);
  const lastMoveRef = useRef("");
  const lastBodyRef = useRef("");
  const lastModeRef = useRef("");
  const onOpenRef = useRef(onOpen);
  reducedRef.current = reduced;
  visibleRef.current = visible;
  onOpenRef.current = onOpen;

  const render = () => {
    const btn = btnRef.current, body = bodyRef.current, st = stateRef.current;
    if (!btn || !body || !st) return;
    const move = `translate3d(${st.x.toFixed(1)}px,${st.y.toFixed(1)}px,0)`;
    if (move !== lastMoveRef.current) { btn.style.transform = move; lastMoveRef.current = move; }
    const b = `rotate(${st.rot.toFixed(1)}deg) scaleX(${E.facing(st)})`;
    if (b !== lastBodyRef.current) { body.style.transform = b; lastBodyRef.current = b; }
    if (st.mode !== lastModeRef.current) { btn.dataset.mode = st.mode; lastModeRef.current = st.mode; }
  };

  const frame = (now: number) => {
    rafRef.current = 0;
    const st = stateRef.current;
    if (!st || !visibleRef.current || document.hidden || reducedRef.current) return;
    const dt = lastRef.current === null ? 0 : (now - lastRef.current) / 1000;
    lastRef.current = now;
    E.step(st, dt, envOf(size), rng);
    render();
    rafRef.current = requestAnimationFrame(frame);
  };
  const startLoop = () => {
    if (!rafRef.current && visibleRef.current && !document.hidden && !reducedRef.current) {
      lastRef.current = null;
      rafRef.current = requestAnimationFrame(frame);
    }
  };
  const stopLoop = () => {
    if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = 0; }
    lastRef.current = null;
  };

  // 보이게 되면 우하단(런처가 있던 자리)에서 다시 나타난다. 안 보이게 되면 멈추고 잡고 있던 것도 놓는다.
  useEffect(() => {
    if (!visible) {
      stopLoop();
      pointerRef.current = null;
      if (stateRef.current?.press) E.cancel(stateRef.current);
      return;
    }
    const env = envOf(size);
    if (!stateRef.current) stateRef.current = E.create(env, rng);
    lastMoveRef.current = ""; lastBodyRef.current = ""; lastModeRef.current = "";
    E.respawn(stateRef.current, env);
    render();
    startLoop();
    return stopLoop;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  // 움직임 줄이기가 바뀌면: 켜지면 멈추고 제자리로, 꺼지면 다시 움직인다
  useEffect(() => {
    if (!visible || !stateRef.current) return;
    if (reduced) { stopLoop(); E.respawn(stateRef.current, envOf(size)); render(); } else startLoop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reduced]);

  // 창 크기 변화·탭 숨김
  useEffect(() => {
    const onResize = () => {
      if (!visibleRef.current || !stateRef.current) return;
      E.reflow(stateRef.current, envOf(size));
      render();
    };
    const onVisibility = () => { if (document.hidden) stopLoop(); else startLoop(); };
    window.addEventListener("resize", onResize);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("resize", onResize);
      document.removeEventListener("visibilitychange", onVisibility);
      stopLoop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!visible) return null;

  const pt = (e: React.PointerEvent) => ({ x: e.clientX, y: e.clientY });

  const onDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    if (pointerRef.current !== null || !stateRef.current) return;
    pointerRef.current = e.pointerId;
    try { e.currentTarget.setPointerCapture?.(e.pointerId); } catch { /* 지원하지 않으면 그대로 진행 */ }
    if (reducedRef.current) return; // 움직임 줄이기: 끌지 않고 클릭만 받는다
    E.press(stateRef.current, pt(e), e.timeStamp);
    e.preventDefault();
  };
  const onMove = (e: React.PointerEvent<HTMLButtonElement>) => {
    const st = stateRef.current;
    if (e.pointerId !== pointerRef.current || reducedRef.current || !st || !st.press) return;
    E.dragTo(st, pt(e), e.timeStamp, envOf(size));
    if (st.drag?.moved) e.currentTarget.classList.add(styles.dragging);
    render();
  };
  const onUp = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (e.pointerId !== pointerRef.current) return;
    const id = pointerRef.current;
    pointerRef.current = null;
    e.currentTarget.classList.remove(styles.dragging);
    try { e.currentTarget.releasePointerCapture?.(id); } catch { /* 이미 놓임 */ }
    if (reducedRef.current) { onOpenRef.current(); return; }
    const st = stateRef.current;
    const result = st?.press ? E.release(st, e.timeStamp, envOf(size)) : "drop";
    render();
    if (result === "click") onOpenRef.current();
    else startLoop(); // 놓으면 낙하 → 착지는 루프가 계산한다
  };
  const onCancel = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (pointerRef.current === null || (e.pointerId !== undefined && e.pointerId !== pointerRef.current)) return;
    pointerRef.current = null;
    e.currentTarget.classList.remove(styles.dragging);
    if (stateRef.current?.press) E.cancel(stateRef.current);
    render();
    startLoop();
  };

  return (
    <div className={styles.layer}>
      <button
        ref={btnRef}
        type="button"
        className={styles.mascot}
        style={{ ["--mascot-size" as string]: `${size}px` }}
        aria-label="에이전트 열기"
        aria-controls="agent-window"
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onCancel}
        onLostPointerCapture={onCancel}
        onContextMenu={(e) => { if (pointerRef.current !== null) e.preventDefault(); }}
        onDragStart={(e) => e.preventDefault()}
        onClick={(e) => { if (e.detail === 0) onOpenRef.current(); }} // 키보드·보조기기 활성화
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpenRef.current(); } }}
      >
        <span ref={bodyRef} className={styles.body}>
          <img src="/mascot.png" alt="" draggable={false} />
        </span>
      </button>
    </div>
  );
}
