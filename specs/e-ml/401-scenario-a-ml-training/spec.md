# Feature Specification: E파트 시나리오 A 모델 학습·평가

**Feature Branch**: `20-e-ml-model-training`
**Created**: 2026-11-06
**Status**: Draft — 미확정 사항 확인 필요
**Input**: Issue #20 및 사용자가 확정한 시나리오 A 요구사항
**관련 이슈**: [#20](https://github.com/SungChul23/smokestack-guard/issues/20)
**담당**: E (`doeun-1202`), 부담당 D (`jaeyan42`)
**SPECIFY_FEATURE_DIRECTORY**: `specs/e-ml/401-scenario-a-ml-training`

대만 CEMS만으로 NOx·SO₂의 기준대비율과 상승 추세를 학습하여 향후 60분의 위험 진입 및 기준대비율을 예측한다. 최종 기능 범위는 실제 모델 학습·평가와 결과 보존까지 포함한다. 이번 변경은 Specify 문서 작성에 한정하며 학습·평가를 실행하지 않는다.

## User Scenarios & Testing *(mandatory)*

아래 검증 시나리오는 향후 기능의 인수 조건이며 이번 작업에서 실행하는 테스트가 아니다.

### User Story 1 - 계약에 맞는 누수 없는 학습 데이터 확보 (Priority: P1)

E 담당자는 대만 CEMS ML-ready 입력에서 물질·목표별로 유효한 행만 선택하고 시간 순서를 보존하여 정직한 모델 비교 기반을 확보한다.

**Why this priority**: 잘못된 입력이나 미래 정보 누수는 모든 성능 평가를 무효화한다.

**Independent Test**: 입력 계약, Feature 목록, 시간 분할, 제외 사유 기록만으로 학습 데이터의 적합성을 확인할 수 있다.

**Acceptance Scenarios**:

1. **Given** 승인된 35개 컬럼 계약의 입력, **When** 물질·목표별 데이터를 선택하면, **Then** NOx는 `nox`, SO₂는 `sox`이며 각 목표의 적격 행만 남는다.
2. **Given** 시간 분할 경계, 결측 슬롯 또는 기준치 변경이 있는 입력, **When** 학습 행을 구성하면, **Then** 미래 Label 누수와 기준치 변경 경계를 가로지르는 행이 제외되고 결측을 보간하거나 슬롯을 건너뛰어 연결하지 않는다.
3. **Given** 계약 또는 버전·타입 불일치, **When** 입력을 검증하면, **Then** 이를 기록하고 유효한 입력으로 취급하지 않는다.

### User Story 2 - 물질별 모델 학습 및 결과 보존 (Priority: P2)

E 담당자는 공통 학습 흐름으로 4개 모델 계열의 6개 결과물을 실제로 학습하고 입력·설정·모델 버전을 추적한다.

**Why this priority**: 코드 준비만으로는 이슈의 실제 학습 완료 목표를 충족하지 못한다.

**Independent Test**: 모델별 실행 이력과 저장된 아티팩트·버전으로 6개 학습 결과물의 존재와 출처를 확인할 수 있다.

**Acceptance Scenarios**:

1. **Given** 유효한 입력과 승인된 실행 환경, **When** 서울 리전에서 학습을 완료하면, **Then** N1-C·N1-R·S1-C·S1-R·RN1·RS1의 아티팩트와 실행 정보가 남는다.
2. **Given** 입력 미확보 또는 학습 실패, **When** 실행 상태를 보고하면, **Then** 준비·실패 상태와 실제 학습 완료 상태를 구분한다.

### User Story 3 - 같은 조건에서 성능 비교 (Priority: P3)

E 담당자는 분류의 위험 탐지와 오경보, 회귀의 오차를 확인하고 물질별 회귀 모델을 같은 조건에서 비교한다.

**Why this priority**: 비교 가능한 평가와 근거가 있어야 후속 활용 여부를 판단할 수 있다.

**Independent Test**: 고정된 평가 데이터의 예측값, 지표, 비교 조건과 ppm 환산 근거로 평가 결과를 확인할 수 있다.

**Acceptance Scenarios**:

1. **Given** 학습된 분류 모델, **When** 확정된 평가 정책으로 평가하면, **Then** PR-AUC·Recall·Precision·F1, 독립 위험 사건 탐지율 및 오경보 분석이 남는다.
2. **Given** 동일 물질의 회귀 모델, **When** 동일한 분할·평가 행·지표로 비교하면, **Then** MAE·RMSE(%p)와 비교 결과 및 기준대비율→ppm 환산 검증 결과가 남는다.

### Edge Cases

- 현재 비율이 90% 이상인 행은 위험 진입 Label의 현재 90% 미만 조건과 구분한다. 분류에는 `classification_eligible` 정책을 적용한다.
- 미래 30분·60분 슬롯 누락이나 시계열 끝부분은 다른 시점으로 대체하지 않는다. 유효성은 확정된 계약·품질 정책으로 판단한다.
- 과거 3시간부터 미래 60분까지 기준치가 바뀌는 행은 제외한다. 변경 후 전체 필요 구간에서 안정적으로 유지되는 행은 허용한다.
- 100% 초과 회귀 Target은 보존한다. 원본 ppm과 기준치는 검증·환산에만 사용한다.
- 굴뚝·물질 사이의 시계열을 연결하지 않는다. 중복 시각, 비정상 기준치, 타입 오류 처리의 상세 정책은 계약 확인 전 임의로 결정하지 않는다.
- 분할 후 유효 행 부족 또는 분류 한쪽 클래스 부재 시 건수·분포와 평가 불가 사유를 보고하고 성공적인 성능 평가로 표시하지 않는다.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 학습 입력은 대만 CEMS `tw_cems_ml_ready` 단독이어야 한다. 국내 TMS 혼합·합성 데이터, 시나리오 B 및 Serving API는 제외한다.
- **FR-002**: C파트의 ML-ready 35개 컬럼 계약과 데이터 타입, `feature_version`, `label_version`, `quality_policy_version`을 검증해야 한다. Silver·ML-ready 생성과 계약 자체는 변경하지 않고 E 학습 단계에서 필터링한다.
- **FR-003**: `item_code = 'nox'`와 `'sox'`를 분리하고, 분류는 `classification_eligible = true`, 회귀는 `regression_eligible = true`인 행을 선택해야 한다.
- **FR-004**: 학습 Feature는 다음 22개를 명시된 순서로 사용해야 한다: `ratio_pct`, `headroom_pct`, `ratio_lag_30m`, `ratio_lag_60m`, `ratio_lag_90m`, `ratio_lag_120m`, `ratio_lag_150m`, `ratio_diff_30m`, `ratio_diff_60m`, `ratio_acceleration`, `ratio_rolling_mean_1h`, `ratio_rolling_mean_3h`, `ratio_rolling_std_3h`, `ratio_rolling_max_3h`, `ratio_range_3h`, `ratio_slope_3h`, `rise_count_3h`, `hour_sin`, `hour_cos`, `month_sin`, `month_cos`, `day_of_week`. 계약에서 확인되지 않은 컬럼명은 만들지 않는다.
- **FR-005**: `measure_value`, `standard_value`, `stack_code`, `item_code`, `measured_at`, Label·적격 여부·버전 컬럼은 모델 입력 Feature에서 제외해야 한다. 식별·정렬·검증·ppm 환산 용도는 구분하여 유지한다.
- **FR-006**: 30분 시계열에서 분류 Target은 `label_entry_60m`이어야 한다. 현재 기준대비율 90% 미만에서 향후 30분 또는 60분에 90% 이상 진입하면 양성(1)이다. 회귀 Target은 정확히 60분 후 비율인 `label_ratio_60m`이며 100% 초과값을 보존해야 한다.
- **FR-007**: 다음 4개 계열·6개 결과물을 학습해야 한다.

| 계열 | 물질 | 학습 결과물 | 알고리즘·목표 |
| --- | --- | --- | --- |
| N1 | NOx | N1-C, N1-R | XGBoost 분류·회귀 |
| S1 | SO₂ | S1-C, S1-R | XGBoost 분류·회귀 |
| RN1 | NOx | RN1 | Random Forest 회귀 |
| RS1 | SO₂ | RS1 | Random Forest 회귀 |

- **FR-008**: 동일 굴뚝·동일 물질별 시계열을 보존하고 시간순 Train/Validation/Test를 사용해야 한다. 미래 60분 Label이 분할 경계를 넘어 다른 분할에 속하는 정보에 의존하지 않도록 하며, Feature는 예측 시점 이후 정보를 사용하지 않아야 한다. 전처리·모델 선택에 Test 정보를 사용해서는 안 된다.
- **FR-009**: 결측 슬롯 보간과 건너뛰기를 금지하고 과거 3시간 Feature부터 미래 60분 Label까지 기준치 변경 경계를 가로지르는 행을 제외해야 한다. 변경 후 필요한 전체 구간이 안정적인 행은 학습을 허용한다.
- **FR-010**: 모델별·분할별 유효 행 수, 제외 사유·건수와 분류 양성·음성 분포를 기록해야 한다. 물질별 XGBoost와 Random Forest 회귀는 동일한 분할·평가 조건으로 비교해야 한다.
- **FR-011**: AWS SageMaker AI의 서울 리전(`ap-northeast-2`)에서 Training Job을 실행할 수 있어야 한다. S3 ML-ready 입력, 모델별 설정, 학습 실행 진입점, 모델 아티팩트와 평가 결과 저장 위치 및 버전을 추적해야 한다. 실제 학습·평가 완료가 최종 범위이며 AWS 리소스 생성·배포는 별도 확인 대상이다.
- **FR-012**: 분류는 PR-AUC·Recall·Precision·F1, 독립 위험 사건 탐지율과 오경보를 평가하고 회귀는 MAE·RMSE(%p)를 평가해야 한다. 기준대비율→ppm 환산의 근거와 검증 결과를 남겨야 한다.
- **FR-013**: 규칙과 모델을 비교하는 경우 같은 데이터 기간·평가 지표·기준선을 사용하고 그 조건을 기록해야 한다. 데이터·모델 버전, 분할 조건, 실행 설정, 평가 근거와 학습·실행 방법 문서를 보존해야 한다.
- **FR-014**: 다음 미확정 사항은 사용자 확인 전 고정하지 않아야 한다.
  - **Q1**: [NEEDS CLARIFICATION: 승인된 35개 컬럼 계약의 위치·버전과 세 가지 버전 허용값, 실제 ML-ready 입력 경로·기간·시각 의미 및 품질 정책은 무엇인가?]
  - **Q2**: [NEEDS CLARIFICATION: Train/Validation/Test 기간 또는 비율과 공통 시간 경계 적용 방식, 분할 경계 행 제외 정책은 무엇인가?]
  - **Q3**: [NEEDS CLARIFICATION: 분류 판정 임계값·독립 위험 사건·오경보 정의, 비교 기준선 및 성능 합격 기준은 무엇인가?]

### Key Entities

- **ML-ready 입력 계약**: 35개 컬럼과 타입·Feature/Label/품질 정책 버전. 원본 측정값·기준치와 모델 입력 Feature를 구분한다.
- **학습 행·시간 분할**: 굴뚝·물질·측정 시각, 현재와 과거 Feature, 미래 Label, 적격·제외 사유 및 Train/Validation/Test 소속.
- **모델 결과물**: 6개 모델의 식별자, 입력·설정·버전, 실행 상태와 아티팩트.
- **평가 기록**: 데이터 기간·평가 행·지표·기준선, 예측값, 사건·오경보 분석 및 환산 근거.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 4개 모델 계열의 6개 결과물 모두 실제 학습과 평가를 완료하고 각 결과물의 아티팩트·버전·입력·실행 정보를 추적할 수 있다.
- **SC-002**: 모든 학습 결과물에서 선택된 Feature와 계약 검증 결과를 확인할 수 있으며 금지 컬럼의 모델 입력 포함 건수는 0건이다.
- **SC-003**: 모든 분할에서 미래 Label 누수 및 기준치 변경 경계 위반으로 채택된 행은 0건이고, 모델별·분할별 유효/제외 건수와 분류 클래스 분포를 확인할 수 있다.
- **SC-004**: 분류 결과물 2개와 회귀 결과물 4개 모두 해당 지표·평가 근거를 보존하며 물질별 회귀 비교 2건과 ppm 환산 검증 결과를 확인할 수 있다.
- **SC-005**: 담당자가 실행 방법 문서로 각 결과물의 입력·분할·설정·저장 위치를 확인할 수 있다. 예측 성능 합격 여부는 Q3 확정 후 판단하며 임의 수치로 합격을 선언하지 않는다.

## Assumptions

- 요구사항 근거는 Issue #20과 이번 사용자의 확정 사항이며 미확정 설계에 추가 가정을 적용하지 않는다.
- 승인된 C파트 계약과 실제 ML-ready 확보에 의존한다. 다른 파트 코드나 계약 문서를 이번 작업에서 탐색·수정하지 않았다.
- Issue의 `m_time`은 15분 측정 구간 시작 시각이라는 사실을 유지한다. 30분 ML-ready `measured_at`과의 대응·집계 해석은 계약 확인 없이 결정하지 않는다.
- 학습 인스턴스·하이퍼파라미터·저장 경로·권한·비용과 버전 관리 방식의 구체값은 미확정이다. 이번 Specify에서 선택하거나 AWS 작업을 실행하지 않는다.
- 원칙상 비밀값은 기록하지 않으며 수집 운영·원본은 변경하지 않는다. 배포는 이번 기능 산출물에 포함하지 않으며 향후 모델 배포에는 2인 확인이 필요하다.
