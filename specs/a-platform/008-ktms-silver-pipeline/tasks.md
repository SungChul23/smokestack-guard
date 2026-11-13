---
description: "008 K-TMS Silver·ML-ready 매일 갱신 파이프라인 작업 목록"
---

# Tasks: K-TMS Silver·ML-ready 매일 갱신 파이프라인

**Input**: `specs/a-platform/008-ktms-silver-pipeline/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: 자동 테스트를 둔다. spec과 plan이 다음을 요구하기 때문이다.
- 범위 교체(FR-009), 재실행 결과 같음(SC-004), 버전 고정(SC-005)
- ML-ready 앞뒤 범위 계산이 전체 계산과 같음(FR-005, research R6)
- 실패 기록(FR-017)

테스트 환경:
- 로컬 Spark 3.5.4 + Iceberg 1.7.1(Hadoop 카탈로그, 임시 폴더)
- boto3는 가짜 객체로 대신한다.
- 실행 환경: `services/tms-silver` dev 의존성(Python 3.11, Java 17)

**Organization**: 사용자 스토리별 단계, 순서는 **US1 → US2 → US3 → US4 → US5**.
- US1(매일 갱신)이 잡·인프라를 만든다.
- US2(처음 전체 생성)는 그 위에 실행 명령을 더한다.
- US3·US4는 US1 결과를 확인하는 작업이 대부분이다.
- US5는 인자 입구만 둔다.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 다른 파일이고 선행 작업이 없어 병렬 가능
- **[Story]**: US1(매일 갱신), US2(전체 생성), US3(최신본·버전 읽기), US4(실패 알림·재실행), US5(합성 입구)
- 🧑: **사람이 하는 작업**(`terraform plan/apply`, AWS 실행, Athena 조회). 에이전트는 실행하지 않는다.

## 경로와 규칙

- 코드: `services/tms-silver/`. C의 `src/smokestack_guard/silver/`는 **수정하지 않는다**. `ktms.read_bronze`, `ktms.to_silver`, `ktms.quality`, `ktms.last_complete_day`, `ktms.STACK`, `ml_ready.to_ml_ready`, `ml_ready.COLUMNS`를 import만 한다.
- 스택: `infra/stacks/tms-silver/`. 기존 CEMS 리소스는 바꾸지 않고 `ktms.tf`에 추가만 한다.
- 버킷 `smokestack-tms-raw-952900391026`:
  - 입력 `tms_cleansys/`: 읽기만
  - 출력 `silver2/ktms/`, `silver2/ktms_ml_ready/`
  - 실행 기록 `silver2/_runs/ktms/`, `silver2/_runs/ktms_ml_ready/`
- Iceberg 카탈로그 이름: 코드에서는 항상 `glue_catalog`다. Glue에서는 GlueCatalog, 로컬 테스트에서는 같은 이름의 Hadoop 카탈로그다. 테이블 식별자는 `glue_catalog.tms_silver2.ktms`처럼 쓴다.

---

## Phase 1: Setup

- [X] T001 `services/tms-silver/pyproject.toml`을 고친다. 다른 줄은 바꾸지 않는다.
  - `[tool.setuptools] py-modules`에 `ktms_pipeline`, `glue_ktms_silver`, `glue_ktms_ml_ready`, `run_ktms`를 추가한다.
  - `[tool.pytest.ini_options]`에 `markers = ["iceberg: 로컬 Iceberg jar가 필요한 통합 테스트 (pytest -m iceberg로 따로 실행)"]`을 추가한다.
- [X] T002 [P] `services/tms-silver/tests/ktms_cases.py`를 만든다. **가짜** K-TMS 데이터를 만드는 함수 두 개다. 실제 원본 값은 쓰지 않는다.
  - `snapshot_body(items: list[dict]) -> bytes`: 수집 원문 형식 `{"response": {"body": {"items": [...]}}}`를 gzip한 바이트를 돌려준다. item 키는 `area_nm`, `fact_manage_nm`, `stack_code`, `mesure_dt`(`"YYYY-MM-DD HH:MM"`), `nox_mesure_value`, `nox_exhst_perm_stdr_value`, `sox_mesure_value`, `sox_exhst_perm_stdr_value`다.
  - `build_silver() -> pd.DataFrame`: `to_silver` 출력과 같은 9컬럼(`area_nm`, `fact_manage_nm`, `stack_code`, `item`, `value`, `limit`, `status`, `ts_kst`, `ratio`) 가짜 Silver를 만든다. 굴뚝 2개 × `nox`·`sox`이고, 2026-11-01 00:00 ~ 2026-11-04 23:30의 30분 격자다. 담을 사례는 모듈 독스트링에 표로 적는다.
    1. 날짜 경계(11-02 21:30 ~ 11-03 00:30) 연속
    2. 30분 한 칸 공백
    3. 진입 1(85 → 88 → 92%), 진입 0, 현재 90% 이상
    4. 기준치가 바뀌는 칸 하나(`limit` 변경)
    5. `status != "ok"`인 칸(`checking`, `stopped`)
    6. ML 대상이 아닌 항목(`co`)
- [X] T003 [P] `services/tms-silver/tests/conftest.py`에 fixture 두 개를 추가한다. 기존 fixture(`spark` 등)는 바꾸지 않는다.
  - `fake_s3`: 메모리 dict 기반 가짜 S3 클라이언트. `get_paginator("list_objects_v2").paginate(Bucket, Prefix)`, `get_object(Bucket, Key)["Body"].read()`, `put_object(Bucket, Key, Body, ContentType)`를 지원한다. C의 `read_bronze(..., s3=fake_s3)`에 그대로 넣을 수 있어야 한다.
  - `iceberg_spark`(scope=session): `local[2]` SparkSession을 만든다. iceberg 표시 테스트만 쓴다.
    - `spark.jars.packages=org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.7.1`
    - `spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions`
    - `spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog`, `.type=hadoop`, `.warehouse=<tmp_path_factory 폴더>`
    - 세션 시간대 UTC는 기존 `spark` fixture와 같게 둔다.
    - 독스트링에 "같은 프로세스에서 `spark` fixture와 함께 쓰지 않는다(먼저 만든 세션에 jar가 붙지 않음). `pytest -m iceberg`로 따로 실행한다"고 적는다.
- [X] T004 [P] `.github/workflows/tms-silver.yml`의 `Test` 단계를 둘로 나눈다. 다른 단계는 그대로 둔다.
  1. `pytest -q -m "not iceberg"`
  2. `pytest -q -m iceberg`. 이름은 `Test (Iceberg)`이고, 주석에 "Maven에서 Iceberg 1.7.1 jar를 받는다(Glue 5.0과 같은 버전)"를 적는다.

---

## Phase 2: Foundational

**Purpose**: `ktms_pipeline.py`의 공통 함수. 두 잡과 `run_ktms.py`가 함께 쓴다. **이 단계가 끝나야 US 작업을 시작한다.**

- [X] T005 [P] `services/tms-silver/tests/test_ktms_pipeline.py`에 범위 계산 테스트를 쓴다(Spark 없음).
  - `resolve_range("auto", "auto", now=2026-11-12T18:00Z)`: `DayRange(2026-11-11, 2026-11-12)` (KST 11-13 03:00 실행)
  - `now=2026-11-12T14:59Z`(KST 11-12 23:59): end는 11-11
  - 한쪽만 `auto`이면 `ValueError`
  - `start > end`이면 `ValueError`
  - `end > last_complete_day(now)`(오늘 KST 포함)이면 `ValueError`
  - `max_days=7`에서 8일이면 `ValueError`, `max_days=None`이면 통과
  - `ingest_dates(DayRange(11-11, 11-12), now=2026-11-12T18:00Z) == (11-10, 11-12)`, 과거 범위 `DayRange(11-01, 11-03)`이면 `(10-31, 11-04)`
  - `ml_ready_window(DayRange(11-11, 11-12)) == (2026-11-10 21:30, 2026-11-13 00:30)`, 양 끝 포함
- [X] T006 `services/tms-silver/ktms_pipeline.py`에 범위 부분을 구현한다. 독스트링에 spec·research 경로를 적는다.
  - `@dataclass(frozen=True) class DayRange: start: date; end: date`
    - 속성 `days`(일수), `start_ts`(start 00:00 naive), `end_ts`(end + 1일 00:00 naive)
    - `to_dict() -> {"start": "YYYY-MM-DD", "end": ...}`
  - `resolve_range(start: str, end: str, now: datetime | None = None, max_days: int | None = None) -> DayRange`
    - `auto`는 `ktms.last_complete_day(now)`를 end로, `start = end − 1`로 둔다.
    - 검사 규칙은 data-model §5 그대로: "`start ≤ end ≤ last_complete_day()`", Silver는 "`end − start + 1 ≤ max_days`".
  - `ingest_dates(r: DayRange, now: datetime | None = None) -> tuple[date, date]`: `(r.start − 1, min(r.end + 1, now의 UTC 날짜))` (research R6)
  - `ml_ready_window(r: DayRange) -> tuple[datetime, datetime]`: `(r.start_ts − 150분, r.end_ts + 30분)`, 양 끝 포함 (data-model §3)
  - T005가 통과해야 한다.
- [X] T007 [P] `services/tms-silver/tests/test_ktms_pipeline.py`에 원본 경로 검사 테스트를 쓴다.
  - `check_source_prefix("tms_cleansys/")`는 통과한다.
  - `check_source_prefix("tms_synthetic/", read_bronze=<prefix 인자 없는 함수>)`는 `ValueError`이고, 메시지에 `"C의 read_bronze에 경로 인자 필요"`가 들어 있다.
  - `prefix` 인자가 있는 가짜 함수를 넣으면 통과한다.
- [X] T008 `services/tms-silver/ktms_pipeline.py`에 `DEFAULT_SOURCE_PREFIX = "tms_cleansys/"`와 `check_source_prefix(prefix: str, read_bronze=ktms.read_bronze) -> None`을 구현한다. 기본 경로가 아니면 `inspect.signature(read_bronze).parameters`에 `prefix`가 있어야 한다(research R9). T007이 통과해야 한다.
- [X] T009 `services/tms-silver/ktms_pipeline.py`에 테이블 정의를 구현한다(data-model §2·§3).
  - Spark `StructType` 두 개 (pyspark를 늦게 import하려고 함수 `silver_schema()`, `ml_ready_schema()`로 구현):
    - `SILVER_SCHEMA`: 9컬럼, 순서는 `to_silver` 출력과 같다. `ts_kst`는 `TimestampNTZType`, `value`·`limit`·`ratio`는 `DoubleType`, 나머지는 `StringType`
    - `ML_READY_SCHEMA`: `ml_ready.COLUMNS` 순서. `measured_at`은 `TimestampNTZType`이고, 피처·라벨 26개는 double, `*_valid`·`*_eligible` 3개는 boolean, 그 밖은 string. 타입은 `infra/stacks/tms-silver/main.tf`의 `ml_ready_columns`와 같아야 한다.
  - `table_ddl(table: str, schema: StructType, ts_col: str, location: str | None) -> str`
    - 결과: `CREATE TABLE IF NOT EXISTS <table> (<컬럼>) USING iceberg PARTITIONED BY (days(<ts_col>)) [LOCATION '<location>'] TBLPROPERTIES ('format-version'='2', 'write.distribution-mode'='hash', 'write.parquet.compression-codec'='zstd')`
    - 컬럼 이름은 백틱으로 감싼다(`limit`이 예약어). `location`이 None이면 LOCATION을 넣지 않는다(로컬).
  - `table_location(bucket: str, table: str) -> str`: `tms_silver2.ktms`이면 `s3://<bucket>/silver2/ktms`다. AGENTS.md 규칙 "`silver2/<테이블>/` = `tms_silver2.<테이블>`"에 따른다.
