# Feature Specification: TW CEMS 재수집 원본 비교 (bronze2 → silver2)

**Feature Branch**: `32-a-tw-cems-ml-ready-spark-이식-silvertw_cems-silvertw_cems_ml_ready` (005와 같은 브랜치)

**Created**: 2026-11-10

**Status**: 실행 완료, silver2를 TW CEMS 공식으로 결정 (2026-11-10)

**Input**: User description: "C가 대만 CEMS 원본 36개월을 다시 받아 bronze2/tw_cems/에 올렸다. 기존 silver/는 유지하고, 같은 규칙으로 silver2/에 Silver와 ML-ready(v2)를 새로 만들어 기존과 비교한다. S3 저장 비용이 들어도 나란히 둔다."

**관련 이슈**: #32 · **관련**: `specs/a-platform/004-tw-cems-silver-glue` (Silver Job) · `specs/a-platform/005-tw-cems-ml-ready-spark` (ML-ready Job) · `specs/c-contract/201-tw-cems-silver` (규칙·계약, C) · #33·PR #34 (ML-ready 적격 규칙 v2)

## 배경

004·005로 만든 `silver/tw_cems`와 `silver/tw_cems_ml_ready`는 `bronze/tw_cems/historical/`(2026-11-03~05 수집)을 입력으로 했다. 2026-11-10 C가 같은 36개월을 다시 받아 `bronze2/tw_cems/`에 올렸다.

두 원본을 줄 단위로 비교한 결과(Athena, 2026-11-10):

| 항목 | 결과 |
|---|---|
| 파일 | 36개월, 각 91.20GB. 달마다 크기 차이 −88KB ~ +113KB |
| 줄 수 | 36개월 모두 같다 (합계 159,725,257) |
| 기존에만 있는 줄 | 0 |
| 새 원본에만 있는 줄 | 3,432,371 (달마다 1.32 ~ 2.69%) |
| 해석 | 기존 원본은 그만큼의 줄이 **이미 받은 줄의 중복**이었고, 새 원본에는 그 자리에 **실제 측정값**이 있다. C 확인: 새 원본은 36개월 모두 `_id`가 1부터 끝까지 연속이고 중복 0, 줄 수가 서버가 알려 준 총 행 수와 같다 |

파일 크기와 줄 수가 같아서 크기 비교로는 드러나지 않았다. Silver 규칙은 완전 중복을 지우므로, 기존 Silver에는 그만큼의 측정값이 빠져 있었다.

이 기능은 **기존 결과를 덮어쓰지 않고** 새 원본으로 같은 규칙을 다시 실행해 나란히 비교한다.

**결정 (2026-11-10)**: 비교 결과 새 원본이 맞으므로 **TW CEMS의 공식 데이터는 `silver2/` (`tms_silver2.*`)다.** 기존 `silver/tw_cems*`(`tms_silver.tw_cems*`)는 옛 원본 기준이라 쓰지 않고, 정리 전까지 보존만 한다(`AGENTS.md` S3 경로 규칙).

```
bronze/tw_cems/historical/ ──(004 Job)──▶ silver/tw_cems/  ──(005 Job)──▶ silver/tw_cems_ml_ready/   (기존, 유지)
bronze2/tw_cems/           ──(같은 스크립트)▶ silver2/tw_cems/ ──(같은 스크립트)▶ silver2/tw_cems_ml_ready/  (이 기능)
```

## User Scenarios & Testing

### User Story 1 - A가 새 원본으로 Silver2를 만든다 (Priority: P1)

A가 `bronze2/tw_cems/` 36개월을 기존과 같은 Silver 규칙으로 `silver2/tw_cems/`에 만든다. 기존 `silver/tw_cems/`는 바뀌지 않는다.

**Independent Test**: 36개월 실행 기록이 모두 성공이고, `tms_silver2.tw_cems`가 월별 36행으로 조회된다. 기존 `tms_silver.tw_cems` 건수는 그대로다.

**Acceptance Scenarios**:

1. **Given** `bronze2/tw_cems/` 36개 파일, **When** Silver2 Job을 월별로 실행하면, **Then** `silver2/tw_cems/year=YYYY/month=MM/`에 36개월이 생기고 실패는 0이다.
2. **Given** 두 Silver, **When** 슬롯 키로 비교하면, **Then** 기존 `ok` 슬롯의 값은 바뀌지 않고, 새 원본에서 `ok`가 늘어난다.

