# Feature Specification: 401 시나리오 A 모델 학습

**관련 이슈** [Issue #20](https://github.com/SungChul23/smokestack-guard/issues/20) · **상태** 기존 구현과 남은 검증을 재정리

## User Scenarios & Testing

### US1 시나리오 A 모델 학습 (P1)

대만 CEMS로 물질별 분류·회귀 모델을 학습하고 각 실행을 재현한다.

**인수 조건** 6개 결과물 각각에서 모델 ID, 데이터 버전, 실제 파라미터, 동일한 시간 경계, 평가·아티팩트 연결을 확인한다.

## Requirements

- **FR-001** 대만 CEMS 단독 학습. NOx는 N1-C·N1-R·RN1, SO₂는 S1-C·S1-R·RS1. `-C`는 XGBoost 분류, `-R`은 XGBoost 회귀, RN1·RS1은 Random Forest 회귀다.
- **FR-002** 각 모델은 전체 적격 Train으로 fit 1회 수행한다. Validation·Test는 학습에 전달하지 않는다.
- **FR-003** 입력·대상 Label·분할은 [402](../402-ml-ready-data-contract/spec.md), 평가는 [403](../403-model-evaluation/spec.md), 실행·저장은 [404](../404-sagemaker-artifacts/spec.md)를 따른다.

## Success Criteria

- **SC-001** 6개 결과물 각각에서 모델 ID, 데이터 버전, 실제 파라미터, 동일한 시간 경계, 평가·아티팩트 연결을 확인한다.

구현 근거와 보류 사항은 [plan.md](plan.md), 작업 상태는 [tasks.md](tasks.md)를 참조한다.

## 변경 이력

401 통합 문서의 원본은 [분리 전 spec.md](https://github.com/SungChul23/smokestack-guard/blob/4c31c393de9e33a218a2799e1ecf6b118543882b/specs/e-ml/401-scenario-a-ml-training/spec.md)에 보존되어 있다. 이전 요구사항과 작업의 새 위치는 [401 문서 이관표](README.md#문서-이관표)를 참조한다.