- [X] T010 `services/tms-silver/ktms_pipeline.py`에 Spark·Iceberg 부분을 구현한다.
  - `build_spark(app: str) -> SparkSession`: `getOrCreate`하고 `spark.sql.session.timeZone=UTC`로 둔다. 카탈로그 설정은 Glue에서는 잡 인자 `--conf`, 로컬에서는 fixture가 한다. 여기서는 넣지 않는다.
  - `to_spark(spark, pdf: pd.DataFrame, schema: StructType) -> DataFrame`: `pdf[schema.fieldNames()]`를 `createDataFrame(..., schema=schema)`로 바꾼다. NaN은 null로, 문자열 컬럼은 `astype(object)`로 둔다.
  - `overwrite_range(df: DataFrame, table: str, ts_col: str, r: DayRange, props: dict[str, str]) -> int`
    - `ts_col`이 `[r.start_ts, r.end_ts)`인 행만 남긴다. 0행이면 `ValueError("empty result")`를 쓰기 전에 던진다.
    - `df.writeTo(table)`에 `option(f"snapshot-property.{k}", v)`를 붙여 `.overwrite((col >= lit(start_ts)) & (col < lit(end_ts)))`로 쓴다. lit은 `timestamp_ntz`로 캐스팅한다.
    - 돌려주는 값은 커밋된 `snapshot_id`다(research R5).
  - `latest_snapshot_id(spark, table) -> int | None`: `SELECT snapshot_id FROM <table>.snapshots ORDER BY committed_at DESC LIMIT 1`
