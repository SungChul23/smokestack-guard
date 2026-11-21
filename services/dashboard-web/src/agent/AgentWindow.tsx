// 에이전트 창(옛 웹의 agent-frame.js·agent-frame-extras.js를 React로 옮기고 확장).
// - 자유 이동: 머리(빈 곳)나 왼쪽 위 손잡이를 끌어 어디로든 옮긴다. 방향키로 조금씩, 더블클릭·Home으로 원래 자리.
// - 자유 크기 조절: 가장자리 4곳 + 모서리 4곳을 끌어 폭·높이를 바꾼다(옛 웹은 좌우 폭만 가능했다). 방향키로 미세 조절, 가장자리 더블클릭은 그 방향만 기본 크기로.
// - 위치·크기·모드는 이 브라우저에만 저장한다(localStorage). 계산은 frameGeometry.ts(순수 로직).
// - 사이드(기본)/전체 모드, Esc는 전체 → 사이드 → 닫기. 폭 640px 이하에서는 전체 시트(이동·크기 조절 없음).
// - 모델·서버에는 아직 연결하지 않는다. 입력한 말은 화면에만 남고 어디로도 전송되지 않는다(⑤단계에서 /agent/chat 연결).
import { useEffect, useRef, useState } from "react";
import * as G from "./frameGeometry";
import { readMode, readRect, writeMode, writeRect, type FrameMode } from "./prefs";
import { WIDE_QUERY, useMediaQuery } from "./useMediaQuery";
import styles from "./AgentWindow.module.css";

const STARTERS = ["선택한 굴뚝의 어제 NOx 평균은?", "오늘 초과한 굴뚝을 알려줘", "기준을 넘으면 어떤 절차가 진행돼?"];
const STEP = 16, BIG_STEP = 64;

const vp = (): G.Viewport => ({
  w: document.documentElement.clientWidth || window.innerWidth,
  h: document.documentElement.clientHeight || window.innerHeight,
});

interface Msg { id: number; who: "user" | "agent"; text: string }

interface Props {
  onClose: () => void;
  mascotOn: boolean;
  onMascotChange: (on: boolean) => void;
}

const GripIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="6" r="1.7" /><circle cx="15" cy="6" r="1.7" /><circle cx="9" cy="12" r="1.7" /><circle cx="15" cy="12" r="1.7" /><circle cx="9" cy="18" r="1.7" /><circle cx="15" cy="18" r="1.7" /></svg>
);

