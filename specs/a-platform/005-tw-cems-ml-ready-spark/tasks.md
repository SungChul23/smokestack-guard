---
description: "005 TW CEMS ML-ready Spark 이식 작업 목록"
---

# Tasks: TW CEMS ML-ready Spark 이식

**Input**: `specs/a-platform/005-tw-cems-ml-ready-spark/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: 자동 테스트를 둔다. spec이 다음을 요구하기 때문이다.
- pandas와의 35컬럼 일치(FR-005, SC-003)
- 실패 판별(US1-3)

테스트 도구:
- 로컬 Spark 3.5.4 + pandas `to_ml_ready`(정답지)
- boto3는 가짜 객체로 대신한다.
- 로컬 실행 환경: `services/tms-silver` dev 의존성(Python 3.11, Java 17)

**Organization**: 사용자 스토리별 단계.
- US2(Spark = pandas)를 먼저 둔다. US1(36개월 생성)이 쓰는 규칙 코드를 만들기 때문이다.
- US3(조회·학습)은 US1의 결과가 있어야 확인할 수 있다.
- 순서: **US2 → US1 → US3**

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 다른 파일이고 선행 작업이 없어 병렬 가능
- **[Story]**: US1(36개월 생성), US2(pandas와 일치), US3(조회·학습)
- 🧑: **사람이 하는 작업**(`terraform plan`/`apply`, Glue 실행, Athena 조회). 에이전트는 실행하지 않는다.

## 경로

- 코드: `services/tms-silver/`. C의 `src/smokestack_guard/`는 **수정하지 않는다**(`ml_ready.py` 상수만 import).
- 스택: `infra/stacks/tms-silver/`. 004 리소스는 바꾸지 않고 추가만 한다.
- 버킷
  - 원본 버킷 `smokestack-tms-raw-952900391026`: 입력 `silver/tw_cems/`, 출력 `silver/tw_cems_ml_ready/`, 실행 기록 `silver/_runs/tw_cems_ml_ready/`
  - 정답지 `smokestack-cems-local-eda-952900391026/ml_ready/part.parquet` (읽기만)

---

## Phase 1: Setup

- [X] T001 `services/tms-silver/pyproject.toml`의 `[tool.setuptools] py-modules`에 `ml_ready_spark`, `glue_tw_cems_ml_ready`, `run_ml_ready`를 추가한다. 다른 줄은 바꾸지 않는다.
- [X] T002 [P] `services/tms-silver/tests/ml_ready_cases.py`를 만든다. **가짜** Silver(pandas DataFrame)를 만드는 함수 `build_silver() -> pd.DataFrame`이다.
  - 컬럼: Silver 13개(`area_nm`, `fact_manage_nm`, `stack_code`, `item`, `unit`, `value`, `limit`, `status`, `ts_kst`, `ratio`, `ts_local`, `code2`, `flag_code_ratio_mismatch`). `ts_kst = ts_local + 1시간`
  - 굴뚝·항목 시리즈마다 담을 사례(모듈 독스트링에 표로 적는다):
    1. **며칠짜리 공백**: 2023-11-27 14:00~16:30 연속 → 공백 → 2023-12-01 06:30~10:00 연속 (2023-11 원본 공백을 줄인 형태, Athena 확인)
    2. **30분 한 칸 공백**: 10:00, 10:30, (11:00 없음), 11:30, 12:00 … 3시간 이상 이어짐
    3. **월 경계**: 2025-09-30 21:00 ~ 2025-10-01 03:00 연속
    4. **진입 1**: 85 → 88 → 92 (t+60에 90% 이상), **진입 0**: 80 → 82 → 84, **현재 90% 이상**: 95
    5. **+30만 있고 +60 없음**: t+30이 70(미진입)이면 null, 91(진입)이면 1
    6. **시리즈 처음 5슬롯**: `feature_valid = false`
    7. **고르기에서 빠져야 할 행**: `status = other_code`, `item = co`, `unit = %`인 행 몇 개
    8. 같은 시리즈를 `nox`와 `sox` 두 항목으로 둠
  - 값은 손으로 정한 소수(예: `ratio` 0.8512)를 쓴다. 실제 원본 값을 쓰지 않는다.
- [X] T003 [P] `services/tms-silver/tests/conftest.py`에 fixture `ml_ready_silver_pdf`(T002의 DataFrame)와 `ml_ready_silver_df`(같은 내용의 Spark DataFrame)를 추가한다. `ts_local`·`ts_kst`는 timestamp, `value`·`limit`·`ratio`는 double이다. 기존 fixture는 바꾸지 않는다.

---

## Phase 2: Foundational

**Purpose**: 결과 비교 함수. US2 테스트와 US1의 `compare` 모드가 함께 쓴다.

- [X] T004 `services/tms-silver/ml_ready_spark.py`에 `compare(ours: DataFrame, theirs: DataFrame, abs_tol=1e-9, rel_tol=1e-9, samples=5) -> dict`를 만든다(data-model.md §4 compare 필드).
  - 키는 (`stack_code`, `item_code`, `measured_at`)이고 full outer join한다.
  - 반환값
    - `ours_rows`, `theirs_rows`
    - `only_ours`, `only_theirs`
    - `column_mismatches`: 키 제외 32컬럼별 불일치 행 수
    - `mismatch_samples`: 컬럼별 최대 `samples`개 키. 키만 남기고 값은 남기지 않는다.
    - `tolerance`, `passed`
  - 같음의 정의
    - 실수: `|a−b| ≤ abs_tol + rel_tol·|b|`
    - null은 null끼리 같다.
    - boolean·string은 그대로 비교한다.
  - `passed`는 `only_ours == only_theirs == 0`이고 모든 컬럼 불일치가 0일 때 true다.

**Checkpoint**: `compare`를 같은 DataFrame끼리 돌리면 `passed: true`가 나온다.

---

## Phase 3: User Story 2 - Spark 결과가 pandas 결과와 같다 (Priority: P1) 🎯

**Goal**: 규칙 코드(`ml_ready_spark.py`)가 pandas `to_ml_ready`와 35컬럼 모두 같은 결과를 낸다.

**Independent Test**: T002 fixture에서 Spark와 pandas 결과를 `compare`하면 `passed: true`다. 행 기준 `lag()` 구현과는 다르다.

### Tests for User Story 2

- [X] T005 [P] [US2] `services/tms-silver/tests/test_ml_ready_spark.py`를 작성한다.
  1. **pandas와 일치**
     - `ml_ready.to_ml_ready(ml_ready_silver_pdf)`를 Spark DataFrame으로 만든다(타입은 data-model.md §2).
     - `ml_ready_spark.to_ml_ready(ml_ready_silver_df)`와 `compare` → `passed: true`
     - 행 수도 같아야 한다.
  2. **컬럼 계약**: 결과 컬럼 이름·순서가 `ml_ready.COLUMNS`와 같고, 타입이 data-model.md §2 표와 같다.
     - `day_of_week`, `rise_count_3h`, `label_entry_60m`는 double이다.
     - `feature_valid`, `classification_eligible`, `regression_eligible`는 boolean이다.
  3. **공백 사례 직접 확인**
     - 2023-12-01 06:30 행: `ratio_lag_30m`이 null, `feature_valid = false`
     - 09:00 행: `feature_valid = true`
     - 2023-11-27 16:00·16:30 행: `label_ratio_60m`이 null
  4. **월 경계**: 2025-10-01 00:00 행의 `ratio_lag_30m`이 2025-09-30 23:30 행의 `ratio_pct`와 같다.
  5. **라벨 사례**: 사례 4·5의 `label_entry_60m`이 1 / 0 / null / null(현재 90% 이상)과 같다.
  6. **민감도**: 테스트 파일 안에 "행 기준 `F.lag`" 버전의 lag 계산을 두고 같은 fixture에 돌린다. `ratio_lag_30m` 불일치가 1건 이상이어야 한다. fixture가 공백을 실제로 담는다는 확인이다.
  7. **고르기**: 사례 7의 행이 결과에 없다.
  8. **K-TMS 정규화 형태** (#30 규칙, R3): `ts_local`·`unit`이 없고 `ts_kst`가 있는 가짜 입력을 `normalize`에 넣는다.
     - `measured_at = ts_kst`
     - `stack_code = area_nm|fact_manage_nm|stack_code`
     - `unit` 조건 없이 고른다.
  9. **중복 키**: 같은 키 2행을 넣으면 `duplicate_keys = 1`이고, `ratio_pct`가 작은 행이 남는다.
- [X] T006 [P] [US2] `services/tms-silver/tests/test_ml_ready_spark.py`에 `compare` 테스트를 추가한다.
  - 같은 것끼리 비교하면 `passed: true`
  - 한 값을 1e-6만큼 바꾸면 그 컬럼 불일치가 1이고 `mismatch_samples`에 키 1개가 있다.
  - 키 하나를 지우면 `only_theirs = 1`이다.
  - 2e-10 차이는 허용한다.

### Implementation for User Story 2

- [X] T007 [US2] `services/tms-silver/ml_ready_spark.py`에 규칙을 구현한다(research.md R1·R2·R3).
  - import: `from smokestack_guard.silver.ml_ready import COLUMNS, ENTRY_PCT, ML_ITEMS, WINDOW, LAGS, FEATURE_VERSION, LABEL_VERSION, QUALITY_POLICY_VERSION`
    - 숫자 90, 6, [30…150], `v1`을 다시 쓰지 않는다.
    - slope 가중치와 분모는 `WINDOW`로 계산한다.
  - `normalize(silver: DataFrame) -> DataFrame`
    - 출력 컬럼: `stack_code`, `item_code`, `measured_at`, `ratio_pct`, `measure_value`, `standard_value`
    - tw_cems(`ts_local` 있음): `status = 'ok'`, `item ∈ ML_ITEMS`, `unit = 'ppm'`, 시각은 `ts_local`
    - ktms(`ts_local` 없음): `unit` 조건 없음, 시각은 `ts_kst`, `stack_code = concat_ws('|', area_nm, fact_manage_nm, stack_code)`
    - `ratio_pct = ratio * 100`
  - `dedupe(df) -> (DataFrame, int)`: 키 중복 건수를 세고, `ratio_pct` 최솟값 행을 남긴다(`row_number` over 키 order by `ratio_pct`, `measured_at`).
  - `add_features(df) -> DataFrame`
    - `slot = cast(unix_timestamp(measured_at) / 1800 as long)`. 세션 시간대는 UTC다.
    - `w = Window.partitionBy("stack_code","item_code").orderBy("slot")`
    - `v(k) = first("ratio_pct").over(w.rangeBetween(k, k))`, k ∈ {−5..−1, +1, +2}
    - `cnt(n) = count("ratio_pct").over(w.rangeBetween(-(n-1), 0))`
    - R2 표대로 35컬럼을 만든다.
    - `day_of_week = weekday(measured_at)`, `hour_sin = sin(2π·hour/24)` 등. 모두 double로 cast한다.
    - 라벨: `label_entry_60m = when(below & known, when(reached, 1.0).otherwise(0.0))`. null 비교는 `coalesce(v ≥ 90, false)`로 false 처리한다.
    - 버전 컬럼은 `lit(...)`
  - `to_ml_ready(silver) -> DataFrame`: normalize → dedupe → add_features → `select(*COLUMNS)`
  - `ml_ready_stats(df) -> dict`
    - 건수: `output_rows`, `feature_valid_rows`, `classification_eligible_rows`, `regression_eligible_rows`, `positive_rows`, `eligible_positive_rows`
    - `by_item`
  - 모듈 독스트링에 "규칙의 기준은 C의 `ml_ready.py`. 의미를 바꾸지 말 것. 바뀌면 `tests/test_ml_ready_spark.py`가 잡는다"를 적는다.
- [X] T008 [US2] 로컬에서 T005·T006을 실행해 모두 통과시킨다.
  - 불일치가 나면 R2 표와 pandas 코드를 대조해 Spark 쪽을 고친다.
  - pandas 쪽(C의 코드)은 고치지 않는다.
  - 이동 표준편차 차이가 허용 오차를 넘으면 그 값과 원인을 `research.md` R5에 기록하고 사용자에게 알린다.

**Checkpoint**: 로컬에서 Spark = pandas(35컬럼), 행 기준 lag ≠ pandas.

---

## Phase 4: User Story 1 - A가 36개월 ML-ready를 한 번에 만든다 (Priority: P1)

**Goal**: Glue에서 build·compare를 실행하고, 결과와 실행 기록을 남긴다.

**Independent Test**
- 로컬: build 결과 파일 수·정렬·실행 기록과 실패 시 `latest.json`이 없음을 확인한다. compare에서 pandas가 쓴 정답지를 읽는다.
- AWS: 🧑 build 1회 실행.

### Tests for User Story 1

- [X] T009 [P] [US1] `services/tms-silver/tests/test_glue_tw_cems_ml_ready.py`를 작성한다. 로컬 모드이고 `tmp_path`를 쓴다.
  1. **build 정상**
     - T002 Silver를 `year=/month=` 파티션으로 써 두고 `--mode build --files 3`을 실행한다.
     - Parquet 3개가 생기고, 파일별 `measured_at` 최소·최대 구간이 겹치지 않는다.
     - 파일 안이 `measured_at` 오름차순이다.
     - `runs/<ts>.json`과 `latest.json`이 같은 내용이고, data-model.md §4 build 필드를 모두 가진다.
     - `silver_months`가 fixture의 월 목록과 같다.
  2. **실패 시 `latest.json` 없음**
     - 먼저 정상 build로 `latest.json`을 만든다.
     - 고를 행이 없는 입력(모두 `status = invalid`)으로 build를 돌리면 `no ml-ready target rows`로 실패한다.
     - 이후 `latest.json`이 **없다**.
  3. **다시 build**: 같은 입력으로 두 번 실행하면 건수가 모두 같고, 파일 수가 그대로다(이전 파일이 남지 않음).
  4. **compare**
     - pandas `to_ml_ready` 결과를 `to_parquet`으로 쓴 정답지(타임스탬프 ns 그대로)로 `--mode compare`를 실행한다.
     - `compare/<ts>.json`에 `passed: true`가 있고, `theirs_measured_at_type`이 기록된다.
  5. **로그에 값 없음**: 출력에 fixture의 `ratio` 값 문자열이 없다.
- [X] T010 [P] [US1] `services/tms-silver/tests/test_run_ml_ready.py`를 작성한다. boto3 가짜 객체를 쓴다.
  - build 성공 시 `latest.json`의 건수를 출력하고 0으로 끝난다.
  - compare `passed: false`면 1로 끝나고 불일치 컬럼을 출력한다.
  - Job `FAILED`면 1로 끝난다.
  - 잘못된 `--mode`면 2로 끝난다.
  - 자동 재시도는 하지 않는다(`start_job_run` 1회).

### Implementation for User Story 1

- [X] T011 [US1] `services/tms-silver/glue_tw_cems_ml_ready.py`를 작성한다(contracts/run-interface.md §1, R4·R6·R7).
  - `awsglue`를 import하지 않는다. `parse_known_args`를 쓴다. 인자는 계약표 그대로이고, `--files`는 1~32다.
  - Spark 설정: `spark.sql.session.timeZone=UTC`, `spark.sql.parquet.outputTimestampType=TIMESTAMP_MICROS`
  - build
    1. `latest.json`을 삭제한다(로컬은 파일 삭제, Glue는 boto3 `delete_object`).
    2. `spark.read.parquet(source)`로 Silver를 읽는다. `silver_months`와 `silver_rows`를 세고, 0이면 `empty silver input`으로 실패한다.
    3. `normalize` → 0행이면 `no ml-ready target rows` → `dedupe` → `add_features` → `select(COLUMNS)`. 컬럼이 다르면 `column contract mismatch`로 실패한다.
    4. `persist` → `repartitionByRange(files, "measured_at").sortWithinPartitions("measured_at","stack_code","item_code").write.mode("overwrite").parquet(output)`
    5. `ml_ready_stats`와 버전을 담아 `runs/<run_ts>.json`을 쓰고, 그다음 `latest.json`을 쓴다.
  - compare
    - `spark.sql.legacy.parquet.nanosAsLong=true`로 `--reference`를 읽는다.
    - `measured_at`이 long이면 `timestamp_micros(col / 1000)`으로 바꾼다. 원래 타입 문자열을 기록한다.
    - `ml_ready_spark.compare(output, reference)` → `compare/<run_ts>.json`
  - 요약 한 줄을 `print`한다(경로, 건수, `passed`, 소요 초). 값은 출력하지 않는다.
- [X] T012 [US1] `services/tms-silver/run_ml_ready.py`를 작성한다(contracts/run-interface.md §2).
  - `run_silver`에서 `estimate_cost`, `_log`, `POLL_SECONDS`, `FAILED_STATES`, `SUCCEEDED`를 import한다.
  - Job 이름 기본값은 `tms-silver-tw-cems-ml-ready`다. `--mode`, `--files`를 Job 인자로 넘긴다.
  - 끝나면 실행 기록(`latest.json` 또는 가장 최근 `compare/*.json`)을 읽어 출력한다.
- [X] T013 [US1] `infra/stacks/tms-silver/main.tf`에 ML-ready 역할을 추가한다(plan "부여 권한", R9). 004 리소스는 바꾸지 않는다.
  - `aws_iam_role.ml_ready`: 이름 `tms-glue-silver-ml-ready`, 설명(ASCII) `"TW CEMS ML-ready Glue job role (silver/tw_cems read, silver/tw_cems_ml_ready write)"`
  - `AWSGlueServiceRole`을 부착한다.
  - `aws_iam_role_policy.ml_ready_data`(이름 `tms-glue-silver-ml-ready-data`). sid는 고정한다.
    - `ListRawScoped`: 원본 버킷, prefix `silver/tw_cems`, `silver/tw_cems/*`, `silver/tw_cems_ml_ready`, `silver/tw_cems_ml_ready/*`, `silver/_runs/tw_cems_ml_ready/*`
    - `ReadSilverTwCems`: Get `silver/tw_cems/*`
    - `ReadOps`: Get `ops/glue-scripts/*`, `ops/glue-packages/*`
    - `ReadWriteMlReady`: Get·Put·Delete·AbortMultipartUpload `silver/tw_cems_ml_ready/*`, `silver/_runs/tw_cems_ml_ready/*`
    - `WriteMlReadyFolderMarker`: Get·Put·Delete `silver/tw_cems_ml_ready_$folder$`
    - `WriteSilverFolderMarker`: Get·Put `silver_$folder$` (Delete 없음)
    - `ListReference`: 정답지 버킷, prefix `ml_ready/*`
    - `ReadReference`: Get `arn:aws:s3:::smokestack-cems-local-eda-952900391026/ml_ready/*`
  - 확인할 것: `silver/tw_cems/*`에 Put·Delete가 없고, `bronze/`·`tms_cleansys/` 권한이 없다.
- [X] T014 [US1] `infra/stacks/tms-silver/main.tf`에 업로드 2개와 Job을 추가한다.
  - `aws_s3_object.ml_ready_module`: `ops/glue-scripts/ml_ready_spark.py`
  - `aws_s3_object.ml_ready_script`: `ops/glue-scripts/glue_tw_cems_ml_ready.py`
  - 둘 다 `etag = filemd5(...)`
  - `aws_glue_job.tw_cems_ml_ready`
    - 이름 `tms-silver-tw-cems-ml-ready`, Glue 5.0, G.1X, `number_of_workers = var.ml_ready_worker_count`, `timeout = 60`, `max_retries = 0`, `max_concurrent_runs = 1`
    - 로그 그룹은 004의 `/aws-glue/tms-silver`를 같이 쓴다.
    - `default_arguments`
      - `--extra-py-files = "s3://…/ops/glue-packages/smokestack_guard.zip,s3://…/ops/glue-scripts/ml_ready_spark.py"`
      - `--mode = "build"`, `--bucket`, `--source_prefix = "silver/tw_cems"`, `--table_prefix = "silver/tw_cems_ml_ready"`, `--runs_prefix = "silver/_runs/tw_cems_ml_ready"`, `--files = "6"`
      - `--reference = var.ml_ready_reference`, `--package_md5`
      - 공통 로그·지표 인자는 004 Job과 같다. `--TempDir`은 넣지 않는다.
- [X] T015 [P] [US1] `infra/stacks/tms-silver/variables.tf`와 `outputs.tf`를 수정한다.
  - 변수(`description`·`type`·기본값 필수)
    - `ml_ready_worker_count` = 10 (2~10 검증)
    - `ml_ready_reference` = `"s3://smokestack-cems-local-eda-952900391026/ml_ready/part.parquet"`
  - 출력: `ml_ready_job_name`, `ml_ready_role_arn`, `ml_ready_location`
- [X] T016 [US1] 로컬 검증(에이전트)
  - `pytest -q`(전체), `ruff check .`
  - `terraform fmt -recursive infra/`, `terraform.exe -chdir=infra/stacks/tms-silver validate`
  - **plan은 실행하지 않는다**(사용자 결정).
  - 사용자에게 `plan`에서 확인할 점을 정리해 준다: 생성만 있고 004 리소스 변경 0, 업로드 2개.
- [ ] T017 🧑 [US1] 사용자가 PowerShell에서 `terraform plan` → `apply`를 실행한다.
- [X] T018 🧑 [US1] build 실행(quickstart §3)
  - `run_ml_ready.py --mode build`
  - 실행 기록(`latest.json`)과 파일 목록을 받아 `plan.md`의 "실행 결과" 절에 기록한다.
  - 실측 시간·비용으로 R8을 고친다.
- [X] T019 🧑 [US1] compare 실행(quickstart §4)
  - `run_ml_ready.py --mode compare`
  - `passed: true`, `eligible_positive_rows = 135,978`을 확인한다.
  - 불일치가 있으면 `mismatch_samples`의 키로 원인을 찾고, 결과를 기록한다.
- [ ] T020 🧑 [US1] 같은 입력으로 build를 다시 실행한다. `latest.json` 건수가 모두 같은지 확인한다(SC-004).

**Checkpoint**: S3에 ML-ready 6개 파일과 `latest.json`이 있고, compare가 `passed: true`다.

---

## Phase 5: User Story 3 - E와 팀원이 ML-ready를 조회하고 학습에 쓴다 (Priority: P2)

**Goal**: Athena 테이블로 조회할 수 있고, 파일 구성이 학습에 맞다.

**Independent Test**: Athena 건수가 실행 기록과 같고, 파일 크기가 범위 안이다.

- [X] T021 [US3] `infra/stacks/tms-silver/main.tf`에 `aws_glue_catalog_table.tw_cems_ml_ready`를 추가한다(T013·T014 뒤, 같은 파일).
  - DB `tms_silver`, `EXTERNAL_TABLE`, **파티션 없음**
  - `location = "s3://…/silver/tw_cems_ml_ready/"`, Parquet SerDe(004 테이블과 같은 형식)
  - 컬럼 35개를 data-model.md §2 순서·타입 그대로 정의한다.
    - double: 4~29번 (`day_of_week`, `rise_count_3h`, `label_entry_60m` 포함)
    - boolean: 30~32번
    - string: 1·2·33~35번
    - timestamp: 3번
  - 설명: "읽기 전에 silver/_runs/tw_cems_ml_ready/latest.json 존재 확인"
  - T016 검증을 다시 실행한다.
- [ ] T022 🧑 [US3] Athena(`tms-eda`)에서 quickstart §6을 실행한다.
  - 건수가 실행 기록과 같은지 확인한다(SC-006).
  - 2023-12-01 06:30 행의 `ratio_lag_30m`이 null인지 확인한다.
  - `aws s3 ls --summarize`로 파일 수 6개, 각 128~256MB인지 확인한다(SC-005). 결과를 `plan.md`에 적는다.
- [ ] T023 [US3] PR 본문 초안에 E 확인 요청을 넣는다(SC-008).
  - 경로와 `latest.json` 확인 방법
  - `measured_at` 필터 예시
  - 분할 경계에 1시간 간격을 둘 것
  - `observed_risk_level`, 기준치 변경 플래그, 월 피처는 범위 밖이며 결정이 필요한 항목

---

## Phase 6: Polish & Cross-Cutting

- [X] T024 [P] `services/tms-silver/README.md`에 "ML-ready" 절을 추가한다.
  - 무엇을 하는지
  - 로컬 테스트
  - `run_ml_ready.py` build·compare 사용법
  - `latest.json` 의미
  - 규칙 기준은 C의 `ml_ready.py`라는 점
- [X] T025 [P] `.github/workflows/tms-silver.yml`이 새 테스트까지 도는지 확인한다(`paths`에 `services/tms-silver/**`, `src/smokestack_guard/silver/**`가 이미 있음). 바꿀 필요가 없으면 바꾸지 않는다.
- [X] T026 최종 확인(에이전트)
  - T016을 다시 실행한다.
  - `git diff --stat main...HEAD -- src/` 결과에 이 기능의 변경이 없는지 확인한다. #28 브랜치의 변경만 있어야 한다.
  - `tasks.md` 체크 상태를 갱신한다.
- [ ] T027 PR 본문 초안을 사용자에게 보여주고 허락을 받는다. 허락 전에는 생성하지 않는다.
  - base는 PR #31이 머지되기 전이면 #28 브랜치, 머지된 뒤면 `main`이다.
  - 담을 내용: spec 링크, `Closes #32`, 리뷰 요청(C: 계산 의미, E: 사용성), T023 내용, 실행 결과

---

## Dependencies & Execution Order

```
Phase 1 (T001 ∥ T002 ∥ T003)
  └▶ Phase 2 (T004 compare)
        └▶ Phase 3 US2: T005·T006 (테스트) → T007 (규칙) → T008 (통과)
              └▶ Phase 4 US1:
                    코드   T009 ∥ T010 (테스트) → T011 → T012
                    인프라 T013 → T014 → T015 (main.tf 순서대로)
                    → T016 → 🧑 T017 → 🧑 T018 → 🧑 T019 → 🧑 T020
              └▶ Phase 5 US3: T021 (T014 뒤, apply 전에 포함) → 🧑 T022 (T018 뒤) → T023
  └▶ Phase 6: T024 ∥ T025 → T026 → T027
```

- `main.tf`를 고치는 작업(T013, T014, T021)은 같은 파일이라 순서대로 한다. T021도 첫 `apply`(T017) 전에 끝내서 한 번에 적용한다.
- `ml_ready_spark.py`를 고치는 작업(T004, T007)도 순서대로 한다.

## Parallel Examples

- **Phase 1**: T001(pyproject), T002(fixture 생성 함수), T003(conftest)
- **US2**: T005와 T006은 같은 파일이라 한 번에 작성한다. 규칙 구현 T007과는 나눠서 테스트를 먼저 쓴다.
- **US1**: T009+T011(진입 스크립트), T010+T012(실행 명령), T013~T015(Terraform)를 세 갈래로 진행한다.
- **Phase 6**: T024, T025

## Implementation Strategy

1. **MVP = US2(T001~T008)**: 규칙이 pandas와 같다는 것을 로컬에서 먼저 증명한다. 이게 안 되면 나머지는 의미가 없다.
2. US1 코드와 Terraform(T009~T016, T021)을 끝내고 PR을 올린다. 리뷰는 C(계산 의미)와 E에게 받는다.
3. 🧑 `apply` → build → compare → 다시 build → Athena 순서로 운영 확인을 하고 결과를 기록한다.
4. **커밋 단위** (작업별, 사용자가 요청할 때만)
   - ① spec 문서
   - ② 테스트 fixture·설정
   - ③ 규칙 코드 + 테스트(US2)
   - ④ 진입 스크립트 + 테스트
   - ⑤ 실행 명령 + 테스트
   - ⑥ Terraform
   - ⑦ README
   - ⑧ 실행 결과 기록