### User Story 2 - A가 Silver2로 ML-ready2(v2)를 만들고 pandas와 비교한다 (Priority: P1)

A가 `silver2/tw_cems/`로 ML-ready(v2 규칙)를 만들고, C가 같은 `bronze2`로 만든 pandas 결과와 35컬럼을 비교한다.

**Independent Test**: compare가 `passed=True`, 행 수 일치, 한쪽에만 있는 행 0.

### User Story 3 - 팀이 두 결과를 비교해 공식 데이터를 정한다 (Priority: P2)

C·E가 Athena에서 `tms_silver.*`와 `tms_silver2.*`를 비교해 학습에 쓸 데이터를 정한다. → `tms_silver2.*`로 결정.

**Independent Test**: 두 DB의 같은 이름 테이블이 각자 자기 경로를 읽는다.

### Edge Cases

- **원본 자체의 공백**: 월요일 저녁~다음 날 아침 공백, 하루 통째로 빈 35일, 굴뚝 무더기 누락은 대만 쪽 원본 특성이다. 다시 받아도 채워지지 않는다(48슬롯 미만인 날 66일, 기존과 같음).
- **실수로 기존 경로를 가리키는 경우**: 새 역할은 `silver2/` 아래에만 쓰기·삭제 권한이 있어 기존 `silver/`를 덮어쓰지 못한다.
- **규칙 버전 차이**: 기존 `silver/tw_cems_ml_ready`는 v1, `silver2/tw_cems_ml_ready`는 v2다. 분류 학습 대상은 v1·v2 차이가 −685행이라 비교에 거의 영향이 없고, 회귀는 v2에서 현재 90% 이상 행이 들어가 차이가 섞인다.

## Requirements

### Functional Requirements

