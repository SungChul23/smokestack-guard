// 기본값을 바꾸기 전의 그래프 모양(2026-11-21 이전). 그래프를 그리는 다른 시험들이 기본값과 상관없이 같은 모양을 보도록 기준선으로 쓴다.
import type { ChartStyle } from "../state/chartStyle";

export const LEGACY_CHART_STYLE: ChartStyle = {
  lineWidth: 2.8, smooth: false, lineGlow: 0, areaOn: true, areaOpacity: 0.45,
  gapLineWidth: 2, gapLineOpacity: 0.7, gapFillOpacity: 0.2,
  gridOn: true, gridOpacity: 1, levelLinesOn: true, levelLineOpacity: 0.7, levelLinesDashed: true,
  zoneOpacity: 0.07, innerRadius: 8, innerOpacity: 1, crosshairOn: true, dotR: 6, dotGlow: 0,
  zoneLabelSize: 16, zoneLabelGlow: 0, levelLabelSize: 16, levelLabelGlow: 0, axisSize: 16, axisGlow: 0,
  labelsActiveOnly: false, pulseOn: false, pulseScale: 1.09, pulseSpeed: 1.25, pulseGlow: 8, pulseFast: true,
  noxColor: null, soxColor: null, areaColor: null, gapLineColor: null, gridColor: null, innerColor: null,
  zoneColor: null, zoneLabelColor: null, textColor: null, crosshairColor: null, dotStrokeColor: null,
  levelCautionColor: null, levelWarnColor: null, levelRiskColor: null, levelExceedColor: null,
};
