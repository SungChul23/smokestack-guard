# Feature Specification: TW CEMS Silver 클라우드 실행 (Glue, 36개월)

**Feature Branch**: `28-a-tw-cems-silver-glue-실행-36개월-원본-버킷-silver`

**Created**: 2026-11-09

**Status**: Draft

**Input**: User description: "대만 CEMS Silver(C의 specs/c-contract/201-tw-cems-silver, tw_cems_spark.py)를 AWS Glue 5.0에서 실행하는 인프라와 36개월(2023-11~2026-10) 월 단위 실행. 입력: 원본 JSONL s3://smokestack-tms-raw-952900391026/bronze/tw_cems/historical/YYYY-MM.jsonl (85GB, 1억 5,972만 행). 출력: (2026-11-09 변경) 원본 버킷의 silver/ 경로에 year/month 파티션 Parquet, Glue 카탈로그 테이블 등록. 새 스택 infra/stacks/tms-silver (tms-eda 패턴 재사용), Glue 역할은 원본 버킷 읽기 전용. smokestack_guard 패키지 zip 배포. ML-ready Spark 이식(005)과 pandas 결과 비교는 범위 밖."

**관련 이슈**: #28 · **관련**: `specs/c-contract/201-tw-cems-silver` (Silver 규칙·계약, C) · `specs/a-platform/003-tw-cems-eda` (같은 원본의 EDA 변환, A)

## 배경

C는 대만 CEMS 원본(15분 기록)을 30분 슬롯 Silver(`tw_cems`)로 바꾸는 규칙을 pandas로 만들었다. 같은 규칙을 Spark로 옮기는 작업과 로컬 Docker 검증도 마쳤다(201 spec의 User Story 4, `spark_migration_checklist.md`). 36개월 전체 실행은 C의 PC에서 pandas로만 했다. 그 결과(원본 1억 5,973만 행 → Silver 8,036만 행)는 C의 PC에만 있고 팀이 함께 쓸 수 없다.

이 기능은 **이미 검증된 Spark 규칙을 그대로 클라우드에서 실행**한다. 그래서 팀 누구나 같은 Silver를 S3와 SQL로 읽을 수 있게 한다. 규칙은 바꾸지 않는다. 규칙·계약은 C의 영역이고, 이 기능은 실행 환경·권한·저장 위치·실행 절차만 다룬다.

```
원본 JSONL (원본 버킷, 85GB) ──[이 기능: Silver 정제, 월 단위]──▶ Silver Parquet (원본 버킷 silver/) ──▶ SQL 조회
                                                                         └──▶ (005) ML-ready
```

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A가 36개월 Silver를 한 번에 만든다 (Priority: P1)

운영 담당자(A)는 명령 하나로 2023-11~2026-10 월별 원본을 Silver로 변환하고 싶다. 실행 전에 대상 월을 미리 볼 수 있어야 한다. 끝나면 월별 성공·실패, 소요 시간, 추정 비용을 한 번에 보고 싶다. 실패한 월만 골라 다시 돌릴 수 있어야 한다.

**Why this priority**: 이 기능의 목적이다. 이 실행이 없으면 클라우드에 Silver가 없다.

**Independent Test**: 한 달(예: 2025-10)만 지정해 실행하고, 그 달 파티션이 Silver 위치에 생기는지와 행 수가 0보다 큰지 확인한다. 이어서 미리 보기 모드로 36개월 목록을 확인한다.

**Acceptance Scenarios**:

1. **Given** 원본에 2023-11~2026-10 JSONL이 있을 때, **When** 미리 보기로 실행하면, **Then** 36개 월이 대상으로 출력되고 실제 변환은 시작되지 않는다.
2. **Given** 대상 월이 36개일 때, **When** 실행하면, **Then** 정해진 동시 실행 수를 넘지 않게 월별 변환이 진행된다. 끝나면 월별 상태·소요 시간과 합계 추정 비용이 출력된다.
3. **Given** 어떤 월이 실패했을 때, **Then** 그 월은 한 번만 자동 재시도한다. 그래도 실패하면 건너뛰고, 마지막에 실패 목록으로 보여 준다.
4. **Given** 일부 월이 이미 변환되었을 때, **When** 그 월만 다시 실행하면, **Then** 그 월 파티션만 교체되고 다른 월은 그대로다.