- [X] T011 `services/tms-silver/ktms_pipeline.py`에 실행 기록 부분을 구현한다(contracts/run-interface.md §3).
  - `run_record_key(runs_prefix, started_at, job_run_id) -> str`: `<prefix>/<YYYYMMDDTHHMMSSZ>_<job_run_id>.json`
  - `runtime_versions(spark) -> dict`: spark, python, pandas, numpy. import에 실패하면 `"missing"`이다.
  - `write_run_record(record: dict, bucket: str, key: str, s3=None, local_dir: Path | None = None)`: `local_dir`가 있으면 파일로, 없으면 S3 `put_object`로 쓴다. 본문은 JSON(`ensure_ascii=False`)이다.
  - `failure_record(base: dict, exc: BaseException) -> dict`: `result="failed"`, `error="<예외 이름>: <메시지 첫 줄>"`이고, 데이터 값은 넣지 않는다.
- [X] T012 [P] `services/tms-silver/tests/test_ktms_iceberg.py`(`pytestmark = pytest.mark.iceberg`, fixture `iceberg_spark`)에 Iceberg 동작 테스트를 쓴다. 가짜 Silver는 T002의 `build_silver()`를 쓴다.
  - `test_overwrite_range_keeps_other_days`: 11-01 ~ 11-04를 쓴 뒤 11-02 ~ 11-03만 값을 바꿔 다시 쓰면, 11-01·11-04는 그대로이고 11-02·11-03은 새 값이다.
  - `test_overwrite_is_idempotent`: 같은 입력으로 두 번 쓰면 내용이 같다(정렬 후 `assert_frame_equal`, SC-004).
  - `test_snapshot_read_is_stable`: 첫 `snapshot_id`로 읽은 결과가 두 번째 쓰기 뒤에도 같다(SC-005).
  - `test_empty_result_does_not_commit`: 범위 밖 행만 넘기면 `ValueError`가 나고 `latest_snapshot_id`가 바뀌지 않는다(FR-010).
  - `test_range_deletes_rows_missing_from_new_result`: 11-02의 한 굴뚝을 빼고 다시 쓰면 그 굴뚝의 11-02 행이 없어진다.
  - `test_ddl_partition_and_columns`: `table_ddl`로 만든 테이블의 컬럼 순서·타입이 스키마와 같고, `partitions` 메타 테이블이 날짜 단위다.

