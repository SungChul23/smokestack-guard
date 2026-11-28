// 글자가 깨알 같아서 안 보인다는 의견이 커서 둔 안전장치: 내 화면 스타일의 글자 크기가 다시 작아지지 않게 한다.
// (A의 첫 화면 landing.css는 대상이 아니다.)
import fs from "node:fs";
import { describe, expect, it } from "vitest";

// 시험은 프로젝트 폴더에서 실행된다(npm test). CSS 모듈 import는 시험 환경에서 원문이 아니라 클래스 이름표를 주므로 파일을 직접 읽는다.
const read = (path: string) => fs.readFileSync(path, "utf8");
const alertList = read("src/dashboard/AlertList.module.css");
const shell = read("src/dashboard/Shell.module.css");
const trend = read("src/dashboard/TrendChart.module.css");
const clock = read("src/map/MapClock.module.css");
const mapPanel = read("src/map/MapPanel.module.css");
const agentWindow = read("src/agent/AgentWindow.module.css");
const naverMap = read("src/map/naver/NaverMap.module.css");

const FILES: Record<string, string> = {
  "AlertList.module.css": alertList,
  "Shell.module.css": shell,
  "TrendChart.module.css": trend,
  "MapClock.module.css": clock,
  "MapPanel.module.css": mapPanel,
  "AgentWindow.module.css": agentWindow,
  "NaverMap.module.css": naverMap,
};
const MIN_PX = 13;

function sizes(css: string): Array<{ rule: string; px: number }> {
  const out: Array<{ rule: string; px: number }> = [];
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const px = /font-size:\s*([0-9.]+)px/.exec(m[2]);
    if (px) out.push({ rule: m[1].trim().replace(/\s+/g, " "), px: Number(px[1]) });
  }
  return out;
}

describe("글자 크기: 13px 아래로 내려가지 않는다", () => {
  for (const [name, css] of Object.entries(FILES)) {
    it(name, () => {
      const list = sizes(css);
      expect(list.length).toBeGreaterThan(0);
      const tooSmall = list.filter((s) => s.px < MIN_PX);
      expect(tooSmall, `작은 글자: ${JSON.stringify(tooSmall)}`).toEqual([]);
    });
  }

  it("차트 안 글자(눈금·기준선 이름)는 화면에서 줄어드는 것을 감안해 16 이상이다", () => {
    expect(sizes(trend).find((s) => s.rule === ".tick")?.px).toBeGreaterThanOrEqual(16);
  });

  it("지도 시계 안 숫자도 크게(15 이상)", () => {
    expect(sizes(clock).find((s) => s.rule === ".numeral")?.px).toBeGreaterThanOrEqual(15);
  });

  it("에이전트 창의 본문·입력 글자도 크다(입력 16px, 대화 16px)", () => {
    const list = sizes(agentWindow);
    expect(list.find((x) => x.rule === ".msg")?.px).toBeGreaterThanOrEqual(16);
    expect(list.find((x) => x.rule === ".composerRow textarea")?.px).toBeGreaterThanOrEqual(16);
  });

  it("물질 카드는 크다: 체크 상자 32px, 비율 글자 34px 이상", () => {
    expect(trend).toMatch(/\.cardBox \{[^}]*width: 32px/);
    expect(trend).toMatch(/\.cardNum \{[^}]*font-size: 34px/);
  });
});