---

### User Story 2 - 팀원이 Silver를 SQL로 조회한다 (Priority: P1)

C(계약 확인), D(대시보드), E(모델)는 Silver를 내려받지 않고 SQL로 월별 `status` 분포, 굴뚝별 값을 조회하고 싶다. 특정 월만 보는 쿼리는 그 월만 읽어야 한다.

**Why this priority**: Silver는 팀 공통 데이터다. 결과가 S3에만 있고 조회할 수 없으면 C의 PC 결과와 다를 바가 없다.

**Independent Test**: 카탈로그 등록 뒤 SQL로 월 조건을 붙인 `status`별 건수를 조회해, 결과가 나오고 읽은 양이 그 월 수준인지 확인한다.

**Acceptance Scenarios**:

1. **Given** 36개월 변환과 카탈로그 등록이 끝났을 때, **When** 팀원이 Silver 테이블을 월 조건과 함께 조회하면, **Then** 그 월의 데이터만 읽고 결과가 나온다.
2. **Given** 카탈로그에 보이는 컬럼, **Then** C의 Silver 계약 13개 컬럼(`area_nm`, `fact_manage_nm`, `stack_code`, `item`, `unit`, `value`, `limit`, `status`, `ts_kst`, `ratio`, `ts_local`, `code2`, `flag_code_ratio_mismatch`)과 파티션 `year`, `month`가 계약의 타입대로 보인다.
3. **Given** 36개월 Silver, **When** 월별 행 수를 합하면, **Then** 결과는 C의 pandas 실행 기록(8,036만 행)과 같은 규모다. 정확한 행·컬럼 비교는 범위 밖이다.

---

### User Story 3 - 원본은 실행이 잘못되어도 안전하다 (Priority: P1)

원본은 다시 받을 수 없다(원칙 I). Silver가 원본 버킷의 `silver/` 경로에 저장되므로, 변환이 실패하거나 설정을 잘못 넣어도 원본 경로(`bronze/`, `tms_cleansys/`)의 객체는 바뀌거나 지워지면 안 된다.

**Why this priority**: 협상 불가 원칙이다. 이 기능은 원본 버킷에 **쓰기·삭제 권한을 가진** 첫 실행 주체를 만든다.

**Independent Test**: 실행 역할의 권한 목록을 검토해 쓰기·삭제 권한이 `silver/tw_cems/` 경로에만 있는지 확인한다. 출력 위치에 `bronze/` 경로를 넣었을 때 실행이 권한 오류로 실패하는지 확인한다.

**Acceptance Scenarios**:

1. **Given** Silver 실행 역할, **Then** 원본 버킷의 `bronze/tw_cems/`에는 목록 조회와 읽기만 허용된다. 쓰기·삭제는 `silver/tw_cems/`와 그 실행 기록 경로에만 허용된다.
2. **Given** 출력 경로를 `bronze/` 아래로 잘못 지정했을 때, **When** 실행하면, **Then** 쓰기 권한이 없어 실패하고 원본은 바뀌지 않는다.

---

### Edge Cases