**Checkpoint**: `pytest -m "not iceberg"`와 `pytest -m iceberg`가 모두 통과한다.

---

## Phase 3: User Story 1 - 매일 최신 K-TMS 학습 테이블이 준비된다 (P1) 🎯 MVP

**Goal**: 매일 03:00 KST에 끝난 최근 2일의 Silver·ML-ready가 다시 계산되어 교체된다.

**Independent Test**:
- 로컬: 가짜 원본으로 두 잡을 `--local` 실행하면 대상 2일만 쓰이고 35컬럼이 맞다.
- AWS: 하루치 시험 실행 결과(quickstart §2)

### Tests for User Story 1

- [X] T013 [P] [US1] `services/tms-silver/tests/test_ktms_pipeline.py`에 `test_ml_ready_context_equivalence`를 쓴다(research R6, T-ML-1).
  - 대상: `build_silver()`, `DayRange(11-02, 11-03)`
  - 전체 계산: `to_ml_ready(전체 silver)`를 대상 범위로 거른 결과
  - 창 계산: `ml_ready_window` 범위의 silver만 `to_ml_ready`에 넣고 대상 범위로 거른 결과
  - 두 결과가 35컬럼 모두 같아야 한다(키 정렬 후 `assert_frame_equal`, NaN끼리 같음).
  - 창을 한 칸(30분) 줄이면 다르다는 것도 확인해 테스트가 경계를 실제로 검사하는지 보인다.
- [X] T014 [P] [US1] `services/tms-silver/tests/test_glue_ktms_silver.py`(iceberg)에 Silver 잡 테스트를 쓴다.
  - 준비: `fake_s3`에 UTC 수집일 11-10 ~ 11-13 폴더를 만든다(`tms_cleansys/ingest_date=…/hour=…/run_ts=…/snapshot.json.gz` + `_SUCCESS`). `_SUCCESS`가 없는 폴더 하나와, 같은 측정 시각이 나중 스냅샷에서 `checking → stopped`로 바뀌는 칸 하나를 둔다.
  - `main([... "--start_date","2026-11-11","--end_date","2026-11-12","--local","--runs_dir",tmp], s3=fake_s3, now=…)`를 실행한다.
  - 기대:
    - 테이블에 `ts_kst` 날짜 11-11·11-12만 있다.
    - 표지 없는 폴더의 값이 없다.
    - 고쳐진 칸은 `stopped`다(US1-2).
    - 실행 기록 `result="succeeded"`이고, `rows`가 테이블 행 수와 같고, `snapshot_id`가 테이블 최신값과 같다.
- [X] T015 [P] [US1] `services/tms-silver/tests/test_glue_ktms_ml_ready.py`(iceberg)에 ML-ready 잡 테스트를 쓴다.
  - 준비: `build_silver()`를 Silver 테이블에 쓴다.
  - 실행: `--start_date 2026-11-02 --end_date 2026-11-03`
  - 기대:
    - 결과 컬럼이 `ml_ready.COLUMNS`와 이름·순서가 같다.
    - `measured_at` 날짜는 11-02·11-03뿐이다.
    - 값이 T013의 전체 계산 결과와 같다.
    - 실행 기록에 `classification_eligible`, `regression_eligible`, `positives`가 있다.

### Implementation for User Story 1

- [X] T016 [US1] `services/tms-silver/glue_ktms_silver.py`를 만든다(Glue 진입 겸 로컬). 인자는 contracts/run-interface.md §2를 따른다.
  - `parse_args`:
    - 인자: `--start_date`, `--end_date`(기본 `auto`), `--bucket`, `--source_prefix`(기본 `tms_cleansys/`), `--silver_table`(기본 `tms_silver2.ktms`), `--runs_prefix`(기본 `silver2/_runs/ktms`), `--max_days`(기본 7), `--package_md5`, `--sfn_execution`(기본 `manual`), `--JOB_RUN_ID`(기본 `local`), `--local`, `--runs_dir`
    - `parse_known_args`로 Glue가 넘기는 인자는 무시한다.
  - `main(argv=None, s3=None, now=None) -> dict` 순서:
    1. 인자 검사: `resolve_range`(max_days), `check_source_prefix`
    2. `ktms.read_bronze(bucket, *ingest_dates(r, now), s3=s3)`. 0행이면 `ValueError("no snapshots")`
    3. `ktms.to_silver`
    4. `ktms.quality`
    5. `ensure` DDL(`table_ddl`, Glue면 `table_location`)
    6. `overwrite_range(to_spark(...), "glue_catalog."+table, "ts_kst", r, {"job_run_id", "range"})`
    7. 성공 기록
  - 예외가 나면 `failure_record`를 쓰고 다시 던진다(FR-017).
  - 실행 기록에는 `empty_days`(범위 안인데 행이 0인 날짜)와 C의 `quality()` 필드를 넣는다.
  - 로그에는 요약 JSON 한 줄(범위, 행 수, `snapshot_id`, 소요 시간)만 남기고 데이터 값은 남기지 않는다.
  - T014가 통과해야 한다.