export default function AgentWindow({ onClose, mascotOn, onMascotChange }: Props) {
  const wide = useMediaQuery(WIDE_QUERY);
  const [mode, setModeState] = useState<FrameMode>(() => readMode());
  const [rect, setRectState] = useState<G.Rect | null>(() => readRect(vp()));
  const [dragging, setDragging] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const rectRef = useRef(rect);
  rectRef.current = rect;
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const active = wide && mode === "side"; // 이동·크기 조절이 켜지는 조건
  const activeRef = useRef(active);
  activeRef.current = active;
  const cleanupRef = useRef<(() => void) | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const idRef = useRef(0);
  const timers = useRef<number[]>([]);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const setRect = (next: G.Rect | null) => {
    rectRef.current = next;
    setRectState(next);
  };
  const commit = (next: G.Rect) => { setRect(next); writeRect(next); };
  const reset = () => { setRect(null); writeRect(null); };
  const setMode = (m: FrameMode) => { setModeState(m); writeMode(m); };

  // ── 끌기(이동·크기 조절) ─────────────────────────────────────
  // 끄는 동안의 움직임·놓기는 window에서 받는다(포인터 캡처가 풀려도 끊기지 않게)
  const begin = (e: React.PointerEvent<HTMLElement>, kind: "move" | "size", edge?: G.Edge) => {
    if (!activeRef.current || e.button !== 0) return;
    e.preventDefault();
    const el = e.currentTarget, id = e.pointerId, sx = e.clientX, sy = e.clientY;
    const start = rectRef.current ?? G.defaultRect(vp()); // 기본 위치는 CSS와 같은 값이다
    try { el.setPointerCapture?.(id); } catch { /* 지원하지 않아도 window 리스너로 진행 */ }
    setDragging(true);
    const move = (ev: PointerEvent) => {
      if (ev.pointerId !== id) return;
      const dx = ev.clientX - sx, dy = ev.clientY - sy;
      setRect(kind === "move" ? G.moveRect(start, dx, dy, vp()) : G.resizeRect(start, edge as G.Edge, dx, dy, vp()));
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", finish);
      cleanupRef.current = null;
    };
    const finish = (ev: PointerEvent) => {
      if (ev.pointerId !== undefined && ev.pointerId !== id) return;
      stop();
      try { el.releasePointerCapture?.(id); } catch { /* 이미 놓임 */ }
      setDragging(false);
      if (rectRef.current) writeRect(rectRef.current); // 움직였을 때만 저장한다
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", finish);
    window.addEventListener("pointercancel", finish);
    cleanupRef.current = stop;
  };

  const onGripKey = (e: React.KeyboardEvent) => {
    if (!active) return;
    if (e.key === "Home") { e.preventDefault(); reset(); return; }
    if (!e.key.startsWith("Arrow")) return;
    e.preventDefault();
    commit(G.nudge(rectRef.current ?? G.defaultRect(vp()), e.key, e.shiftKey ? BIG_STEP : STEP, vp()));
  };
  const onEdgeKey = (e: React.KeyboardEvent, edge: G.Edge) => {
    if (!active || !e.key.startsWith("Arrow")) return;
    e.preventDefault();
    commit(G.resizeByKey(rectRef.current ?? G.defaultRect(vp()), edge, e.key, e.shiftKey ? BIG_STEP : STEP, vp()));
  };

  // ── 환경 변화·정리 ───────────────────────────────────────────
  useEffect(() => {
    const onResize = () => { if (rectRef.current) commit(G.clampRect(rectRef.current, vp())); };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (modeRef.current === "full") setMode("side"); else onCloseRef.current();
    };
    document.addEventListener("keydown", onKey);
    inputRef.current?.focus({ preventScroll: true });
    return () => {
      document.removeEventListener("keydown", onKey);
      cleanupRef.current?.();
      for (const t of timers.current) window.clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [messages]);

  // ── 대화(아직 모델에 연결하지 않는다) ─────────────────────────
  const grow = () => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    const h = Math.min(el.scrollHeight, 140);
    el.style.height = `${h}px`;
    el.style.overflowY = el.scrollHeight > 140 ? "auto" : "hidden";
  };
  const submit = () => {
    const value = text.trim();
    if (!value) return;
    const mine: Msg = { id: ++idRef.current, who: "user", text: value };
    setMessages((m) => [...m, mine]);
    setText("");
    requestAnimationFrame(grow);
    // 모델이 없으므로 답변을 만들지 않고, 연결 전이라는 안내만 보여 준다.
    timers.current.push(window.setTimeout(() => {
      setMessages((m) => [...m, { id: ++idRef.current, who: "agent", text: "에이전트가 아직 연결되지 않았습니다." }]);
    }, 350));
  };

  const moved = active && rect;
  const style = moved ? { left: rect.x, top: rect.y, width: rect.w, height: rect.h, right: "auto", bottom: "auto" } : undefined;
  const full = mode === "full";

  return (
    <>
      {full && <div className={styles.backdrop} aria-hidden="true" />}
      <section
        id="agent-window"
        role="dialog"
        aria-label="에이전트 대화"
        className={`${styles.panel} ${dragging ? styles.dragging : ""}`}
        data-mode={mode}
        data-moved={moved ? "1" : undefined}
        style={style}
      >
        <div
          className={styles.header}
          data-draggable={active || undefined}
          onPointerDown={(e) => { if (!(e.target as HTMLElement).closest("button, input, textarea, a")) begin(e, "move"); }}
        >
          {active && (
            <button
              type="button"
              className={`${styles.btn} ${styles.grip}`}
              aria-label="창 이동 손잡이: 끌어서 옮기거나 방향키로 움직이세요. 더블클릭하면 원래 위치로 돌아갑니다"
              title="끌어서 창 이동 · 더블클릭하면 원래 위치"
              onPointerDown={(e) => begin(e, "move")}
              onDoubleClick={reset}
              onKeyDown={onGripKey}
            >
              <GripIcon />
            </button>
          )}
          <img src="/mascot.png" alt="" width={40} height={40} className={styles.headIcon} />
          <div className={styles.title}>
            <strong>에이전트</strong>
            <span>화면 틀 미리보기 · 모델 미연결</span>
          </div>
          {/* 화면 돌아다니기(마스코트) 스위치: 한 줄을 차지하지 않도록 머리에 둔다. 설명은 마우스를 올리면 보인다 */}
          <label className={styles.roam} title="화면 돌아다니기: 켜면 창을 닫았을 때 마스코트가 화면 가장자리를 돌아다닙니다. 끄면 우하단에 고정됩니다.">
            <span className={styles.roamText}>돌아다니기</span>
            <button
              type="button"
              role="switch"
              aria-checked={mascotOn}
              aria-label="화면 돌아다니기"
              className={`${styles.switch} ${mascotOn ? styles.switchOn : ""}`}
              onClick={() => onMascotChange(!mascotOn)}
            >
              <span className={styles.thumb} />
            </button>
          </label>
          <button
            type="button"
            className={`${styles.btn} ${styles.toggle}`}
            aria-label={full ? "사이드 창으로 줄이기" : "전체 창으로 넓히기"}
            title={full ? "사이드 창으로 줄이기" : "전체 창으로 넓히기"}
            onClick={() => setMode(full ? "side" : "full")}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 17l-5-5 5-5" /><path d="M18 17l-5-5 5-5" /></svg>
          </button>
          <button type="button" className={styles.btn} aria-label="에이전트 닫기" onClick={onClose}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>

        <div ref={logRef} className={styles.log} role="log" aria-live="polite">
          <div className={styles.inner}>
            {messages.length === 0 && (
              <div className={styles.welcome}>
                <img src="/mascot.png" alt="" width={96} height={108} />
                <h3>무엇을 확인할까요?</h3>
                <p>굴뚝 이름, 물질, 기간을 말씀해 주세요.{"\n"}지금은 화면 틀만 보여 드리는 미리보기입니다.</p>
                <div className={styles.chips}>
                  {STARTERS.map((s) => (
                    <button key={s} type="button" className={styles.chip} onClick={() => { setText(s); inputRef.current?.focus(); requestAnimationFrame(grow); }}>
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m) => (
              <div key={m.id} className={`${styles.msg} ${m.who === "user" ? styles.user : `${styles.agent} ${styles.notice}`}`}>
                <p>{m.text}</p>
                {m.who === "agent" && <small>화면 틀 미리보기입니다. 입력한 내용은 어디로도 전송되지 않습니다.</small>}
              </div>
            ))}
          </div>
        </div>

        <form className={styles.composer} onSubmit={(e) => { e.preventDefault(); submit(); }}>
          <div className={styles.composerRow}>
            <label className={styles.sr} htmlFor="agent-window-input">질문 입력</label>
            <textarea
              ref={inputRef}
              id="agent-window-input"
              rows={1}
              maxLength={1000}
              placeholder="질문을 입력하세요"
              value={text}
              onChange={(e) => { setText(e.target.value); requestAnimationFrame(grow); }}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); } }}
            />
            <button type="submit" className={`${styles.btn} ${styles.send}`} aria-label="보내기">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5" /><path d="M5 12l7-7 7 7" /></svg>
            </button>
          </div>
          <p className={styles.foot}>모델이 연결되기 전이라 답변은 만들어지지 않습니다.</p>
        </form>

        {active && G.EDGES.map((edge) => {
          const side = edge.length === 1;
          return (
            <div
              key={edge}
              className={`${styles.edge} ${styles[`edge_${edge}`]}`}
              data-edge={edge}
              role={side ? "separator" : undefined}
              aria-orientation={side ? (edge === "n" || edge === "s" ? "horizontal" : "vertical") : undefined}
              aria-hidden={side ? undefined : true}
              tabIndex={side ? 0 : undefined}
              aria-label={side ? `${G.EDGE_LABEL[edge]}: 끌어서 크기 조절, 방향키로 미세 조절, 더블클릭하면 이 방향만 기본 크기` : undefined}
              title={side ? "끌어서 크기 조절" : undefined}
              onPointerDown={(e) => begin(e, "size", edge)}
              onKeyDown={(e) => onEdgeKey(e, edge)}
              onDoubleClick={() => commit(G.resetEdge(rectRef.current ?? G.defaultRect(vp()), edge, vp()))}
            />
          );
        })}
      </section>
    </>
  );
}