- **다른 달 행이 섞인 원본 파일**: 월 단위 덮어쓰기는 결과에 나온 달의 파티션을 교체한다. 그래서 `2025-10.jsonl`에 9월이나 11월 행이 섞여 있으면, 그 달의 이미 만들어진 Silver를 덮어쓸 수 있다. 실행은 입력 월과 다른 달의 행을 발견하면 쓰기 전에 멈추고, 그 건수를 보고해야 한다. 2026-11-09에 Athena로 확인한 결과, 현재 36개월 원본에는 이런 행이 0건이다. 이 검사는 2026-11 이후 새 월이 추가될 때를 대비해 둔다.
- **원본 공백 월**: 2023-11은 11-27 16:30에서 끊기고, 2023-12는 첫 6시간 반이 없다. 채우지 않고 그대로 변환한다. 실패로 보지 않는다.
- **시각 형식 혼재**: 달마다 `T`/공백 구분, 초 유무가 다르다. C의 규칙이 모두 처리하며, 로컬에서 검증했다.
- **같은 달을 두 번 실행**: 결과가 같아야 하고, 그 달 파티션만 교체된다.
- **원본에 없는 월을 지정**: 그 월은 건너뛰고 "원본 없음"으로 보고한다. 빈 파티션을 만들지 않는다.
- **실행 중 중단(시간 초과 등)**: 그 월은 실패로 보고한다. 다시 실행하면 그 월 파티션이 통째로 교체되어 반쯤 쓴 결과가 남지 않아야 한다.
- **규칙 코드가 바뀐 뒤 실행**: 어떤 버전의 규칙 코드로 만든 Silver인지 알 수 있어야 한다.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 시스템은 C의 Silver Spark 규칙(`src/smokestack_guard/silver/tw_cems_spark.py`)을 **수정하지 않고** 클라우드 분산 실행 환경에서 실행해야 한다. 실행 환경은 로컬 검증 조건(Spark 3.5, Java 17, Python 3)과 같은 계열이어야 한다.
- **FR-002**: 입력은 원본 버킷의 월별 JSONL(`bronze/tw_cems/historical/YYYY-MM.jsonl`)이다. EDA Parquet(`tms_eda.tw_cems_raw`)은 입력으로 쓰지 않는다. 003 spec의 결정을 따른다.
- **FR-003**: 실행 단위는 한 달이다. 한 실행은 입력 월의 Silver 파티션(`year`, `month`)만 만들거나 교체해야 한다.
- **FR-004**: 시스템은 입력 월과 다른 달의 행이 결과에 있으면 쓰기 전에 실행을 멈추고, 그 건수를 보고해야 한다.
- **FR-005**: 출력은 원본 버킷의 **`silver/` 경로**에 열 단위 압축 형식(Parquet)으로, `year`/`month` 파티션으로 저장해야 한다. 원본 경로(`bronze/`, `tms_cleansys/`)와 경로가 겹치지 않아야 한다.
- **FR-006**: 시스템은 Silver를 SQL로 조회할 수 있게 카탈로그에 테이블로 등록해야 한다. 컬럼과 타입은 C의 Silver 계약을 따르고, 파티션 조건 조회는 그 파티션만 읽어야 한다.
- **FR-007**: 실행 역할은 원본 버킷의 `bronze/tw_cems/` 아래를 목록 조회·읽기만 할 수 있어야 한다. 쓰기·삭제 권한은 `silver/tw_cems/`와 그 실행 기록 경로에만 준다. `tms_cleansys/`에는 접근하지 않는다.
- **FR-008**: 사람이 실행하는 일괄 실행 명령이 있어야 한다. 이 명령은 다음을 제공한다.
  - 대상 월 범위 지정(기본 2023-11~2026-10)과 미리 보기
  - 동시 실행 수 제한
  - 실패 월 1회 자동 재시도
  - 월별 결과 표(상태, 소요 시간)와 합계 추정 비용
  - 실패 목록
- **FR-009**: 정기 스케줄은 만들지 않는다. 실행은 사람이 시작한다.
- **FR-010**: 시스템은 월별 실행 결과로 다음을 남겨야 한다.
  - 입력 행 수
  - Silver 행 수와 `status`별 행 수
  - 사용한 규칙 코드의 버전(배포한 패키지 해시, plan R5)
  - 이 값들은 실행 로그나 기록 파일에서 확인할 수 있어야 한다.
- **FR-011**: 모든 리소스는 코드로 만들고 사람이 적용한다(원칙 III). 실행 로그는 보존 기간을 두고 남긴다.
- **FR-012**: 규칙 코드(`smokestack_guard` 패키지)를 실행 환경에 올리는 절차가 있어야 한다. 저장소의 코드가 바뀌면 같은 절차로 다시 올릴 수 있어야 한다.
- **FR-013**: Silver 저장 위치에는 005(ML-ready)와 K-TMS의 결과도 둘 수 있게 테이블별 경로를 분리해야 한다.
- **FR-014**: Silver 경로·테이블 이름 규칙을 팀 공통 규칙(`AGENTS.md`)에 적어, 다른 Silver(K-TMS 등)도 같은 규칙을 따르게 해야 한다.