- [X] T017 [US1] `services/tms-silver/glue_ktms_ml_ready.py`를 만든다.
  - 인자: `--start_date`, `--end_date`, `--silver_table`(기본 `tms_silver2.ktms`), `--ml_ready_table`(기본 `tms_silver2.ktms_ml_ready`), `--runs_prefix`(기본 `silver2/_runs/ktms_ml_ready`), 그리고 공통 인자. `max_days` 제한은 없다.
  - 순서:
    1. Silver 테이블에서 `ml_ready_window` 범위(양 끝 포함)를 읽어 `toPandas()` 한다.
    2. 0행이면 실패한다.
    3. `ml_ready.to_ml_ready`
    4. `ML_READY_SCHEMA`로 `overwrite_range(..., "measured_at", r, ...)`
    5. 성공 기록: `input_rows`, `classification_eligible`, `regression_eligible`, `positives`(`label_entry_60m == 1` & `classification_eligible`)
  - 실패 처리는 T016과 같다. T015가 통과해야 한다.
- [X] T018 [US1] `infra/stacks/tms-silver/variables.tf`에 변수 두 개를 추가한다. `description`과 `type`을 쓴다.
  - `ktms_schedule_enabled`(bool, 기본 false): 전체 생성이 끝나기 전에는 끈다.
  - `ktms_worker_count`(number, 기본 2): G.1X 작업자 수. Glue 최소 2
- [X] T019 [US1] `infra/stacks/tms-silver/ktms.tf`에 Glue 부분을 만든다. 맨 위 주석에 spec 경로와 "C 코드 수정 없음, 테이블은 잡 DDL이 만든다(plan Complexity Tracking)"를 적는다.
  - `locals`:
    - `ktms_silver_table = "silver2/ktms"`, `ktms_ml_ready_table = "silver2/ktms_ml_ready"`
    - 실행 기록 경로 2개
    - `ktms_iceberg_conf`: `--conf` 값 한 줄. `spark.sql.extensions=…IcebergSparkSessionExtensions --conf spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog --conf spark.sql.catalog.glue_catalog.catalog-impl=org.apache.iceberg.aws.glue.GlueCatalog --conf spark.sql.catalog.glue_catalog.io-impl=org.apache.iceberg.aws.s3.S3FileIO --conf spark.sql.catalog.glue_catalog.warehouse=s3://<버킷>/silver2/ --conf spark.sql.session.timeZone=UTC`
  - `aws_s3_object` 3개: `ops/glue-scripts/glue_ktms_silver.py`, `glue_ktms_ml_ready.py`, `ops/glue-packages/ktms_pipeline.py`. etag는 `filemd5`
  - IAM 역할 2개(`tms-glue-silver2-ktms`, `tms-glue-silver2-ktms-ml-ready`): 신뢰 관계는 기존 `glue_assume`, `AWSGlueServiceRole`을 붙인다. 인라인 정책은 plan "IAM 권한 목록" 표 그대로 쓰고, 기존 `silver2_data` 정책 문서 형식을 따른다.
    - Silver 역할만 `tms_cleansys/*` `GetObject`를 가진다. 원본 쓰기·삭제 권한은 어느 역할에도 없다.
    - Glue 카탈로그 ARN: `catalog`, `database/tms_silver2`, `table/tms_silver2/<테이블>`
  - `aws_glue_job` 2개(`tms-silver2-ktms`, `tms-silver2-ktms-ml-ready`):
    - `glue_version = "5.0"`, `G.1X`, `var.ktms_worker_count`, `timeout = 60`, `max_concurrent_runs = 1`
    - 로그 그룹은 기존 `aws_cloudwatch_log_group.glue`
    - `default_arguments`: 기존 공통 인자 + `--datalake-formats = "iceberg"`, `--conf = local.ktms_iceberg_conf`, `--extra-py-files = <C zip>,<ktms_pipeline.py>`, `--package_md5 = data.archive_file.package.output_md5`, 그리고 contracts §2의 기본값
- [X] T020 [P] [US1] `infra/stacks/tms-silver/ktms_pipeline.asl.json`을 만든다(`templatefile` 변수 `silver_job`, `ml_ready_job`, `topic_arn`). research R8 구조를 따른다.
  1. `Defaults`(Pass): `States.JsonMerge({"start_date":"auto","end_date":"auto","stage":"all"}, $$.Execution.Input, false)`
  2. `RouteStart`(Choice): `stage == "ml_ready"`이면 `MlReady`로 간다.
  3. `Silver`(`arn:aws:states:::glue:startJobRun.sync`): 인자 `--start_date`, `--end_date`, `--sfn_execution`(`$$.Execution.Name`)
  4. `RouteAfterSilver`(Choice): `stage == "silver"`이면 `Done`으로 간다.
  5. `MlReady`: 3과 같은 인자
  6. `Done`(Succeed)
  - 두 Task의 `Retry`:
    - `Glue.ConcurrentRunsExceededException`: 120초 × 5회
    - `States.ALL`: 60초 × 1회
  - `Catch`는 `Notify`(`arn:aws:states:::sns:publish`, Subject `[tms] K-TMS silver2 failed`(SNS 제목은 ASCII만 허용), Message에 실행 이름·단계·`$.error.Error`·`$.error.Cause` 앞부분)로 간 뒤 `Failed`(Fail)로 끝난다.