- **FR-001**: 기존 `bronze/`, `silver/`, `tms_silver.*`를 바꾸지 않는다(원칙 I).
- **FR-002**: Silver2·ML-ready2는 기존 Job과 **같은 스크립트와 같은 패키지**를 쓴다. 경로 인자만 다르다.
- **FR-003**: Silver2 역할은 `bronze2/tw_cems/*` 읽기, `silver2/tw_cems/*`·`silver2/_runs/tw_cems/*` 쓰기·삭제만 가진다.
- **FR-004**: ML-ready2 역할은 `silver2/tw_cems/*` 읽기, `silver2/tw_cems_ml_ready/*`·`silver2/_runs/tw_cems_ml_ready/*` 쓰기·삭제, 정답지 경로 읽기만 가진다.
- **FR-005**: 경로 규칙 `silver2/<테이블>/` = `tms_silver2.<테이블>`. 컬럼 정의는 기존 테이블과 같다(Terraform `locals` 공유).
- **FR-006**: ML-ready2는 main에 머지된 v2 적격 규칙(#33, PR #34)을 쓴다.
- **FR-007**: silver2 리소스는 `infra/stacks/tms-silver/silver2.tf` 한 파일에 모은다. 공식으로 결정됐으므로 유지한다.

## Success Criteria

| ID | 기준 | 결과 (2026-11-10) |
|---|---|---|
| SC-001 | Silver2 36개월 성공 | ✅ 36/36, 실패 0, 약 18분 |
| SC-002 | 기존 `ok` 슬롯 값 변경 0 | ✅ `ok → ok` 24,743,836슬롯 중 값 변경 0 |
| SC-003 | ML-ready2 compare `passed=True` | ✅ 18,436,379행 양쪽 일치, 한쪽에만 있는 행 0 |
| SC-004 | 기존 `silver/`·`tms_silver.*` 무변경 | ✅ 새 역할에 기존 경로 쓰기 권한 없음 |

## 결과 (2026-11-10)

### Silver: 기존 vs Silver2

| | 기존 | Silver2 | 변화 |
|---|---|---|---|
| 슬롯 | 80,359,440 | 80,381,988 | +22,548 |
| `ok` | 24,743,836 | 25,854,851 | **+1,111,015 (+4.5%)** |
| `partial` | 4,555,488 | 1,202,295 | **−74%** |

기존 `partial`(15분 값 2개 중 하나만 있는 슬롯)이 새 원본에서 바뀐 상태: `not_monitored` 1,367,808 · `ok` 1,111,015 · `other_code` 895,527 · `partial` 그대로 1,179,556 · `invalid` 1,582 (합 4,555,488). 새로 생긴 슬롯은 `partial` 22,522 · `invalid` 26.
상태가 같은 슬롯은 모든 상태에서 값 변경이 0이다. 슬롯 키는 `area_nm`·`fact_manage_nm`·`stack_code`·`item`·`unit`·`ts_local`(Silver 규칙과 같음)이다.
기존 `partial`의 약 74%는 중복 줄이 측정값 자리를 차지해 생긴 것이었다. 복구된 슬롯은 요일·시간대에 고르게 퍼져 있다(특정 시간대 장애가 아님).

### ML-ready: 기존(v1) vs ML-ready2(v2)

| | 기존 v1 | 기존 원본 v2 (C pandas) | **ML-ready2 v2** | 기존 원본 v2 대비 |
|---|---|---|---|---|
| ML-ready 행 | 17,643,361 | 17,643,361 | 18,436,379 | +4.5% |
| `feature_valid` | 11,631,568 | — | 15,282,179 | |
| 분류 학습 가능 | 9,858,569 | 9,857,883 | **14,158,991** | **+43.6%** |
| 그중 양성 | 133,726 | 133,715 | **181,231** | +35.5% |
| 회귀 학습 가능 | 10,532,709 | 10,687,092 | **14,664,879** | +37.2% |

| ML-ready2 | NOx | SO₂ |
|---|---|---|
| ML-ready 행 | 10,246,871 | 8,189,508 |
| 분류 학습 가능 | 7,861,136 | 6,297,855 |
| 양성 (비율) | 144,744 (1.84%) | 36,487 (0.58%) |
| 회귀 학습 가능 | 8,174,747 | 6,490,132 |

- **`ok`는 4.5% 늘었는데 분류 학습 행은 44% 늘었다.** 피처는 3시간(6슬롯), 정답은 그 뒤 2슬롯이 모두 있어야 한다. 흩어진 누락 하나가 앞뒤 최대 8행의 학습 자격을 없앴다.
- **증가는 고르다.** 36개월 모두 +24 ~ +60%. 굴뚝·항목별 증가율 중간값 +44%, 상위 10% +50% (NOx 341, SO₂ 267). 학습 행이 0이던 굴뚝이 새로 생기지는 않았다.
- **새로 생긴 행의 피처 분포는 기존과 같다.** 평균 비율 NOx 49.11 → 48.87, SO₂ 23.60 → 23.41.
- **양성 비율은 1.36% → 1.28%.** 새로 생긴 행의 양성 비율이 약 17% 낮다(NOx 1.95% → 1.59%). 정답 규칙상 양성은 다음 두 슬롯 중 하나만 있어도 정해지고 음성은 둘 다 있어야 정해진다. 그래서 누락이 음성을 더 많이 지워 기존 양성 비율이 부풀었던 것으로 본다(추론, 행 단위 미확인).

### compare (Glue Spark vs C pandas, 같은 bronze2)

`passed=True`, 18,436,379행 일치. 35컬럼 중 30개는 값이 완전히 같다. 나머지는 부동소수점 계산 순서 차이다.

| 컬럼 | 최대 차이 |
|---|---|
| `hour_sin`, `month_sin` | 1.11e-16 |
| `ratio_rolling_mean_1h` / `_3h` | 7.67e-13 / 2.27e-13 |
| `ratio_rolling_std_3h` | 5.96e-06 (허용 1e-5, 005 R5) |

## Assumptions

- 정답지: `s3://smokestack-cems-local-eda-952900391026/tw_cems_ml_ready_fixed/part.parquet` (C가 bronze2로 만든 pandas v2 결과, 1.06GB).
- 비용: Silver2 36개월 약 $3.7, ML-ready2 build·compare 약 $0.4, Athena 비교 약 $1(일회성). 보관 비용은 `bronze2/` 91.2GB 약 $2.3/월이 대부분이다.
- 기존 `bronze/`·`silver/` 정리 시점은 이 기능 범위 밖이다(tasks.md "남은 결정").
