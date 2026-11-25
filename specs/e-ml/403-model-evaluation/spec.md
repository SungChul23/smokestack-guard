# Feature Specification: 403 모델 평가·임계값·Event Recall

**관련 이슈** [Issue #20](https://github.com/SungChul23/smokestack-guard/issues/20) · **상태** 기존 구현과 남은 검증을 재정리

## User Scenarios & Testing

### US1 모델 평가·임계값·Event Recall (P1)

동일한 평가 단위에서 분류·회귀 성능과 경보 부담을 비교한다.

**인수 조건** Test에서 임계값을 재선정하지 않으며, 사건 비교는 동일 사건·관측 가능 시점과 경보 묶음 규칙으로 재현 가능하다.

## Requirements

- **FR-001** 분류는 Precision·Recall·F1·F2·AP 및 TP/FP/FN/TN을 기록한다. AP는 PR 곡선 요약 지표로 표기한다.
- **FR-002** Validation에서 F2 최대 임계값을 선택한다. 동점은 높은 Recall, 낮은 임계값 순이다. 확률 ≥ 임계값을 경보로 처리하고 Test에 고정 적용한다.
- **FR-003** 회귀는 MAE·RMSE(%p)를 기록한다. XGBoost와 RF는 동일 물질·동일 평가 행에서 비교한다.
- **FR-004** Event Recall을 보고할 때 실제 진입 사건, 평가 가능 사건과 탐지 사건의 분모·분자를 밝힌다. 행 Recall과 사건 Recall을 분리한다.

## Success Criteria

- **SC-001** Test에서 임계값을 재선정하지 않으며, 사건 비교는 동일 사건·관측 가능 시점과 경보 묶음 규칙으로 재현 가능하다.

구현 근거와 보류 사항은 [plan.md](plan.md), 작업 상태는 [tasks.md](tasks.md)를 참조한다.