- [X] T021 [US1] `infra/stacks/tms-silver/ktms.tf`에 흐름 부분을 추가한다.
  - `data "aws_sns_topic" "alerts" { name = "tms-collector-alerts" }`
  - Step Functions 역할 `tms-sfn-silver2-ktms`: `glue:StartJobRun`·`GetJobRun`·`GetJobRuns`·`BatchStopJobRun`(잡 2개), `sns:Publish`(토픽 1개)
  - `aws_sfn_state_machine` `tms-silver2-ktms`: STANDARD, `templatefile`로 T020 정의를 읽는다.
  - Scheduler 역할 `tms-scheduler-silver2-ktms`: `states:StartExecution`(상태 머신 1개)
  - `aws_scheduler_schedule` `tms-silver2-ktms-daily`
    - `cron(0 3 * * ? *)`, `Asia/Seoul`, 유연한 시간 창 OFF
    - `state = var.ktms_schedule_enabled ? "ENABLED" : "DISABLED"`
    - 대상 입력 `{}`
  - `outputs.tf`에 상태 머신 ARN과 잡 이름 2개를 추가한다.
- [X] T022 [P] [US1] `services/tms-silver/tests/test_ktms_asl.py`에 ASL 테스트를 쓴다. ASL 파일의 `${...}`를 가짜 값으로 바꿔 JSON으로 읽는다.
  - 모든 `Next`와 `Default`가 존재하는 상태를 가리킨다.
  - 두 Glue Task에 위 Retry 두 개와 `Catch → Notify`가 있다.
  - `stage`별 경로: `all`은 Silver → MlReady, `silver`는 Silver → Done, `ml_ready`는 MlReady만
- [X] T023 [US1] `infra/stacks/tms-silver`에서 `terraform fmt -recursive`와 `terraform validate`를 실행한다(WSL `/mnt/c/terraform/terraform.exe`). `plan`은 실행하지 않는다.
- [X] T024 🧑 [US1] PowerShell에서 `terraform plan`을 확인한다. 추가만 있고(Glue 잡 2, 역할 4, 상태 머신, 스케줄 DISABLED, S3 객체 3), 기존 CEMS 리소스 변경이 없어야 한다. 그다음 `terraform apply`를 실행한다.
- [X] T025 🧑 [US1] quickstart §2 하루치 시험(`run_ktms.py rerun --from 2026-11-11 --to 2026-11-11`, T027 뒤에 실행)을 한다. 실행 기록의 `versions.pandas`, `AccessDenied` 여부, 실행 시간, driver 메모리를 확인해 plan "남은 확인"에 결과를 적는다.

**Checkpoint**: 하루치가 AWS에서 Silver → ML-ready로 만들어지고 Athena로 읽힌다.

---

## Phase 4: User Story 2 - 쌓인 기간 전체를 처음 한 번 만든다 (P1)

**Goal**: 2026-10-30부터 어제까지 Silver·ML-ready를 한 번에 채운다.

**Independent Test**: 날짜별 행 수와 `status` 분포, ML-ready 학습 가능 행·양성 수가 PR #45 수치와 같다(SC-001·002).

- [X] T026 [P] [US2] `services/tms-silver/tests/test_run_ktms.py`에 테스트를 쓴다. 가짜 `stepfunctions`·`s3` 클라이언트를 쓰고 sleep은 주입한다.
  - `plan_backfill(date(2026,10,30), date(2026,11,12), chunk_days=5)`
    - 결과: `[silver 10-30~11-03, silver 11-04~11-08, silver 11-09~11-12, ml_ready 10-30~11-12]`
  - `backfill`
    - 실행을 순서대로 하나씩 시작한다(앞 실행이 `SUCCEEDED`일 때만 다음).
    - 하나가 `FAILED`이면 멈추고 종료 코드 1
    - `--dry-run`은 API를 호출하지 않는다.
  - `rerun`: 입력 `{"start_date","end_date","stage"}`를 그대로 넘긴다.
  - 실행 이름: `ktms-<stage>-<start>-<end>-<UTC 초>`(80자 이하, 허용 문자만)
  - `runs --table ktms --last 5`: `silver2/_runs/ktms/`의 최근 키 5개를 읽어 표로 출력한다(결과, 범위, 행 수, `snapshot_id`).
- [X] T027 [US2] `services/tms-silver/run_ktms.py`를 구현한다(contracts §4).
  - 하위 명령: `backfill`(`--from`, `--to`, `--chunk-days` 기본 5, `--dry-run`), `rerun`(`--from`, `--to`, `--stage`), `runs`(`--table`, `--last`)
  - 공통 옵션: `--state-machine-arn`(기본은 계정·리전·`tms-silver2-ktms`로 만든 ARN), `--profile`, `--region`
  - 30초마다 `describe_execution`으로 상태를 보고, 끝나면 소요 시간을 출력한다. 자격증명은 코드에 쓰지 않는다.
  - T026이 통과해야 한다.