### Key Entities

- **원본 월 파일**: `bronze/tw_cems/historical/YYYY-MM.jsonl`. 15분 기록, 원본 키 15개. 읽기 전용이다.
- **tw_cems (Silver)**: 굴뚝 × 항목 × 단위 × 30분 슬롯마다 한 행. 계약 컬럼 13개와 파티션 `year`·`month`(대만 현지 시각 기준). 정의는 `specs/c-contract/201-tw-cems-silver/spec.md`를 따른다.
- **월 실행 기록**: 월, 상태, 시도 횟수, 소요 시간, 입력 행 수, Silver 행 수, `status`별 행 수, 규칙 코드 버전.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 36개 월이 모두 성공 상태로 끝나고, Silver에 36개 월 파티션이 있다.
- **SC-002**: 36개월 Silver 전체 행 수가 C의 로컬 기록(약 8,036만 행)과 같다. 다르면 그 차이를 월별로 설명할 수 있다.
- **SC-003**: 월 조건을 붙인 SQL 조회가 그 월의 데이터만 읽는다. 읽은 양이 전체의 1/36 수준이다.
- **SC-004**: 같은 달을 두 번 실행한 뒤 그 달 행 수와 `status`별 행 수가 같고, 다른 달 파티션은 바뀌지 않는다.
- **SC-005**: 원본 버킷의 객체 수와 크기가 실행 전후로 같다.
- **SC-006**: 36개월 전체 실행의 총 비용과 총 소요 시간이 기록되어, 다시 실행할 때의 비용을 미리 알 수 있다.
- **SC-007**: C·D·E 중 1명 이상이 Silver 테이블을 SQL로 조회해 업무에 쓸 수 있다고 확인한다.

## Assumptions

- **실행 환경 버전**: Glue 5.0을 쓴다. C가 검증한 Spark 3.5.4 / Java 17과 같은 계열이고, 201 spec의 FR-018(Glue 5.0/5.1)과 맞는다. 기존 `tms-eda` 스택의 6.0과 맞추지 않는다.
- **저장 위치** (2026-11-09 사용자 결정): 원본 버킷 `smokestack-tms-raw-952900391026`의 `silver/` 경로에 둔다.
  - Silver는 `silver/tw_cems/`이고, 005에서 `silver/tw_cems_ml_ready/`, 나중에 K-TMS는 `silver/ktms/`를 쓴다.
  - EDA 버킷에는 Silver를 두지 않는다.
  - 쓰기·삭제 권한은 `silver/<자기 테이블>/`로만 좁힌다.
- **조회**: 기존 `tms-eda` Athena 워크그룹을 쓴다. 쿼리 결과는 EDA 버킷에 저장되어 30일 뒤 지워진다. 원본 버킷에 수명 주기 규칙을 두지 않기 위해서다.
- **카탈로그**: 새 데이터베이스(예: `tms_silver`)에 테이블 `tw_cems`를 둔다. EDA 데이터베이스(`tms_eda`)와 섞지 않는다.
- **스택**: 새 스택 `infra/stacks/tms-silver`. Glue 작업·역할·로그·스크립트 업로드·일괄 실행 명령은 `tms-eda`의 구성을 재사용한다.
- **pandas 결과와의 비교는 범위 밖**이다. C의 pandas 결과가 S3에 올라오면 후속 작업에서 비교한다. 이 spec은 행 수 규모(SC-002)만 확인한다.
- **ML-ready(Feature·라벨) Spark 이식은 범위 밖**이다. `005-tw-cems-ml-ready-spark`에서 다룬다.
- **2023-10 이전과 2026-11 이후 월**은 대상이 아니다. 원본이 생기면 같은 명령으로 범위만 넓힌다.
- Silver 규칙(`tw_cems.py`, `tw_cems_spark.py`)이 바뀌어야 하면 C에게 요청하고, 이 기능에서는 고치지 않는다. 예외로 FR-004(다른 달 행 차단)는 실행 진입점(Glue 스크립트)에서 처리하고 규칙 코드는 건드리지 않는다.
- 이 기능은 수집 Lambda·스케줄에 영향이 없다(원칙 I의 수집 공백 위험 없음).
