---
description: "004 TW CEMS Silver 클라우드 실행 작업 목록"
---

# Tasks: TW CEMS Silver 클라우드 실행 (Glue, 36개월)

**Input**: `specs/a-platform/004-tw-cems-silver-glue/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: 자동 테스트를 둔다. spec이 다음을 결과로 확인하도록 요구하기 때문이다.
- 다른 달 행 차단(FR-004)
- 그 달만 교체(US1-4, SC-004)
- 실행 기록(FR-010)

테스트 도구는 두 가지다.
- 진입 스크립트: pytest + 로컬 Spark 3.5.4(Docker `sg-spark:3.5` 또는 CI의 Java 17)
- 일괄 실행 명령: pytest + boto3 mock

**Organization**: 사용자 스토리별 단계.
- US1(36개월 실행), US2(SQL 조회), US3(원본 안전)는 모두 P1이다.
- US2의 확인과 US3의 실행 전후 비교는 US1의 실행 결과가 필요하다. 그래서 **US1 → US2, US3** 순서로 둔다.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 다른 파일이고 선행 작업이 없어 병렬 가능
- **[Story]**: US1(36개월 실행), US2(SQL 조회), US3(원본 안전)
- 🧑 표시는 **사람이 하는 작업**(`apply`, Job 실행, Athena 조회, AWS 확인). 에이전트는 실행하지 않는다.

## 경로

- 스택: `infra/stacks/tms-silver/`
- 코드: `services/tms-silver/`
- 규칙 코드(C, 읽기만): `src/smokestack_guard/silver/tw_cems.py`, `tw_cems_spark.py`. **이 작업에서 고치지 않는다.**
- 버킷: 원본 `smokestack-tms-raw-952900391026` 하나만 쓴다.
  - 읽기: `bronze/tw_cems/`
  - 쓰기: `silver/tw_cems/`, `silver/_runs/tw_cems/`
  - Terraform 업로드: `ops/`
  - 접근하지 않음: `tms_cleansys/`

---

## Phase 1: Setup

**Purpose**: 폴더, 의존성, 가짜 샘플, 리뷰어를 준비한다.

- [ ] T001 `services/tms-silver/`, `services/tms-silver/tests/fixtures/`, `infra/stacks/tms-silver/` 폴더를 만든다.
- [ ] T002 [P] `services/tms-silver/pyproject.toml`을 작성한다(plan "Technical Context").
  - `name = "tms-silver"`, `requires-python = ">=3.11,<3.12"` (Glue 5.0 = Python 3.11)
  - 런타임 `dependencies = []`. Glue 5.0이 pyspark, boto3, pandas를 제공한다(R1).
  - `[project.optional-dependencies] dev = ["pyspark==3.5.4", "pandas==2.2.3", "numpy<2", "pyarrow==16.1.0", "boto3", "pytest", "ruff"]`
  - `[tool.setuptools] py-modules = ["glue_tw_cems_silver", "run_silver"]`
  - `[tool.pytest.ini_options] pythonpath = [".", "../../src"]`, `testpaths = ["tests"]`. `../../src`는 C의 `smokestack_guard`를 import하기 위한 것이다.
  - `[tool.ruff] line-length = 100`, `target-version = "py311"`, lint `select = ["E", "F", "W", "I", "B", "UP"]` (`services/tms-eda/pyproject.toml`과 같은 규칙)
- [ ] T003 [P] `services/tms-silver/tests/fixtures/`에 **가짜 데이터** JSONL 3개를 만든다. 실제 원본 값을 복사하지 않는다.
  - 원본 키 15개를 모두 둔다: `importdate`, `_id`, `abbr`, `cno`, `code2`, `code2desc`, `epb_county`, `item`, `itemdesc`, `m_time`, `m_value`, `polno`, `std`, `std_s`, `unit`
  - `synthetic_2025_10.jsonl`(정상 달). 다음 경우가 한 번씩 나오게 한다.
    - 같은 굴뚝·항목의 `:00`·`:15` 두 행(`code2 = "NA10"`, `std` 양수) → `ok`
    - `std = "-1.00"` → `not_monitored`
    - `code2 = "FA10"` → `other_code`
    - 한 행만 있는 슬롯 → `partial`
    - `m_value = "nan"` → `invalid`
    - `m_time`에 `T` 구분과 공백 구분을 섞는다.
  - `synthetic_2025_10_mixed.jsonl`: 위 파일에 `m_time`이 `2025-09-30T23:45:00`인 행 1개를 더한다. 다른 달 행이 섞인 경우다.
  - `synthetic_2025_09.jsonl`: 9월 행 몇 개. 기존 다른 달 파티션 역할이다.
  - `tests/fixtures/README.md`에 "가짜 데이터"라고 적는다.
- [ ] T004 [P] `.github/CODEOWNERS`에 두 줄을 A 구역 아래에 추가한다. 기존 줄은 바꾸지 않는다.
  - `/services/tms-silver/          @SungChul23 @gjfeel4512` (C의 규칙 코드를 감싸므로 C 포함)
  - `/infra/stacks/tms-silver/      @SungChul23 @olchangiagi` (원본 버킷에 쓰기 권한을 주므로 B 포함, 원칙 I)

---

## Phase 2: Foundational (모든 스토리의 전제)

**Purpose**: 스택 뼈대, 패키지·스크립트 업로드, 역할, 카탈로그를 만든다. `main.tf`를 고치는 작업은 같은 파일이라 **순서대로** 한다.

- [ ] T005 `infra/stacks/tms-silver/backend.tf`를 작성한다. `infra/stacks/tms-eda/backend.tf`와 같고 `key = "stacks/tms-silver/terraform.tfstate"`만 다르다.
- [ ] T006 [P] `infra/stacks/tms-silver/versions.tf`를 작성한다.
  - `required_version = "~> 1.15.0"`
  - providers: `aws ~> 6.0`, `archive ~> 2.0` (`infra/stacks/tms-collection/versions.tf`와 같음)
  - provider `region = "ap-northeast-2"`
  - `default_tags { project = "tms", managed_by = "terraform", stack = "tms-silver" }`
- [ ] T007 [P] `infra/stacks/tms-silver/variables.tf`를 작성한다. 모두 `description`과 `type`, 기본값을 둔다.
  - `raw_bucket_name` = `"smokestack-tms-raw-952900391026"` (설명: 원본 버킷, `tms-collection`이 관리, 이 스택은 이름만 참조)
  - `glue_worker_count` = `10` (`validation`: 2~10)
  - `glue_timeout_minutes` = `60`
  - 비밀값 변수는 없다.
- [ ] T008 `infra/stacks/tms-silver/main.tf`에 원본 버킷 참조와 업로드를 정의한다(R5, R10, contracts/run-interface.md §1).
  - `data "aws_s3_bucket" "raw"`. 원본 버킷에 **어떤 `resource`도 붙이지 않는다**: 버전 관리, 수명 주기, 정책 모두 없음(R11).
  - `data "archive_file" "package"`
    - `type = "zip"`, `source_dir = "${path.module}/../../../src"`
    - `output_path = "${path.module}/../../../services/tms-silver/build/smokestack_guard.zip"` (`.gitignore`의 `services/**/*.zip`에 해당)
    - `output_file_mode = "0666"`
    - `excludes = ["smokestack_guard/data/**", "**/__pycache__/**", "**/*.pyc"]`
    - zip 안에는 `smokestack_guard/__init__.py`와 `smokestack_guard/silver/*.py`만 들어가야 한다(T024에서 확인).
  - `aws_s3_object.package`: `bucket = data.aws_s3_bucket.raw.id`, `key = "ops/glue-packages/smokestack_guard.zip"`, `source = archive 경로`, `etag = data.archive_file.package.output_md5`
  - `aws_s3_object.job_script`: `key = "ops/glue-scripts/glue_tw_cems_silver.py"`, `source = services/tms-silver/glue_tw_cems_silver.py`, `etag = filemd5(...)`
  - 주석으로 "원본 버킷의 `ops/`에는 운영 파일만 둔다(R10)"라고 적는다.
- [ ] T009 `infra/stacks/tms-silver/main.tf`에 역할과 로그 그룹을 정의한다(plan "부여 권한", R12).
  - `aws_iam_role.glue`: 이름 `tms-glue-silver`, 신뢰 대상 `glue.amazonaws.com`. 설명은 ASCII만 쓴다: `"TW CEMS Silver Glue job role (bronze read, silver/tw_cems write)"`
  - `aws_iam_role_policy_attachment`: `arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole`
  - `aws_iam_role_policy.glue_data` (이름 `tms-glue-silver-data`) 문장. sid는 고정한다.
    - `ListRawScoped`
      - 동작: `s3:ListBucket`, 원본 버킷 ARN
      - 조건: `StringLike s3:prefix = ["bronze/tw_cems/*", "silver/tw_cems", "silver/tw_cems/*", "silver/_runs/tw_cems/*"]`
    - `ReadBronzeTwCems`: `s3:GetObject`, `${raw}/bronze/tw_cems/*`
    - `ReadOps`: `s3:GetObject`, `${raw}/ops/glue-scripts/*`, `${raw}/ops/glue-packages/*`
    - `ReadWriteSilverTwCems`
      - 동작: `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, `s3:AbortMultipartUpload`
      - 대상: `${raw}/silver/tw_cems/*`, `${raw}/silver/_runs/tw_cems/*`
  - 확인할 것: `bronze/`·`tms_cleansys/`·버킷 전체(`${raw}/*`)에 대한 Put/Delete가 없고, 버킷 전체 `ListBucket`(조건 없음)도 없다.
  - `aws_cloudwatch_log_group.glue`: 이름 `/aws-glue/tms-silver`, `retention_in_days = 14`
- [ ] T010 `infra/stacks/tms-silver/main.tf`에 카탈로그를 정의한다(R6, data-model.md §2, contracts/tw-cems-silver-table.md).
  - `aws_glue_catalog_database.silver`
    - 이름 `tms_silver`
    - 설명: "Silver 테이블. 경로 규칙 silver/<테이블>/ = tms_silver.<테이블> (specs/a-platform/004-tw-cems-silver-glue)"
  - `aws_glue_catalog_table.tw_cems`: `table_type = "EXTERNAL_TABLE"`
    - `storage_descriptor.location = "s3://${raw}/silver/tw_cems/"`
    - 입출력: `org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat` / `MapredParquetOutputFormat`
    - SerDe: `org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe`
  - 컬럼 13개를 **이 순서와 타입 그대로** 정의한다(data-model.md §2):
    - `area_nm` string, `fact_manage_nm` string, `stack_code` string, `item` string, `unit` string
    - `value` double, `limit` double, `status` string
    - `ts_kst` timestamp, `ratio` double, `ts_local` timestamp
    - `code2` string, `flag_code_ratio_mismatch` boolean
  - `partition_keys`: `year` string, `month` string
  - `parameters` (파티션 프로젝션):
    - `"classification" = "parquet"`, `"projection.enabled" = "true"`
    - `"projection.year.type" = "integer"`, `"projection.year.range" = "2023,2030"`
    - `"projection.month.type" = "integer"`, `"projection.month.range" = "1,12"`, `"projection.month.digits" = "2"`
    - `"storage.location.template" = "s3://${raw}/silver/tw_cems/year=$${year}/month=$${month}/"`
  - 테이블 설명: "Spark는 카탈로그가 아니라 S3 경로로 읽는다(프로젝션은 Athena 전용)"

**Checkpoint**: `terraform validate`가 통과한다(Job은 아직 없음).

---

## Phase 3: User Story 1 - A가 36개월 Silver를 한 번에 만든다 (Priority: P1) 🎯 MVP

**Goal**:
- 진입 스크립트와 Glue Job을 배포한다.
- 명령 하나로 대상 월 전체를 변환·재시도·요약한다.
- 다른 달 행이 섞이면 쓰기 전에 멈춘다.

**Independent Test**:
- 로컬: 정상 달은 그 달 파티션 하나와 실행 기록을 만든다. 다른 달 행이 섞인 달은 실패하고 기존 파티션이 남는다.
- AWS: 🧑 2025-10 한 달을 실행해 파티션과 실행 기록이 생기는지 본다.

### Tests for User Story 1

- [ ] T011 [P] [US1] `services/tms-silver/tests/test_glue_tw_cems_silver.py`를 작성한다. 모두 로컬 Spark(`local[2]`, `spark.sql.session.timeZone=UTC`)와 `tmp_path`를 쓴다. 세션은 `conftest.py`의 session fixture로 한 번만 만든다. 경우:
  1. **정상 달**: `synthetic_2025_10.jsonl`, `--year 2025 --month 10`
     - 출력에 `year=2025/month=10/` 하나만 생긴다.
     - 실행 기록 JSON이 생긴다.
     - `silver_rows == sum(status_rows.values())`이다.
     - `status_rows` 키는 5개(`ok`, `not_monitored`, `other_code`, `partial`, `invalid`)이고 각각 1 이상이다.
     - `input_rows`는 fixture의 줄 수와 같다.
  2. **다른 달 섞임**: 먼저 `synthetic_2025_09.jsonl`을 9월로 실행해 둔다. 그다음 `synthetic_2025_10_mixed.jsonl`을 10월로 실행한다.
     - 예외 메시지에 `month mismatch`, `expected 2025-10`, `"2025-09": 1`이 들어 있다.
     - 9월 파티션의 파일 목록과 행 수가 그대로다.
     - 10월 파티션과 10월 실행 기록이 생기지 않는다.
  3. **0행**: 모든 줄의 `cno`가 null인 입력이면 `empty silver for 2025-10`으로 실패하고 아무것도 쓰지 않는다.
  4. **그 달만 교체**: 9월과 10월을 쓴 뒤 10월을 다시 실행한다.
     - 10월 행 수와 `status`별 건수가 같다.
     - 9월 파티션 파일 목록이 그대로다.
  5. **파티션 식 일치(R4)**: 같은 입력에 대해 `tw_cems_spark.build(spark, src, out_c)` 결과와 이 스크립트 결과를 비교한다.
     - (`year`, `month`) 집합이 같다.
     - `stack_code, item, unit, ts_kst`로 정렬한 13개 컬럼이 같다.
  6. **로그에 데이터 값이 없음**: `capsys`로 잡은 출력에 fixture의 `m_value`·`abbr` 값이 들어 있지 않다.
- [ ] T012 [P] [US1] `services/tms-silver/tests/test_run_silver.py`를 작성한다. `services/tms-eda/tests/test_run_backfill.py`를 바탕으로 하고, boto3는 가짜 클라이언트로 대신한다. 바뀐 점만 추가로 검증한다.
  - `--only-missing`: `silver/_runs/tw_cems/YYYY-MM.json`이 있는 월은 `SKIPPED`이다. `_SUCCESS`는 보지 않는다.
  - 결과 표: 실행 기록에서 읽은 `input_rows`, `silver_rows`, `ok_rows` 열과 합계가 있다. 기록이 없으면 `-`이다.
  - `--start-crawler` 옵션이 없다(인자 오류).
  - 기본값: `--job-name tms-silver-tw-cems`, 출력 버킷 `smokestack-tms-raw-952900391026`, runs 경로 `silver/_runs/tw_cems`
  - 그대로 유지되는지 확인할 동작: 범위 계산, 미리 보기, 동시 실행 제한, 1회 재시도, `ConcurrentRunsExceededException` 대기(시도로 세지 않음), 종료 코드 0/1/2

### Implementation for User Story 1

- [ ] T013 [US1] `services/tms-silver/glue_tw_cems_silver.py`를 작성한다(contracts/run-interface.md §1, research R2·R3·R4, data-model.md §2·§3).
  - **import 규칙**
    - `awsglue`를 import하지 않는다(`services/tms-eda/tw_cems_parquet.py`와 같음). Glue가 넘기는 `--JOB_NAME` 등은 `parse_known_args`로 무시한다.
    - C의 코드는 `from smokestack_guard.silver import tw_cems_spark`, `from smokestack_guard.silver.tw_cems import RAW`로만 쓴다. C의 함수 본문을 복사하지 않는다.
  - `parse_args(argv)`
    - 필수: `--year`(4자리), `--month`(`01`~`12`)
    - Glue 인자: `--raw_bucket`, `--raw_prefix`(기본 `bronze/tw_cems/historical`), `--silver_bucket`, `--table_prefix`(기본 `silver/tw_cems`), `--runs_prefix`(기본 `silver/_runs/tw_cems`), `--package_md5`(기본 `"unknown"`)
    - 로컬 인자: `--local`, `--input_path`, `--output_path`, `--runs_path`. `--local`이면 이 세 경로가 필수다.
  - `build_spark(local)`
    - 공통: `spark.sql.session.timeZone=UTC`, `spark.sql.sources.partitionOverwriteMode=dynamic`
    - 로컬이면 `master("local[2]")`
  - `read_input(spark, path) -> (DataFrame, int)`
    1. `tw_cems_spark.read_raw`로 읽는다.
    2. 컬럼 이름을 소문자로 바꾼다.
    3. `RAW` 중 존재하는 컬럼만 `select`한다. `_corrupt_record` 등 나머지는 버린다.
    4. `persist(StorageLevel.MEMORY_AND_DISK)` 후 `count()`한다.
  - `with_partitions(silver)`: `year = date_format(ts_local, "yyyy")`, `month = date_format(ts_local, "MM")`. 식이 `tw_cems_spark.build`와 같아야 한다(T011-5).
  - `collect_counts(silver) -> dict[(year, month), dict[status, int]]`: `groupBy("year","month","status").count().collect()`. Silver는 `persist`한 뒤 센다.
  - `check_months(counts, year, month)`
    - 다른 (year, month)가 있으면 `ValueError(f"month mismatch: expected {year}-{month}, found {json.dumps({...})}")`
    - 결과가 비었으면 `ValueError(f"empty silver for {year}-{month}")`
    - **쓰기보다 먼저** 호출한다.
  - `write_silver(silver, output_root)`: `write.mode("overwrite").partitionBy("year","month").parquet(output_root)` (동적 덮어쓰기)
  - `build_run_record(...) -> dict`: data-model.md §3의 필드를 모두 채운다.
    - 필드: `month`, `job_run_id`(`--JOB_RUN_ID` 또는 `"local"`), `source`, `output`, `input_rows`, `silver_rows`, `status_rows`(5개 키, 없으면 0), `package_md5`, `versions`, `started_at`, `finished_at`
    - `versions`: `spark`, `python`, `pandas`, `numpy`. pandas·numpy는 import 성공 여부 확인용이다(R1).
    - 불변식 `silver_rows == sum(status_rows.values())`를 `assert`한다.
  - `write_run_record(record, ...)`: Glue면 boto3 `put_object(Bucket=silver_bucket, Key=f"{runs_prefix}/{YYYY}-{MM}.json", ContentType="application/json")`, 로컬이면 `runs_path`에 파일로 쓴다. **데이터 쓰기가 성공한 뒤에만** 호출한다.
  - `main(argv=None)`
    - 순서: 읽기 → 변환 → 파티션 → 집계 → 검사 → 쓰기 → 실행 기록
    - 끝나면 요약 한 줄(`json.dumps`: 경로, 건수, `status_rows`, `package_md5`, `versions`, 소요 초)을 `print`한다.
    - 데이터 값은 출력하지 않는다.
  - `if __name__ == "__main__": main()`
- [ ] T014 [US1] `infra/stacks/tms-silver/main.tf`에 Glue Job을 정의한다(R1, R9, R11).
  - `aws_glue_job.tw_cems` 기본 설정
    - 이름 `tms-silver-tw-cems`, 설명 "TW CEMS 원본 월 파일 1개를 Silver(silver/tw_cems)로 변환"
    - `role_arn = aws_iam_role.glue.arn`, `glue_version = "5.0"`, `worker_type = "G.1X"`
    - `number_of_workers = var.glue_worker_count`, `timeout = var.glue_timeout_minutes`
    - `max_retries = 0` (재시도는 `run_silver.py`가 1회), `execution_class = "STANDARD"`
    - `execution_property { max_concurrent_runs = 6 }`
    - `command { name = "glueetl", python_version = "3", script_location = "s3://${raw}/${aws_s3_object.job_script.key}" }`
  - `default_arguments`
    - 공통: `--job-language = "python"`, `--job-bookmark-option = "job-bookmark-disable"`, `--enable-continuous-cloudwatch-log = "true"`, `--continuous-log-logGroup = aws_cloudwatch_log_group.glue.name`, `--enable-metrics = "true"`
    - 패키지: `--extra-py-files = "s3://${raw}/${aws_s3_object.package.key}"`
    - 경로: `--raw_bucket`, `--raw_prefix = "bronze/tw_cems/historical"`, `--silver_bucket = var.raw_bucket_name`, `--table_prefix = "silver/tw_cems"`, `--runs_prefix = "silver/_runs/tw_cems"`
    - 버전: `--package_md5 = data.archive_file.package.output_md5`
    - **`--TempDir`은 넣지 않는다**(R11).
  - `--year`, `--month`는 기본값 없이 실행 때마다 넘긴다.
- [ ] T015 [US1] `services/tms-silver/run_silver.py`를 작성한다. `services/tms-eda/run_backfill.py`를 복사해서 아래만 바꾼다(R8, contracts/run-interface.md §2).
  - 상수 `DEFAULT_JOB_NAME = "tms-silver-tw-cems"`, `DEFAULT_SILVER_BUCKET = "smokestack-tms-raw-952900391026"`, `DEFAULT_RUNS_PREFIX = "silver/_runs/tw_cems"`
  - `--eda-bucket`·`--output-prefix`·`--start-crawler`·`--crawler-name`을 지운다. `--silver-bucket`, `--runs-prefix`를 추가한다.
  - `plan_targets`의 완료 판단을 `_SUCCESS`에서 `{runs_prefix}/{YYYY-MM}.json` 존재로 바꾼다.
  - 미리 보기 표에 "실행 기록 있음" 열을 추가한다.
  - 실행이 끝나면 각 월의 실행 기록을 `get_object`로 읽어 `input_rows`, `silver_rows`, `ok_rows`(= `status_rows["ok"]`)를 결과 표에 붙이고, 합계 행에도 더한다. 읽기에 실패하면 `-`로 둔다.
  - 독스트링 첫 줄과 계약 참조를 004로 바꾼다. 나머지 동작(재시도, 대기, 비용 추정, 종료 코드)은 바꾸지 않는다.
- [ ] T016 [P] [US1] `infra/stacks/tms-silver/outputs.tf`: 출력에 모두 `description`을 단다.
  - `glue_job_name`
  - `glue_role_arn`
  - `glue_database_name`
  - `silver_table_name`
  - `silver_location` (`s3://.../silver/tw_cems/`)
  - `package_md5`
- [ ] T017 [US1] 로컬 검증(에이전트)
  - Spark 테스트: `docker run ... sg-spark:3.5 python3 -m pytest services/tms-silver/tests -q -p no:cacheprovider` (quickstart §1)
  - 린트: `cd services/tms-silver && ruff check .`
  - Terraform: `terraform fmt -recursive infra/`, `/mnt/c/terraform/terraform.exe -chdir=infra/stacks/tms-silver init` / `validate`
  - 실패가 있으면 고친 뒤 다시 실행한다.
- [ ] T018 [US1] `terraform plan`(에이전트, WSL에서 `/mnt/c/terraform/terraform.exe -chdir=infra/stacks/tms-silver plan`)을 실행해 결과를 사용자에게 보여준다. 확인할 것:
  - 생성만 있고 변경·삭제가 0이다.
  - `smokestack-tms-raw-952900391026`에 대한 `aws_s3_bucket*` 리소스가 없다. 업로드 객체 2개(`ops/`)만 있다.
  - `tms-collection`·`tms-eda` 상태와 무관하다(다른 backend key).
- [ ] T019 🧑 [US1] 사용자가 PowerShell에서 `terraform apply`를 실행한다.
- [ ] T020 🧑 [US1] 한 달 시험 실행 (quickstart §3)
  - 명령: `python run_silver.py --from 2025-10 --to 2025-10 --dry-run` → `python run_silver.py --from 2025-10 --to 2025-10`
  - 확인할 것:
    - `SUCCEEDED`이다.
    - 실행 기록이 있고, `versions.pandas` 값이 있다(import 성공).
    - `ListBucket` `AccessDenied`가 없다(R12). 거부되면 로그의 접두어만 T009에 추가하고 다시 `plan` → `apply`한다.
  - 실측 소요 시간과 비용을 `research.md` R9에 기록한다.
- [ ] T021 🧑 [US1] 36개월 실행 (quickstart §4)
  - 명령: `python run_silver.py --dry-run` → `python run_silver.py --only-missing`
  - 결과 표(월별 행 수, 합계 비용·시간)를 `plan.md` 끝에 "실행 결과 (YYYY-MM-DD)" 절로 붙인다(SC-001, SC-006).

**Checkpoint**: 36개 월 모두 `SUCCEEDED`이고, `silver/_runs/tw_cems/`에 실행 기록이 36개 있다.

---

## Phase 4: User Story 2 - 팀원이 Silver를 SQL로 조회한다 (Priority: P1)

**Goal**: Athena(`tms-eda` 워크그룹)에서 `tms_silver.tw_cems`를 월 조건으로 조회할 수 있다.

**Independent Test**: 월 조건 쿼리가 결과를 내고, 스캔량이 전체의 약 1/36이다.

- [ ] T022 [P] [US2] `specs/a-platform/004-tw-cems-silver-glue/quickstart.md` §5의 쿼리에 아래를 더한다.
  - 전체 행 수 합계 쿼리
  - 실행 기록 합계와의 비교 방법: 실행 기록은 `aws s3 cp`로 내려받아 합한다
  - 결과가 다를 때 월별로 차이를 찾는 쿼리
- [ ] T023 🧑 [US2] 사용자가 Athena에서 quickstart §5를 실행한다. 확인할 것:
  - 36행이 나온다.
  - 합계가 약 8,036만이고 실행 기록 합계와 같다(SC-002).
  - 월 조건 쿼리의 스캔량이 전체의 약 1/36이다(SC-003).
  - 컬럼 타입이 data-model.md §2와 같다(`SHOW CREATE TABLE`).
  - 결과를 `plan.md` "실행 결과" 절에 적는다.
- [ ] T024 [US2] C·D·E 중 1명에게 조회 확인을 요청하는 문구를 PR 본문 초안에 넣는다(SC-007). 확인 결과는 PR 댓글로 받는다.

**Checkpoint**: Athena에서 Silver를 월 단위로 조회할 수 있다.

---

## Phase 5: User Story 3 - 원본은 실행이 잘못되어도 안전하다 (Priority: P1)

**Goal**: Glue 역할이 `bronze/`·`tms_cleansys/`에 쓰거나 지울 수 없다는 것을 코드와 실제 권한으로 확인한다.

**Independent Test**: IAM 정책 시뮬레이터에서 `bronze/` 쓰기·삭제는 거부되고, `silver/tw_cems/` 쓰기는 허용된다.

- [ ] T025 [P] [US3] zip 내용 확인(에이전트). `terraform plan` 뒤 `unzip -l services/tms-silver/build/smokestack_guard.zip` 결과에 `smokestack_guard/__init__.py`와 `smokestack_guard/silver/*.py`만 있는지 본다. `data/`와 `__pycache__`가 없어야 한다.
- [ ] T026 [P] [US3] `specs/a-platform/004-tw-cems-silver-glue/quickstart.md`에 "§8 권한 확인" 절을 추가한다. `aws iam simulate-principal-policy --policy-source-arn <tms-glue-silver ARN>` 명령과 기대 결과를 적는다.
  - `s3:PutObject` / `s3:DeleteObject`
    - `bronze/tw_cems/historical/2025-10.jsonl` → `implicitDeny`
    - `tms_cleansys/_state/latest.json` → `implicitDeny`
    - `silver/tw_cems/year=2025/month=10/x.parquet` → `allowed`
    - `silver/tw_cems_ml_ready/x` → `implicitDeny`
  - `s3:ListBucket` (prefix `tms_cleansys/`) → `implicitDeny`
- [ ] T027 🧑 [US3] 사용자가 §8 명령을 실행하고 결과를 `plan.md` "실행 결과" 절에 적는다.
- [ ] T028 🧑 [US3] 36개월 실행(T021) **전과 후**에 `aws s3 ls s3://smokestack-tms-raw-952900391026/bronze/tw_cems/historical/ --summarize`를 실행한다. 객체 수와 크기 합계가 같아야 한다(SC-005, quickstart §7).

**Checkpoint**: 원본 경로에 대한 쓰기·삭제가 정책상 불가능하고, 실행 전후 원본이 같다.

---

## Phase 6: Polish & Cross-Cutting

- [ ] T029 [P] `AGENTS.md`를 고친다(FR-014, R10). 규칙은 이 파일에서만 고친다.
  - "저장소 구조" 트리에 두 줄을 추가한다.
    - `infra/stacks/tms-silver/` ("Silver 실행: Glue Job + 역할 + 카탈로그 (버킷은 원본 버킷 silver/)")
    - `services/tms-silver/` ("Silver Glue 진입 스크립트 + 일괄 실행 명령")
  - 새 절 "## S3 경로 규칙"을 "저장소 구조" 다음에 추가한다. 내용은 R10의 경로 트리와 규칙 1~6이다.
    - 원본 버킷의 `bronze/`·`tms_cleansys/`는 수집 주체만 쓴다.
    - `silver/<테이블>/` = `tms_silver.<테이블>`
    - 테이블 이름은 `<출처>[_<용도>]`
    - 파티션 기본 `year=/month=`
    - `_` 폴더는 테이블이 아니다.
    - 역할마다 자기 테이블 경로에만 쓴다.
    - `ops/`는 Terraform이 올리는 운영 파일만 둔다.
  - 문장은 기존 AGENTS.md 문체(짧은 평서문, 한국어)를 따른다.
- [ ] T030 [P] `services/tms-silver/README.md`를 작성한다.
  - 무엇을 하는지(한 줄)
  - 로컬 테스트 방법(Docker, CI)
  - `run_silver.py` 사용법(미리 보기 → 한 달 → 36개월 → `--only-missing`)
  - 실행 기록 위치
  - 첫 실행 확인 항목(pandas import, `ListBucket` 거부)
  - 상세는 spec·contracts 링크로 대신한다.
- [ ] T031 [P] `.github/workflows/tms-silver.yml`을 만든다. `.github/workflows/tms-eda.yml`을 바탕으로 한다.
  - `paths`: `services/tms-silver/**`, `src/smokestack_guard/silver/**`, `.github/workflows/tms-silver.yml`. C의 규칙 코드가 바뀌어도 진입 스크립트 테스트가 돈다.
  - Java 17 (temurin), Python `3.11`
  - `working-directory: services/tms-silver`
  - `pip install -e ".[dev]"` → `ruff check .` → `pytest -q`
- [ ] T032 최종 확인(에이전트): T017을 다시 실행해 `pytest`, `ruff`, `terraform fmt -recursive`, `terraform validate`가 모두 통과하는지 본다.
  - `src/smokestack_guard/` 아래 파일이 바뀌지 않았는지 `git diff --stat -- src/`로 확인한다. 결과는 비어 있어야 한다.
  - C의 `scripts/`, `spark_migration_checklist.md`도 바뀌지 않았는지 확인한다.
- [ ] T033 PR 본문 초안을 사용자에게 보여주고 허락을 받는다. 허락 전에는 생성하지 않는다. 담을 내용:
  - spec 링크
  - 리뷰 요청: C(진입 스크립트, 파티션 식), B(원본 버킷 권한, 원칙 I)
  - C에게 후속 제안 2개: 상수를 pandas 없는 모듈로 분리, `build()`를 변환·쓰기로 분리
  - C의 201 tasks T032(36개월 Glue 실행)와의 관계
  - `plan` 요약
  - `Closes #<이슈번호>`

---

## Dependencies & Execution Order

```
Phase 1 (T001 → T002·T003·T004 병렬)
  └▶ Phase 2: T005 → T006·T007 병렬 → T008 → T009 → T010     (main.tf는 순서대로)
        └▶ Phase 3 US1:
              테스트 T011 ∥ T012   (T002·T003 이후)
              코드   T013 (T011과 함께) ∥ T015 (T012와 함께)
              인프라 T014 (T010 이후, T013 파일 필요) → T016
              → T017 → T018 → 🧑 T019 → 🧑 T020 → 🧑 T021
        ├▶ Phase 4 US2: T022 (언제든) → 🧑 T023 (T021 이후) → T024
        └▶ Phase 5 US3: T025 (T018 이후) ∥ T026 (언제든) → 🧑 T027 (T019 이후)
                        🧑 T028 (T021 전·후)
  └▶ Phase 6: T029·T030·T031 병렬 (언제든) → T032 (T019 전) → T033
```

- `main.tf`를 고치는 작업(T008, T009, T010, T014)은 같은 파일이라 순서대로 한다.
- 🧑 작업은 에이전트가 실행하지 않는다. 에이전트는 명령과 기대 결과를 준비하고, 사용자가 붙여준 결과로 문서를 갱신한다.
- 🧑 T028의 "전" 측정은 T021보다 먼저 해야 한다.

## Parallel Examples

- **Phase 1**: T002(pyproject), T003(fixtures), T004(CODEOWNERS)를 동시에 작성한다.
- **US1**: T011+T013(진입 스크립트와 테스트)과 T012+T015(실행 명령과 테스트)를 두 갈래로 진행한다. T014는 Terraform 갈래다.
- **Phase 6**: T029(AGENTS.md), T030(README), T031(CI)을 동시에 진행한다.

## Implementation Strategy

1. **MVP = Phase 1~3의 T001~T018 + T029~T032**: 코드, 테스트, `plan`까지 끝내고 PR을 올린다. 이 시점에 리뷰(C, B)를 받는다.
2. 승인 뒤 🧑 T019(`apply`) → T020(한 달 시험)으로 비용·권한·pandas를 확인한다. 문제가 있으면 고치고 다시 `plan` → `apply`한다.
3. 🧑 T028(전) → T021(36개월) → T028(후) → T023 → T027 순서로 운영 확인을 하고, 결과를 문서에 적는다(후속 커밋).
4. **커밋 단위(작업별, 사용자가 요청할 때만)**:
   - ① spec 문서(spec, plan, research, data-model, contracts, quickstart, tasks)
   - ② Setup(pyproject, fixtures, CODEOWNERS)
   - ③ 진입 스크립트 + 테스트
   - ④ 일괄 실행 명령 + 테스트
   - ⑤ Terraform 스택(`.terraform.lock.hcl` 포함)
   - ⑥ AGENTS.md·README·CI
   - ⑦ (`apply` 뒤) 실행 결과 기록