- [X] T028 🧑 [US2] quickstart §3을 진행한다. `backfill --dry-run`으로 묶음 계획을 보고, `backfill`을 실행한다.
- [X] T029 🧑 [US2] Athena로 SC-001(10-31 ~ 11-10 Silver 3,304,429행, `status` 분포)과 SC-002(eligible 956,194, positives 3,768, 컬럼 순서)를 확인한다. 차이가 있으면 날짜별로 좁혀 C와 확인한다.

**Checkpoint**: 과거 전체가 테이블에 있고, C의 로컬 결과와 맞는다.

**결과 (2026-11-13)**: 백필 10-30 ~ 11-12 완료.
- Silver 10-31 ~ 11-10: 3,304,429행으로 PR #45와 같다(SC-001).
- ML-ready 10-31 ~ 11-10: eligible 969,137 / positives 3,804로 PR #45(956,194 / 3,768)보다 많다. 차이는 범위 경계 칸 때문이다.
  - 10-31 00:00 ~ 02:00, 11-10 23:00 ~ 23:30 경계 칸: eligible 12,950 / positives 43. 우리 쪽은 앞뒤 날짜가 있어 학습 가능해졌다.
  - 경계를 뺀 안쪽: 956,187 / 3,761. C보다 7행(모두 양성) 적다. 경계 쿼리가 11-10 23:00을 통째로 뺐기 때문이다. C 로컬에서도 23:00은 +30분(23:30)만으로 진입이 확인되면 양성 라벨이 붙는다. 같은 규칙으로 계산한 결과로 본다(SC-002).
  - 시리즈 수(굴뚝 × NOx·SOx): 3,559

---

## Phase 5: User Story 3 - E가 최신본과 과거 버전을 읽는다 (P2)

**Goal**: 읽는 법과 버전 고정 방법이 문서로 있고 실제로 동작한다.

**Independent Test**: 기록한 `snapshot_id`로 읽은 결과가 이후 갱신 뒤에도 같다(SC-005).

- [X] T030 [US3] `services/tms-silver/README.md`에 "K-TMS (008)" 절을 추가한다.
  - 파일 표(`ktms_pipeline.py`, 두 잡, `run_ktms.py`)
  - 테스트 실행법(`-m "not iceberg"`, `-m iceberg`)
  - 실행 명령 예시
  - 읽는 법 요약과 `contracts/ktms-tables.md` 링크
  - "S3 Parquet을 직접 읽지 말 것"
- [ ] T031 🧑 [US3] quickstart §5를 진행한다. 전체 생성 직후 `ktms_ml_ready`의 `snapshot_id`와 행 수·합계를 적어 두고, 매일 실행 3번 뒤 같은지 확인한다.

---

## Phase 6: User Story 4 - 실패를 알고 다시 돌린다 (P2)

**Goal**: 실패하면 재시도 1회 뒤 메일이 오고, 테이블은 그대로이며, 범위를 지정해 다시 돌릴 수 있다.

**Independent Test**: 원본이 없는 과거 범위로 실행하면 실패 기록, 알림, 테이블 변경 없음이 확인된다(SC-006).

- [X] T032 [P] [US4] `services/tms-silver/tests/test_glue_ktms_silver.py`(iceberg)에 실패 테스트를 추가한다.
  - 원본이 없는 범위: `ValueError("no snapshots")`가 다시 던져진다.
  - 실행 기록 `result="failed"`이고 `error`가 채워진다.
  - `latest_snapshot_id`가 바뀌지 않는다.
  - 인자 오류(`start > end`)도 실패 기록을 남긴다.
- [X] T033 [P] [US4] `services/tms-silver/tests/test_glue_ktms_ml_ready.py`(iceberg)에 실패 테스트를 추가한다. Silver 테이블에 범위 행이 없으면 실패하고 ML-ready 테이블은 그대로다.
- [ ] T034 🧑 [US4] quickstart §6을 진행한다(`rerun --from 2026-10-01 --to 2026-10-01`). 재시도 1회, 10분 안 메일, ML-ready 미실행, 실패 기록 2개, `snapshot_id` 변화 없음을 확인한다.

---

## Phase 7: User Story 5 - 합성 데이터를 같은 경로로 처리할 수 있다 (P3)

**Goal**: 인자 입구만 둔다. 합성 잡·테이블·권한은 만들지 않는다(research R9). **B의 진행에 따라 바뀔 수 있다.**

**Independent Test**: 합성 경로로 실행하면 읽기 전에 분명한 메시지로 실패하고, 실측 테이블은 그대로다.

- [X] T035 [P] [US5] `services/tms-silver/tests/test_glue_ktms_silver.py`(iceberg)에 테스트를 추가한다. `--source_prefix tms_synthetic/ --silver_table tms_silver2.ktms_synthetic`로 실행하면 `ValueError`에 `"C의 read_bronze에 경로 인자 필요"`가 들어 있다. 실측 테이블 `snapshot_id`는 바뀌지 않고, 합성 테이블은 생기지 않는다(검사가 DDL보다 먼저).
- [X] T036 [US5] `specs/a-platform/008-ktms-silver-pipeline/research.md` R9 "나중에 할 것"에 착수 조건과 할 일을 체크 목록 없이 문장으로 적는다.
  - 착수 조건: C의 `read_bronze` 경로 인자, B의 업로드 시작
  - 할 일: 합성 잡 2개, 상태 머신, 권한 `tms_synthetic/*` 읽기와 `silver2/ktms_synthetic*` 쓰기, 계약 문서 §6 갱신

