// 에이전트 열기 버튼 · 마스코트 · 창을 묶는다.
// - 창이 닫혀 있으면: 마스코트가 켜져 있고 화면이 넓으면(540px 초과) 마스코트가 돌아다니고, 아니면 우하단 고정 버튼이다.
// - 창이 열려 있으면 둘 다 숨고, 닫으면 다시 나타난다(마스코트는 우하단에서).
// - 마스코트는 기본 꺼짐(옛 웹과 같음). 창 안의 "화면 돌아다니기" 스위치나 ?mascot=on으로 켠다. ?mascot=off가 가장 우선이다.
import { useEffect, useRef, useState } from "react";
import AgentWindow from "./AgentWindow";
import Mascot from "./Mascot";
import { mascotWanted, writeMascot } from "./prefs";
import { NARROW_QUERY, useMediaQuery } from "./useMediaQuery";
import styles from "./AgentDock.module.css";

export default function AgentDock() {
  const [open, setOpen] = useState(false);
  const [mascotOn, setMascotOn] = useState(() => mascotWanted());
  const narrow = useMediaQuery(NARROW_QUERY);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);

  const roaming = mascotOn && !narrow; // 마스코트가 돌아다니는 상태(좁은 화면에서는 고정 버튼)
  const showLauncher = !open && !roaming;

  // 창을 닫으면 열기 버튼으로 초점을 돌려준다(마스코트일 때는 마스코트가 다시 나타난다)
  useEffect(() => {
    if (wasOpen.current && !open) launcherRef.current?.focus({ preventScroll: true });
    wasOpen.current = open;
  }, [open]);

  const changeMascot = (on: boolean) => {
    writeMascot(on);
    setMascotOn(mascotWanted()); // 주소의 ?mascot= 이 있으면 그쪽이 우선이다
  };

  return (
    <>
      {showLauncher && (
        <button
          ref={launcherRef}
          type="button"
          className={styles.launcher}
          aria-label="에이전트 열기"
          aria-controls="agent-window"
          aria-expanded={false}
          onClick={() => setOpen(true)}
        >
          <img src="/mascot.png" alt="" width={82} height={92} />
        </button>
      )}
      <Mascot visible={roaming && !open} onOpen={() => setOpen(true)} />
      {open && <AgentWindow onClose={() => setOpen(false)} mascotOn={mascotOn} onMascotChange={changeMascot} />}
    </>
  );
}
