// 그래프 설정 패널: 톱니바퀴를 누르면 오른쪽에 열린다. 바꾸는 즉시 아래 추세 그래프에 반영되고 이 브라우저에 저장된다.
// 다크·라이트 모드마다 따로 저장된다(모드를 바꾸면 그 모드의 설정이 적용된다). 값은 JSON으로 복사해 나눌 수 있다.
// 사업장을 고르지 않으면 그래프가 없으므로 "예시 사업장 열기"로 하나 고를 수 있다.
import { useEffect, useRef, useState } from "react";
import { changedCount, defaultsFor, RANGES, useActiveStyle, useChartStyle, type ChartStyle, type ColorKey } from "../state/chartStyle";
import { useThemeName, type ThemeName } from "../theme/useThemeName";
import styles from "./ChartStylePanel.module.css";

type NumKey = keyof typeof RANGES;
type BoolKey = "smooth" | "areaOn" | "gridOn" | "levelLinesOn" | "levelLinesDashed" | "crosshairOn" | "labelsActiveOnly" | "pulseOn" | "pulseFast";
const MODE_NAME: Record<ThemeName, string> = { dark: "다크", light: "라이트" };

function Slider({ id, label, k, unit = "", digits = 2 }: { id: string; label: string; k: NumKey; unit?: string; digits?: number }) {
  const { style, theme } = useActiveStyle();
  const set = useChartStyle((s) => s.set);
  const value = style[k];
  const [min, max, step] = RANGES[k];
  const changed = value !== defaultsFor(theme)[k];
  return (
    <div className={styles.row} data-changed={changed || undefined}>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        aria-valuetext={`${Number(value.toFixed(digits))}${unit}`}
        onChange={(e) => set({ [k]: Number(e.target.value) } as Partial<ChartStyle>)}
      />
      <span className={styles.value} aria-hidden="true">{Number(value.toFixed(digits))}{unit}</span>
    </div>
  );
}

function Toggle({ label, k }: { label: string; k: BoolKey }) {
  const { style, theme } = useActiveStyle();
  const set = useChartStyle((s) => s.set);
  const on = style[k];
  return (
    <label className={styles.toggle} data-changed={on !== defaultsFor(theme)[k] || undefined}>
      <input type="checkbox" checked={on} onChange={(e) => set({ [k]: e.target.checked } as Partial<ChartStyle>)} />
      <span>{label}</span>
    </label>
  );
}

/** 테마 색(CSS 변수)을 #rrggbb로 풀어 쓴다. 변수를 못 읽는 환경(시험 등)에서는 fallback */
export function resolveThemeHex(cssVar: string, fallback: string): string {
  try {
    const probe = document.createElement("span");
    probe.style.color = `var(${cssVar})`;
    probe.style.display = "none";
    document.body.appendChild(probe);
    const m = getComputedStyle(probe).color.match(/\d+(?:\.\d+)?/g);
    probe.remove();
    if (!m || m.length < 3) return fallback;
    return "#" + m.slice(0, 3).map((n) => Math.round(Number(n)).toString(16).padStart(2, "0")).join("");
  } catch {
    return fallback;
  }
}

/** 색 한 줄. cssVar는 "기본색"이 가리키는 테마 색, follow는 기본이 다른 색을 따를 때의 설명 */
function ColorPick({ label, k, cssVar, fallback, follow }: { label: string; k: ColorKey; cssVar?: string; fallback: string; follow?: string }) {
  const { style, theme } = useActiveStyle(); // 모드가 바뀌면 다시 그려서 기본색 견본도 그 모드의 색이 된다
  const set = useChartStyle((s) => s.set);
  const value = style[k];
  const base = cssVar ? resolveThemeHex(cssVar, fallback) : fallback;
  const dflt = defaultsFor(theme)[k];
  return (
    <div className={styles.row} data-changed={value !== dflt || undefined}>
      <label htmlFor={`cs-${k}`} title={follow ? `기본: ${follow}` : undefined}>{label}</label>
      <input id={`cs-${k}`} type="color" value={value ?? base} onChange={(e) => set({ [k]: e.target.value } as Partial<ChartStyle>)} />
      <button type="button" className={styles.small} disabled={value === dflt} onClick={() => set({ [k]: dflt } as Partial<ChartStyle>)}>
        기본색
      </button>
    </div>
  );
}