---

## Phase 8: Polish & Cross-Cutting

- [X] T037 [P] `AGENTS.md`를 고친다(research R13, FR-021).
  - "S3 경로 규칙"에 Iceberg 예외 문단을 추가한다. 내용: `tms_silver2.ktms`, `ktms_ml_ready`는 테이블 형식의 날짜 파티션을 쓰고, Spark·pandas·Athena 모두 카탈로그로 읽는다. 계약 링크도 넣는다.
  - 기존 "Spark는 Silver를 카탈로그가 아니라 S3 경로로 읽는다" 줄에 "(Iceberg 테이블 제외)"를 붙인다.
  - "저장소 구조"의 `tms-silver/` 설명에 "K-TMS Silver·ML-ready(Iceberg, 매일)"를 추가한다.
  - `.claude/settings.json`은 바꾸지 않는다.
- [X] T038 [P] `infra/stacks/tms-silver`의 스택 주석(main.tf 맨 위 또는 `ktms.tf`)과 `services/tms-silver/pyproject.toml`의 `description`을 K-TMS 포함으로 고친다.
- [X] T039 `services/tms-silver`에서 `ruff check .`, `pytest -q -m "not iceberg"`, `pytest -q -m iceberg`를 실행해 모두 통과하는지 확인한다.
- [ ] T040 🧑 quickstart §7을 진행한다. `ktms_schedule_enabled = true`로 `apply`하고, 7일 연속 성공(SC-003)을 확인한다.
- [ ] T041 🧑 quickstart §8로 원본 쓰기 0을 확인한다(SC-007).
- [ ] T042 🧑 C에게 테이블 형식·파티션 리뷰를 요청하고(원칙 IV), 합성 데이터를 올릴 시점에 `read_bronze` 경로 인자를 요청한다. E에게 `contracts/ktms-tables.md`를 공유한다(카탈로그로 읽기, `snapshot_id` 기록, `month_*` 드랍).
- [ ] T043 `specs/a-platform/008-ktms-silver-pipeline/spec.md`의 Status를 결과에 맞게 바꾼다(배포, 전체 생성 완료 등). plan "남은 확인"에 첫 실행 결과(pandas 버전, 메모리, 시간, 비용)를 적는다.

---

## Dependencies & Execution Order

```
Phase 1 (T001~T004)
   ▼
Phase 2 (T005~T012)  ← 모든 US의 선행
   ▼
US1 코드 (T013~T017) ─┬─ US1 인프라 (T018~T023) ─▶ 🧑 T024 apply
                      │
US2 코드 (T026~T027) ─┘  (US1 잡이 있어야 의미가 있지만 코드는 병렬 가능)
   ▼
🧑 T025 하루치 시험 → 🧑 T028~T029 전체 생성·비교 → 🧑 T031·T034 → 🧑 T040 스케줄 켜기
US3 문서(T030), US4 테스트(T032~T033), US5(T035~T036), T037~T039: Phase 2 뒤 언제든
```

- US1 → US2: `run_ktms.py`가 US1의 상태 머신을 실행한다. 사람 작업 T025가 T027을 쓰므로 코드는 T027까지 먼저 끝낸다.
- US3·US4는 US1 잡에 테스트와 확인만 더한다.
- US5는 US1 잡의 인자 검사에만 의존한다.

## Parallel Opportunities

- Phase 1: T002, T003, T004
- Phase 2: T005·T007·T012(테스트 먼저) 병렬. 구현 T006 → T008 → T009 → T010 → T011은 같은 파일이라 순서대로
- US1: 테스트 T013·T014·T015 병렬. T020(ASL)·T022(ASL 테스트)는 Python 작업과 병렬
- 나머지: T026(US2 테스트), T030, T032·T033, T035, T037·T038 병렬

예시(US1 시작 시):

```
동시에: T013 (ML-ready 창 동등성), T014 (Silver 잡 테스트), T015 (ML-ready 잡 테스트), T020 (ASL)
이어서: T016 → T017,  T018 → T019 → T021 → T022 → T023
```

## Implementation Strategy

1. **MVP = Phase 1 + 2 + US1 코드·인프라 + US2 `run_ktms.py`**
   - 이 단위로 PR을 올린다(spec·plan·tasks 포함).
   - 머지 뒤 사람이 apply, 하루치 시험, 전체 생성을 한다.
2. **검증**: SC-001·002(T029)가 맞을 때까지 스케줄을 켜지 않는다.
3. **운영**: 스케줄을 켜고(T040) 7일을 지켜본 뒤 SC-003·005·007을 확인한다.
4. **합성**: US5는 입구만 이번 PR에 넣는다. 실제 합성 처리는 C·B 준비 뒤 별도 이슈로 한다.
