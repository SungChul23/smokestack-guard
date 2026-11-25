# Feature Specification: 402 ML-ready 계약·Feature·적격성 및 누수 방지

**관련 이슈** [Issue #20](https://github.com/SungChul23/smokestack-guard/issues/20) · **상태** 기존 구현과 남은 검증을 재정리

## User Scenarios & Testing

### US1 ML-ready 계약·Feature·적격성 및 누수 방지 (P1)

C파트 입력의 의미와 시간 경계를 보존해 모델별 X/y를 만든다.

**인수 조건** Feature 순서와 X/y 대응이 일치하고, 미래 또는 경계 위반 행이 없다. 입력 기간 밖 행은 오류로 드러나며 첫·끝 슬롯 관측 누락만으로 실패하지 않는다.

## Requirements

- **FR-001** 필수 35컬럼과 자료형, feature/label v1, quality_policy v2를 검증한다. NOx/SO₂ 및 feature_valid와 작업별 eligibility를 적용한다.
- **FR-002** 분류 `label_entry_60m`은 현재 <90%에서 정확한 +30분 또는 +60분에 ≥90% 진입, 회귀 `label_ratio_60m`은 정확히 +60분 기준대비율이다. 100% 초과값을 보존한다.
- **FR-003** Feature에 식별자·측정시각·원값·기준치·Label·플래그·버전·출처를 넣지 않는다. 결측 보간·슬롯 압축·미래값 참조를 금지한다.
- **FR-004** 대만 현지 시각으로 Train [2023-11-01, 2025-11-01), Validation [2025-11-01, 2026-05-01), Test [2026-05-01, 2026-11-01). 모든 굴뚝·물질에 같은 경계를 적용하고 이전 구간의 마지막 60분은 제외한다.
- **FR-005** 기준치 변경을 가로지르는 이력·Label 구간은 제외해야 한다. E에서 플래그를 소비하는 것과 변경 규칙의 종단 검증은 구분한다.

### Feature 순서 (22개)

```text
ratio_pct, headroom_pct,
ratio_lag_30m, ratio_lag_60m, ratio_lag_90m, ratio_lag_120m, ratio_lag_150m,
ratio_diff_30m, ratio_diff_60m, ratio_acceleration,
ratio_rolling_mean_1h, ratio_rolling_mean_3h, ratio_rolling_std_3h,
ratio_rolling_max_3h, ratio_range_3h, ratio_slope_3h, rise_count_3h,
hour_sin, hour_cos, month_sin, month_cos, day_of_week
```

## Success Criteria

- **SC-001** Feature 순서와 X/y 대응이 일치하고, 미래 또는 경계 위반 행이 없다. 입력 기간 밖 행은 오류로 드러나며 첫·끝 슬롯 관측 누락만으로 실패하지 않는다.

구현 근거와 보류 사항은 [plan.md](plan.md), 작업 상태는 [tasks.md](tasks.md)를 참조한다.