export default function ChartStylePanel({ open, onClose, onPickSample }: { open: boolean; onClose: () => void; onPickSample?: () => void }) {
  const theme = useThemeName();
  const other: ThemeName = theme === "dark" ? "light" : "dark";
  const { style } = useActiveStyle();
  const reset = useChartStyle((s) => s.reset);
  const replace = useChartStyle((s) => s.replace);
  const copyFrom = useChartStyle((s) => s.copyFrom);
  const [note, setNote] = useState("");
  const [paste, setPaste] = useState<string | null>(null);
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) return;
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  const n = changedCount(style, theme);
  const json = JSON.stringify(style, null, 2);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(json);
      setNote(`${MODE_NAME[theme]} 모드의 현재 값을 복사했습니다.`);
    } catch {
      setPaste(json); // 복사 권한이 없으면 글상자에 보여 준다
      setNote("복사하지 못해 아래에 보여 드립니다. 직접 복사해 주세요.");
    }
  };
  const apply = () => {
    try {
      replace(JSON.parse(paste ?? ""));
      setNote(`붙여 넣은 값을 ${MODE_NAME[theme]} 모드에 적용했습니다.`);
    } catch {
      setNote("값을 읽지 못했습니다. 복사한 JSON 그대로 붙여 넣어 주세요.");
    }
  };

  return (
    <aside ref={ref} tabIndex={-1} className={styles.panel} role="dialog" aria-modal="false" aria-label="그래프 설정">
      <header className={styles.head}>
        <div>
          <strong>그래프 설정 · {MODE_NAME[theme]} 모드</strong>
          <span>{n ? `이 모드의 기본값에서 ${n}개 바꿈` : "이 모드의 기본값 그대로"}</span>
        </div>
        <button type="button" className={styles.close} onClick={onClose} aria-label="그래프 설정 닫기">×</button>
      </header>

      <div className={styles.body}>
        <div className={styles.actions}>
          {onPickSample && <button type="button" className={styles.btn} onClick={onPickSample}>예시 사업장 열기</button>}
          <button type="button" className={styles.btn} onClick={() => document.getElementById("trend")?.scrollIntoView?.({ behavior: "smooth", block: "start" })}>그래프로 이동</button>
        </div>
        <p className={styles.hint}>
          바꾸면 바로 그래프에 반영됩니다. <strong>다크·라이트 모드는 설정이 따로</strong>라서, 모드를 바꾸면 그 모드에서 정한 값이 적용됩니다. 사업장을 고르지 않았다면 "예시 사업장 열기"를 눌러 보세요.
        </p>
        <div className={styles.actions}>
          <button type="button" className={styles.btn} onClick={() => { copyFrom(other); setNote(`${MODE_NAME[other]} 모드의 설정을 ${MODE_NAME[theme]} 모드로 복사했습니다.`); }}>
            {MODE_NAME[other]} 모드 설정 가져오기
          </button>
        </div>

        <section aria-label="선">
          <h3>선</h3>
          <Slider id="cs-lw" label="굵기" k="lineWidth" digits={1} />
          <Toggle label="부드러운 곡선" k="smooth" />
          <Slider id="cs-lg" label="빛(라이팅)" k="lineGlow" unit="px" digits={0} />
        </section>

        <section aria-label="영역 채움">
          <h3>선 아래 영역(안쪽 채움)</h3>
          <Toggle label="영역 채움" k="areaOn" />
          <Slider id="cs-ao" label="진하기" k="areaOpacity" />
          <ColorPick label="영역 색" k="areaColor" fallback="#0f7a5c" follow="물질 색" />
        </section>

        <section aria-label="공백 구간">
          <h3>값이 없는 구간(점선)</h3>
          <Slider id="cs-gw" label="점선 굵기" k="gapLineWidth" digits={1} />
          <Slider id="cs-go" label="점선 진하기" k="gapLineOpacity" />
          <Slider id="cs-gf" label="아래 칠 진하기" k="gapFillOpacity" />
          <ColorPick label="점선·칠 색" k="gapLineColor" fallback="#0f7a5c" follow="물질 색" />
        </section>

        <section aria-label="눈금과 기준선">
          <h3>눈금·기준선</h3>
          <Toggle label="안쪽 눈금선" k="gridOn" />
          <Slider id="cs-go2" label="눈금선 진하기" k="gridOpacity" />
          <Toggle label="주의·경고·위험·초과 기준선" k="levelLinesOn" />
          <Toggle label="기준선 점선(초과선 제외)" k="levelLinesDashed" />
          <Slider id="cs-lo" label="기준선 진하기" k="levelLineOpacity" />
          <Slider id="cs-zo" label="위쪽 20% 초과 영역 칠" k="zoneOpacity" digits={2} />
          <ColorPick label="눈금선 색" k="gridColor" cssVar="--stage-grid" fallback="#1a2925" />
          <ColorPick label="초과 영역 색" k="zoneColor" cssVar="--lv-exceed" fallback="#ff3b2f" />
          <ColorPick label="주의 기준선 색" k="levelCautionColor" cssVar="--lv-caution" fallback="#d9b43f" />
          <ColorPick label="경고 기준선 색" k="levelWarnColor" cssVar="--lv-warn" fallback="#f0a14a" />
          <ColorPick label="위험 기준선 색" k="levelRiskColor" cssVar="--lv-risk" fallback="#ef5a43" />
          <ColorPick label="초과 기준선 색" k="levelExceedColor" cssVar="--lv-exceed" fallback="#ff3b2f" />
        </section>

        <section aria-label="바깥 글자와 숫자">
          <h3>바깥 글자·숫자</h3>
          <h4>"기준 초과 영역(압축)" 글자</h4>
          <Slider id="cs-zs" label="크기" k="zoneLabelSize" unit="px" digits={0} />
          <Slider id="cs-zg" label="빛(라이팅)" k="zoneLabelGlow" unit="px" digits={0} />
          <ColorPick label="글자 색(영역)" k="zoneLabelColor" cssVar="--lv-exceed" fallback="#ff3b2f" follow="초과 영역 색" />
          <h4>단계 글자(초과·위험·경고·주의)</h4>
          <Slider id="cs-ls" label="크기" k="levelLabelSize" unit="px" digits={0} />
          <Slider id="cs-lg2" label="빛(라이팅)" k="levelLabelGlow" unit="px" digits={0} />
          <Toggle label="점의 단계 글자만 보이기" k="labelsActiveOnly" />
          <p className={styles.hint}>그래프에서 점을 찍으면(클릭) 그 점의 %가 속한 단계 글자 하나만 남습니다. 70% 미만이면 모두 숨습니다. 글자 색은 위 "기준선 색"을 따릅니다.</p>
          <h4>축 숫자(% · 시각)</h4>
          <Slider id="cs-as" label="크기" k="axisSize" unit="px" digits={0} />
          <Slider id="cs-ag" label="빛(라이팅)" k="axisGlow" unit="px" digits={0} />
          <ColorPick label="축 글자 색" k="textColor" cssVar="--muted" fallback="#93a49d" />
        </section>

        <section aria-label="박동">
          <h3>박동(두근두근)</h3>
          <Toggle label="박동 켜기" k="pulseOn" />
          <Slider id="cs-ps" label="부푸는 크기(배)" k="pulseScale" digits={2} />
          <Slider id="cs-pt" label="한 번 뛰는 시간" k="pulseSpeed" unit="초" digits={2} />
          <Slider id="cs-pg" label="번지는 빛" k="pulseGlow" unit="px" digits={0} />
          <Toggle label="높은 단계일수록 빠르게" k="pulseFast" />
          <p className={styles.hint}>로그인 화면의 "넘기 전에"처럼 두 번 뛰고 쉽니다. 그래프에서 점을 찍으면 그 점의 %가 속한 단계(주의·경고·위험·초과) 글자가 박동합니다. 움직임 줄이기 설정에서는 멈춥니다.</p>
        </section>

        <section aria-label="안쪽 판">
          <h3>안쪽 판(그래프 바탕)</h3>
          <Slider id="cs-ir" label="모서리 둥글기" k="innerRadius" digits={0} />
          <Slider id="cs-io" label="바탕 진하기" k="innerOpacity" />
          <ColorPick label="바탕 색" k="innerColor" cssVar="--stage-bg" fallback="#0a110f" />
        </section>

        <section aria-label="선택한 시점">
          <h3>선택한 시점</h3>
          <Toggle label="세로선" k="crosshairOn" />
          <Slider id="cs-dr" label="점 크기" k="dotR" digits={0} />
          <Slider id="cs-dg" label="점 빛(라이팅)" k="dotGlow" unit="px" digits={0} />
          <ColorPick label="세로선 색" k="crosshairColor" cssVar="--ink" fallback="#e9f1ed" />
          <ColorPick label="점 테두리 색" k="dotStrokeColor" cssVar="--bg" fallback="#0b1210" />
        </section>

        <section aria-label="색">
          <h3>물질 색(선·점·카드)</h3>
          <ColorPick label="NOx" k="noxColor" cssVar="--accent" fallback="#0f7a5c" />
          <ColorPick label="SOx" k="soxColor" cssVar="--series-2" fallback="#3a6fb5" />
          <p className={styles.hint}>색을 고르지 않은 줄은 이 모드에 맞는 테마 색을 씁니다. "기본색"을 누르면 그 줄만 이 모드의 기본값으로 돌아가고, 아래 "기본값으로 되돌리기"는 이 모드의 모든 설정을 되돌립니다.</p>
        </section>

        <section aria-label="저장과 공유">
          <h3>저장·공유</h3>
          <div className={styles.actions}>
            <button type="button" className={styles.btn} onClick={copy}>현재 값 복사(JSON)</button>
            <button type="button" className={styles.btn} onClick={() => setPaste(paste === null ? "" : null)}>값 붙여 넣기</button>
            <button type="button" className={styles.btn} onClick={() => { reset(); setNote(`${MODE_NAME[theme]} 모드를 기본값으로 되돌렸습니다.`); }} disabled={n === 0}>기본값으로 되돌리기</button>
          </div>
          {paste !== null && (
            <div className={styles.paste}>
              <textarea aria-label="그래프 설정 JSON" value={paste} onChange={(e) => setPaste(e.target.value)} rows={6} spellCheck={false} />
              <button type="button" className={styles.btn} onClick={apply}>적용</button>
            </div>
          )}
          <p className={styles.hint} role="status">{note || "설정은 이 브라우저에 모드별로 저장됩니다. 마음에 드는 값을 복사해 알려 주시면 기본값으로 반영할 수 있어요."}</p>
        </section>
      </div>
    </aside>
  );
}
