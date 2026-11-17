# Feature Specification: TW CEMS ML-ready Spark 이식 (silver/tw_cems → silver/tw_cems_ml_ready)

**Feature Branch**: `32-a-tw-cems-ml-ready-spark-이식-silvertw_cems-silvertw_cems_ml_ready` (#28 브랜치에서 분기)

**Created**: 2026-11-09

**Status**: Draft

**Input**: User description: "C의 pandas ML-ready 규칙(src/smokestack_guard/silver/ml_ready.py, #30 변경 기준)을 Spark로 옮겨 Glue 5.0에서 실행. 입력 s3://smokestack-tms-raw-952900391026/silver/tw_cems/ 36개월(8,036만 행), 출력 silver/tw_cems_ml_ready/ (약 1,769만 행, 35컬럼), 카탈로그 tms_silver.tw_cems_ml_ready. 36개월 한 번에 실행, 전체 덮어쓰기, 실행 기록 silver/_runs/tw_cems_ml_ready/. 빈 슬롯 때문에 시각 기준 윈도우로 18개 컬럼 계산. 기본안: Spark 윈도우 함수 구현 + pandas는 정답지, 파일 4~8개(128~256MB) 파티션 없음(E 확인 필요). 검증: C의 pandas 결과와 35컬럼 비교 불일치 0, 양성 135,978. 같은 tms-silver 스택에 Job 추가. 범위 밖: 피처·라벨 정의 변경, K-TMS ML-ready 실행, SageMaker 학습."

**관련 이슈**: #32 · **관련**: `specs/a-platform/004-tw-cems-silver-glue` (입력 Silver, PR #31) · `specs/c-contract/201-tw-cems-silver` (ML-ready 규칙·계약, C) · #30 (C, `ml_ready.py` 변경)

## 배경

004(PR #31)로 대만 CEMS Silver 36개월(80,359,440행)이 `silver/tw_cems/`에 있다. 학습용 테이블(ML-ready)은 아직 C의 PC에서 pandas(`ml_ready.py`)로 만든 결과뿐이다. 그 결과(약 1,769만 행, 학습 가능 양성 135,978행)는 `s3://smokestack-cems-local-eda-952900391026/ml_ready/part.parquet`(924MB)에 올라와 있다. 하지만 클라우드 파이프라인이 만든 것이 아니라서, Silver가 바뀌거나 월이 추가될 때 다시 만들 수 없다.

이 기능은 **같은 규칙을 Spark로 옮겨** 클라우드에서 실행한다.
- 결과: `silver/tw_cems_ml_ready/`
- 조회: Athena `tms_silver.tw_cems_ml_ready`
- SageMaker 학습(E)은 이 경로를 읽는다.

규칙(피처·라벨 정의)은 바꾸지 않는다. 규칙은 C의 영역이고, 이 기능은 같은 규칙의 Spark 구현과 실행 환경만 다룬다.

```
silver/tw_cems/ (36개월, 8,036만 행)
   │ 이 기능: 고르기 → 굴뚝×항목별 시간순 → 파생 피처·라벨
   ▼
silver/tw_cems_ml_ready/ (약 1,769만 행, 35컬럼) ──▶ Athena 조회, SageMaker 학습(E)
```

**핵심 난점**: pandas 구현은 굴뚝×항목마다 30분 격자의 빈 칸을 채운 뒤 앞뒤 값을 계산한다. 그래서 빈 구간을 건너뛰어 앞뒤 값을 잇지 않는다. 다른 시각의 값을 참조하는 18개 컬럼(lag, 변화량, 이동통계, 추세, 유효 여부, 라벨)은 같은 의미를 지켜야 한다. "바로 앞 행"이 아니라 "정확히 30분 전 슬롯"이고, 비어 있으면 값 없음이다.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A가 36개월 ML-ready를 한 번에 만든다 (Priority: P1)

운영 담당자(A)는 명령 하나로 Silver 36개월 전체에서 ML-ready를 만들고 싶다. Silver에 월이 추가되거나 다시 만들어지면 같은 명령으로 전체를 다시 만들 수 있어야 한다. 끝나면 행 수, 학습 가능 행 수, 양성 수, 소요 시간, 추정 비용을 보고 싶다.

**Why this priority**: 이 기능의 목적이다. 이 실행이 없으면 E가 학습할 클라우드 테이블이 없다.

**Independent Test**: 실행 뒤 `silver/tw_cems_ml_ready/`에 파일이 생기고, 실행 기록의 행 수·양성 수가 0보다 큰지 확인한다.

**Acceptance Scenarios**:

1. **Given** Silver 36개월이 있을 때, **When** 실행하면, **Then** ML-ready가 만들어지고 실행 기록에 단계별 행 수(Silver 입력 → 대상 선택 후 → 학습 가능 → 양성)가 남는다.
2. **Given** ML-ready가 이미 있을 때, **When** 다시 실행하면, **Then** 결과 전체가 새 결과로 바뀐다. 이전 결과와 섞이지 않는다.
3. **Given** 실행이 도중에 실패했을 때, **Then** 이전 ML-ready는 그대로 남거나 실행 기록이 없어서 실패를 알 수 있다. 반쯤 쓴 결과를 완료로 오인하지 않는다.

---

### User Story 2 - Spark 결과가 pandas 결과와 같다 (Priority: P1)

C(규칙 담당)와 E(모델 담당)는 클라우드 ML-ready가 C가 검증한 pandas 결과와 **같은 값**인지 확인받고 싶다. 특히 빈 슬롯이 있는 구간에서 lag와 라벨이 틀린 값을 가져오지 않아야 한다.

**Why this priority**: 값이 다르면 모델 성능 비교(원칙 V)가 무의미해진다. 이 기능에서 가장 위험한 부분이다.

**Independent Test**:
- 빈 슬롯을 일부러 넣은 가짜 데이터로 Spark 결과와 pandas `to_ml_ready` 결과를 35컬럼 모두 비교한다.
- 실데이터에서는 C의 결과 파일과 키(`stack_code`, `item_code`, `measured_at`)로 맞춰 비교한다.

**Acceptance Scenarios**:

1. **Given** 10:00과 11:00은 있고 10:30이 없는 굴뚝, **When** 11:00 행을 만들면, **Then** 30분 전 값은 값 없음이다(10:00 값이 아니다). 3시간 통계와 `feature_valid`도 pandas와 같다.
2. **Given** 같은 Silver 입력, **When** Spark와 pandas로 각각 만들면, **Then** 행 집합과 35컬럼이 모두 같다. 실수는 상대 오차 1e-9 이내, 값 없음은 값 없음끼리 같다.
3. **Given** 36개월 실데이터, **When** C의 pandas 결과와 비교하면, **Then** 행 수가 같고, 불일치 행이 0이며, 학습 가능 양성 수가 135,978이다. 다르면 차이를 행 단위로 설명할 수 있다.

---

### User Story 3 - E와 팀원이 ML-ready를 조회하고 학습에 쓴다 (Priority: P2)

E는 SageMaker 학습에서 ML-ready 경로를 읽는다. 학습 전에는 SQL로 양성 비율과 피처 분포를 보고 싶다. D도 SQL로 조회할 수 있어야 한다.

**Why this priority**: 결과가 있어도 읽기 불편하면 쓰이지 않는다. 다만 US1·US2가 먼저다.

**Independent Test**: SQL로 학습 가능 행 수와 양성 수를 조회해 실행 기록과 같은지 확인한다. 파일 크기가 정한 범위 안인지 확인한다.

**Acceptance Scenarios**:

1. **Given** ML-ready가 만들어졌을 때, **When** SQL로 `classification_eligible`·`label_entry_60m`별 건수를 조회하면, **Then** 실행 기록의 수와 같다.
2. **Given** ML-ready 파일 목록, **Then** 파일 하나가 정한 크기 범위(기본 128~256MB) 안이다. 작은 파일이 수백 개 생기지 않는다.

---

### Edge Cases

- **빈 슬롯**: 30분 격자에서 빠진 슬롯(`ok`가 아닌 슬롯 포함)은 앞뒤 값 계산에서 값 없음으로 다룬다. 빠진 슬롯은 출력 행으로 만들지 않는다. pandas도 관측된 행만 남긴다.
- **월 경계**: 10월 1일 00:00의 30분 전 값은 9월 30일 23:30 슬롯이다. 36개월을 한 번에 읽어 월 경계를 넘는다.
- **시리즈 처음과 끝**: 처음 슬롯은 과거 값이 없고, 마지막 슬롯은 미래 라벨이 없다. 값 없음으로 둔다.
- **같은 시각 중복**: 같은 굴뚝·항목·시각에 행이 여러 개면 하나만 남긴다. pandas `drop_duplicates`와 같은 기준을 따른다. Silver 계약상 `ok`·`ppm`에서는 생기지 않아야 한다. 생기면 건수를 기록한다.
- **현재 90% 이상**: `label_entry_60m`은 값 없음이다(진입 예측 대상 아님). pandas 정의를 따른다.
- **라벨 판단 불가**: +30분이나 +60분 중 하나만 있고 90% 미만이면 0으로 확정할 수 없어 값 없음이다. 하나라도 90% 이상이면 1이다.
- **극단값·음수 `ratio_pct`**: 거르지 않는다(201 Open Question 2, 범위 밖).
- **Silver에 월이 추가됨(2026-11 이후)**: 다시 실행하면 전체가 그 범위로 바뀐다.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 시스템은 Silver 경로 `silver/tw_cems/`의 모든 월을 한 번에 읽어야 한다. 카탈로그 테이블이 아니라 저장 경로로 읽는다(004 규칙).
- **FR-002**: 시스템은 `status = ok`, 항목 `nox`·`sox`, 단위 `ppm`인 슬롯만 대상으로 고르고, C의 `ml_ready.py`와 같은 이름 바꾸기(`ts_local`→`measured_at` 등)와 `ratio_pct = ratio × 100`을 해야 한다.
- **FR-003**: 시스템은 C의 `ml_ready.py`(#30 반영본)와 **같은 35컬럼, 같은 순서, 같은 의미**를 만들어야 한다. 컬럼 목록과 상수(90%, 3시간 창, lag 목록, 버전)는 그 모듈에서 가져오고 다시 쓰지 않는다.
- **FR-004**: 다른 시각을 참조하는 컬럼은 **시각 기준**으로 계산해야 한다.
  - "N분 전·후 값"은 정확히 그 시각 슬롯의 값이고, 없으면 값 없음이다.
  - 이동통계는 창 안의 슬롯이 정해진 개수만큼 모두 있을 때만 계산한다(1시간 2개, 3시간 6개).
  - 표준편차는 표본 표준편차다.
- **FR-005**: 시스템은 실데이터 비교 전에, 빈 슬롯이 있는 가짜 데이터로 pandas 구현과 35컬럼이 같음을 자동 테스트로 보여야 한다. "바로 앞 행"으로 계산하면 실패하는 경우를 테스트에 넣는다.
- **FR-006**: 출력은 `silver/tw_cems_ml_ready/`에 Parquet으로 저장하고, 다시 실행하면 전체를 바꿔야 한다. 이전 결과와 섞이지 않는다.
- **FR-007**: 출력은 파티션 없이, 파일 하나가 정한 크기 범위(128~256MB, 4~8개)에 들도록 나눠야 한다. 파일 수는 실행 인자로 바꿀 수 있어야 한다.
  - 행은 `measured_at` 순서로 정렬해 쓴다. 기간 조건(예: Validation 3개월)으로 읽을 때 해당 구간만 읽게 하기 위해서다.
  - 기간 분할은 `measured_at`으로 거른다.
- **FR-008**: 시스템은 실행이 성공한 뒤에만 실행 기록을 `silver/_runs/tw_cems_ml_ready/`에 남겨야 한다. 실행 기록에는 다음을 담는다.
  - Silver 입력 행 수, 대상 선택 후 행 수, 출력 행 수
  - `feature_valid`·`classification_eligible`·`regression_eligible` 건수, 양성(`label_entry_60m = 1`) 수
  - 같은 시각 중복 건수
  - 패키지 해시, 런타임 버전, 시각
- **FR-009**: 시스템은 SQL로 조회할 수 있게 카탈로그에 `tms_silver.tw_cems_ml_ready`를 등록해야 한다. 컬럼 타입은 계약을 따른다.
- **FR-010**: 실행 역할은 다음 권한만 가져야 한다.
  - 읽기: `silver/tw_cems/`
  - 쓰기·삭제: `silver/tw_cems_ml_ready/`와 그 실행 기록 경로, 그리고 Glue가 만드는 폴더 표시 파일(`silver/tw_cems_ml_ready_$folder$`)
  - `bronze/`, `tms_cleansys/`, `silver/tw_cems/` 쓰기는 없다.
- **FR-011**: 실데이터 비교는 C의 결과 파일(`smokestack-cems-local-eda-952900391026/ml_ready/part.parquet`)을 읽기만 한다. 결과는 행 수, 키 불일치 수, 컬럼별 불일치 수로 남긴다.
- **FR-012**: Spark 구현은 A의 `services/tms-silver/`에 두고, C의 코드(`src/smokestack_guard/`)는 수정하지 않는다. 상수와 컬럼 목록은 C의 `ml_ready.py`에서 가져온다. 계산 의미는 PR에서 C의 리뷰를 받는다(CODEOWNERS A+C). 입력 정규화(시각 컬럼, `stack_code`, `unit` 유무)는 분리해서, 나중에 K-TMS에도 쓸 수 있게 한다. K-TMS 실행은 범위 밖이다.
- **FR-013**: 모든 리소스는 코드로 만들고 사람이 적용한다(원칙 III). 같은 `tms-silver` 스택에 추가한다.

### Key Entities

- **tw_cems (입력)**: 004의 Silver. 13컬럼, `year`·`month` 파티션.
- **tw_cems_ml_ready (출력)**: 굴뚝(`stack_code`) × 항목(`item_code`) × 측정 시각(`measured_at`, 대만 현지)마다 한 행. 35컬럼. 정의는 `src/smokestack_guard/silver/ml_ready.py`의 `COLUMNS`와 `specs/c-contract/201-tw-cems-silver/spec.md` FR-011~015를 따른다.
  - 기본 7개: 키, 값, 기준, `ratio_pct`, `headroom_pct`
  - 파생 피처 20개: lag 5개, 변화량 3개, 이동통계 5개, 추세 2개, 시간 주기 5개
  - 라벨 2개, 학습 가능 여부 3개(`feature_valid` 포함), 버전 3개
- **ML-ready 실행 기록**: 실행 ID, 입력 범위(Silver 월 목록), 단계별 행 수, 양성 수, 중복 수, 패키지 해시, 런타임 버전, 시각.
- **pandas 기준 결과 (비교용, 읽기만)**: C의 36개월 ML-ready 1개 파일(924MB).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 36개월 ML-ready가 한 번의 실행으로 만들어지고, 실행 기록이 남는다.
- **SC-002**: C의 pandas 결과와 비교했을 때 행 수가 같고(17,643,361), 키 불일치 0, 35컬럼 불일치 0이다(이동 표준편차는 abs 1e-5 허용, research R5). 학습 가능 양성 수가 135,978이다.
- **SC-003**: 빈 슬롯을 포함한 자동 테스트에서 pandas 구현과 35컬럼이 모두 같다. 이 테스트는 "바로 앞 행" 방식의 잘못된 구현을 잡아낸다.
- **SC-004**: 같은 입력으로 두 번 실행한 결과의 행 수와 실행 기록의 모든 건수가 같다.
- **SC-005**: 출력 파일 수가 정한 범위(기본 4~8개) 안이고, 파일 하나가 1GB를 넘지 않는다.
- **SC-006**: SQL 조회 결과(학습 가능 행 수, 양성 수)가 실행 기록과 같다.
- **SC-007**: 실행 1회의 시간과 비용이 기록된다. 다시 만들 때의 비용을 미리 알 수 있다.
- **SC-008**: E가 이 테이블만으로 학습 입력을 만들 수 있다고 확인한다.

## Assumptions

- **구현 방식** (이슈 #32 기본안): Spark 윈도우 함수로 새로 구현한다. pandas 구현은 테스트와 비교의 정답지로만 쓴다.
- **규칙 기준**: C의 PR #30이 바꾼 `ml_ready.py`를 기준으로 한다. 대만 CEMS 계산은 #30 전후가 같다. #30이 늦게 머지되면 그 브랜치의 내용을 기준으로 맞추고, 머지 뒤 다시 확인한다.
- **실행 환경**: 004와 같은 Glue 5.0 / Spark 3.5.4. 실행 단위는 36개월 전체 1회다. 월 단위로 나누면 월 경계 lag가 끊긴다.
- **출력 구성** (2026-11-09 사용자 결정): 파티션 없이 파일 4~8개로 한다.
  - E의 분할안은 Train 2024-11~2026-04, Validation 2026-05~07, Test 2026-08~10이다. 2026년 안에 세 구간이 모두 있어 연도 경계와 맞지 않는다.
  - 2023년은 2개월뿐이라 연도별 파일 크기가 고르지 않다.
  - 그래서 `year=` 파티션은 이점이 작다. 기간은 `measured_at`으로 거른다.
  - E가 연도 분할을 정하면 쓰기와 카탈로그 정의만 바꾼다.
- **비교 데이터 위치**: C의 결과는 `smokestack-cems-local-eda-952900391026` 버킷에 있다. 이 버킷은 Terraform으로 관리되지 않는다. 비교 실행에 필요한 읽기 권한은 그 경로로만 좁힌다.
- **K-TMS**: #30으로 `ml_ready.py`가 K-TMS 입력도 받게 되었다. 이 기능은 대만 CEMS만 실행하지만, 입력 정규화를 분리해 K-TMS도 같은 Spark 코드를 쓸 수 있게 한다.
- **기간**: ML-ready는 Silver 36개월(2023-11~2026-10)을 모두 담는다.
  - E의 분할 문서는 Train을 2024-11부터로 적었다. 범위를 36개월로 넓히기(2026-11-06) 전 문서로 보인다.
  - Train은 2023-11~2026-04(30개월)가 될 가능성이 크다. 확정은 E가 한다. 36개월을 다 담아 두면 어느 쪽이든 `measured_at` 시작일만 바꾸면 된다.
  - 2023-11(11-27 16:30 이후 없음), 2023-12(12-01 06:30부터)는 원본 공백이 있다. 2026-11-09 Athena로 `tms_silver.tw_cems`에서 확인했다. 11-28~30은 행이 없고, 2023-11의 첫 슬롯은 11-01 00:30이다. 빈 칸을 채우지 않으므로 공백 직후 3시간은 `feature_valid = false`로 자동 제외된다.
- **분할 경계 누수** (E에게 알림): 라벨이 60분 뒤 값을 보므로 각 구간의 마지막 1시간 행은 다음 구간 값을 참조한다.
  - 2026-04/05, 2026-07/08 경계에 1시간 이상 간격을 둔다.
  - 이 처리는 E의 분할 코드에서 하며, 이 기능의 범위 밖이다.
- **범위 밖**:
  - 피처·라벨 정의 변경: 201 Open Questions의 기준 변경, 극단값, NB 코드
  - K-TMS ML-ready 실행
  - SageMaker 학습과 학습·검증·테스트 분할: E의 영역
  - 004 Silver 자체와 C의 pandas Silver 비교
- 이 기능은 수집 Lambda·스케줄과 원본(`bronze/`, `tms_cleansys/`)에 영향이 없다.
