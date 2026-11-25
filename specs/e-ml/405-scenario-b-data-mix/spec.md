# Feature Specification: 405 대만 CEMS·국내 실측·합성 데이터 혼합

**관련 이슈** [Issue #58](https://github.com/SungChul23/smokestack-guard/issues/58) · **상태** 기존 구현과 남은 검증을 재정리

## User Scenarios & Testing

### US1 대만 CEMS·국내 실측·합성 데이터 혼합 (P1)

세 출처를 계약에 맞춰 Train에 결합하고 국내 실측으로 검증·테스트한다.

**인수 조건** 세 출처는 Train에만 결합되고 Validation/Test의 합성·대만 행은 0건이다. 시간 경계와 출처별 건수를 추적할 수 있다.

## Requirements

- **FR-001** 공통 입력·Feature·Label은 [402](../402-ml-ready-data-contract/spec.md)를 계승한다. `data_source`는 추적용이며 Feature에서 제외한다.
- **FR-002** 국내 실측 `ktms_ml_ready` 5488575191367819703, 합성 `ktms_synth_ml_ready` 6619206033361917612를 고정한다. 합성은 Train 전용이다.
- **FR-003** 대만 Train [2023-11-01, 2025-11-01) Asia/Taipei. 국내 Asia/Seoul 기준 Train [2026-10-30, 11-11), Validation [11-11, 11-14), Test [11-14, 11-16 23:00). Train·Validation의 끝 직전 60분은 제외한다.

## Success Criteria

- **SC-001** 세 출처는 Train에만 결합되고 Validation/Test의 합성·대만 행은 0건이다. 시간 경계와 출처별 건수를 추적할 수 있다.

구현 근거와 보류 사항은 [plan.md](plan.md), 작업 상태는 [tasks.md](tasks.md)를 참조한다.
