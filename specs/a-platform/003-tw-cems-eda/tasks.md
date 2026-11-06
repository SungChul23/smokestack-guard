---
description: "003 TW CEMS Athena EDA 환경 작업 목록"
---

# Tasks: TW CEMS Athena EDA 환경 (JSONL → Parquet 1회 변환)

**Input**: `specs/a-platform/003-tw-cems-eda/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: spec이 자동 테스트를 요구한다(US3 Independent Test, FR-011, FR-012). 테스트는 pytest + 로컬 SparkSession(Java 17)으로 하고, boto3는 mock으로 대신한다.

**Organization**: 사용자 스토리별 단계.
- US2(백필)와 US1(조회)은 둘 다 P1이다. 하지만 조회 대상이 변환 결과이므로 **US2 → US1** 순서로 둔다.
- US3(결과가 원본과 같은지 검증)는 변환 스크립트의 테스트다.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 다른 파일이고 선행 작업이 없어 병렬 가능
- **[Story]**: US1(Athena 조회), US2(1회 일괄 변환), US3(결과 검증)
- 🧑 표시는 **사람이 하는 작업**(apply, 백필 실행, 크롤러 시작, AWS 확인). 에이전트는 실행하지 않는다.

## 경로

- 스택: `infra/stacks/tms-eda/`
- 코드: `services/tms-eda/`
- 버킷: 원본 `smokestack-tms-raw-952900391026`(읽기만), EDA `smokestack-tms-eda-952900391026`

---

## Phase 1: Setup

**Purpose**: 폴더, 의존성, 무시 파일, 가짜 샘플을 준비한다.

- [x] T001 `services/tms-eda/`와 `services/tms-eda/tests/fixtures/`, `infra/stacks/tms-eda/` 폴더를 만든다.
- [x] T002 [P] `services/tms-eda/pyproject.toml`을 작성한다.
  - `name = "tms-eda"`, `requires-python = ">=3.13,<3.14"`, 런타임 `dependencies = []`
  - `[project.optional-dependencies] dev = ["pyspark==4.1.1", "boto3", "pytest", "ruff"]`
  - `[tool.pytest.ini_options] pythonpath = ["."]`, `testpaths = ["tests"]`
  - `[tool.ruff] line-length = 100, target-version = "py313"`
  - 패키지 설치 대상 모듈은 `tw_cems_parquet`, `run_backfill`이다(`[tool.setuptools] py-modules`).
- [x] T003 [P] 저장소 루트 `.gitignore`에 `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `spark-warehouse/`, `metastore_db/`, `derby.log`를 추가한다. 기존 줄은 바꾸지 않는다.
- [x] T004 [P] `services/tms-eda/tests/fixtures/synthetic_edge_cases.jsonl`을 만든다. **가짜 데이터**이며, JSONL은 주석을 쓸 수 없으므로 README와 테스트 독스트링에 "가짜 데이터"라고 표시한다. 담을 줄:
  - 2024-03 기준 15개 키(`ImportDate`, `_id`, `abbr`, `cno`, `code2`, `code2desc`, `epb_county`, `itemdesc`, `m_time`, `item`, `m_value`, `std`, `polno`, `std_s`, `unit`)를 가진 기본 행 몇 개
  - `polno` 없이 `flareno`·`locationno`가 있는 행
  - `m_time` 형식 3종(`2025-03-01 00:15:00`, `2025/3/1 0:15`, `2025-03-01T00:15:00`)
  - `std`가 `"nan"`인 행, 빈 문자열 값, 숫자 리터럴 값(예: `"m_value": 12.30`)
  - 모든 값이 같은 중복 행 2줄
  - **손상된 줄 1개**(예: `{"cno": "X01", "m_value": `)
  - **빈 줄 1개**
  - 비어 있지 않은 줄 수를 테스트에서 상수로 쓸 수 있게 고정한다.
- [x] T005 [P] `services/tms-eda/tests/fixtures/synthetic_month_b.jsonl`을 만든다(가짜). T004와 키 구성이 다르게 한다(예: `std_s` 없음, `extra_note` 추가).
- [x] T006 [P] `services/tms-eda/tests/fixtures/synthetic_case_conflict.jsonl`을 만든다(가짜). 한 줄에는 `ImportDate`, 다른 줄에는 `importdate` 키가 있다.

---

## Phase 2: Foundational (모든 스토리의 전제)

**Purpose**: 스택 뼈대(버킷, 역할, 로그)와 변환 스크립트를 만든다.

**⚠️ CRITICAL**: Phase 3 이후의 Terraform 작업은 T007~T011, 코드 작업은 T012가 끝나야 시작한다.

- [x] T007 `infra/stacks/tms-eda/backend.tf`를 작성한다. `tms-collection/backend.tf`와 같고 `key = "stacks/tms-eda/terraform.tfstate"`만 다르다.
- [x] T008 [P] `infra/stacks/tms-eda/versions.tf`를 작성한다.
  - `required_version = "~> 1.15.0"`, `aws ~> 6.0`(archive 없음)
  - provider `region = "ap-northeast-2"`
  - `default_tags { project = "tms", managed_by = "terraform", stack = "tms-eda" }`
- [x] T009 [P] `infra/stacks/tms-eda/variables.tf`를 작성한다. 모두 `description`과 `type`, 기본값을 둔다.
  - `raw_bucket_name` = `"smokestack-tms-raw-952900391026"`
  - `eda_bucket_name` = `"smokestack-tms-eda-952900391026"`
  - `glue_worker_count` = `5` (`validation`: 2~10)
  - `athena_bytes_scanned_cutoff` = `10737418240` (10GB)
- [x] T010 `infra/stacks/tms-eda/main.tf`에 EDA 버킷을 정의한다(plan "main.tf 구성", research R10).
  - `data "aws_s3_bucket" "raw"`
  - `aws_s3_bucket.eda`: `lifecycle { prevent_destroy = true }`, `force_destroy` 쓰지 않음
  - ownership controls `BucketOwnerEnforced`, versioning `Enabled`, SSE `AES256`, public access block 4개 `true`
  - `aws_s3_bucket_lifecycle_configuration.eda` 규칙:
    - `athena-results/`: 현재 버전 30일, 이전 버전 1일
    - `glue-temp/`: 현재 버전 7일, 이전 버전 1일
    - `tw_cems_raw/`: 이전 버전 7일, 만료된 삭제 표시 정리
    - 버킷 전체: 미완료 멀티파트 업로드 7일 정리
  - 원본 버킷에는 어떤 리소스도 붙이지 않는다.
- [x] T011 `infra/stacks/tms-eda/main.tf`에 역할과 로그 그룹을 정의한다(plan "부여 권한" 표).
  - `aws_iam_role.glue` 이름 `tms-glue-eda`, 신뢰 대상 `glue.amazonaws.com`
  - `aws_iam_role_policy_attachment`로 `arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole` 부착
  - `aws_iam_role_policy.glue_data`의 문장(sid는 고정):
    - `ListRawTwCems`: `s3:ListBucket`, 원본 버킷 ARN, 조건 `StringLike s3:prefix = ["bronze/tw_cems/*"]`
    - `ReadRawTwCems`: `s3:GetObject`, `${raw}/bronze/tw_cems/*`
    - `ListEda`: `s3:ListBucket`, EDA 버킷 ARN
    - `ReadWriteEdaData`: `s3:GetObject`·`s3:PutObject`·`s3:DeleteObject`·`s3:AbortMultipartUpload`, `${eda}/tw_cems_raw/*`, `${eda}/glue-temp/*`
    - `ReadGlueScripts`: `s3:GetObject`, `${eda}/glue-scripts/*`
  - 원본 버킷에 Put/Delete 권한이 없는지 확인한다.
  - `aws_cloudwatch_log_group.glue` 이름 `/aws-glue/tms-eda`, `retention_in_days = 14`
- [x] T012 `services/tms-eda/tw_cems_parquet.py`를 작성한다. Glue Job과 로컬 실행을 겸한다([contracts/run-interface.md §1](contracts/run-interface.md), research R3·R4·R6·R12).
  - `parse_args(argv)`: `argparse` + `parse_known_args`
    - `--year`(4자리), `--month`(두 자리, `01`~`12` 검증)는 필수
    - `--raw_bucket`, `--raw_prefix`(기본 `bronze/tw_cems/historical`), `--eda_bucket`, `--output_prefix`(기본 `tw_cems_raw`)
    - `--local`(플래그), `--input_path`, `--output_path`. `--local`이면 입출력 경로가 필수다.
  - `build_spark(local: bool)`: 로컬이면 `master("local[2]")`, `spark.sql.session.timeZone=UTC`. Glue면 `SparkSession.builder.getOrCreate()`
  - `resolve_paths(args) -> (input_path, output_path)`:
    - 입력: `s3://{raw_bucket}/{raw_prefix}/{YYYY}-{MM}.jsonl`
    - 출력: `s3://{eda_bucket}/{output_prefix}/year={YYYY}/month={MM}/`
    - 로컬이면 출력은 `{output_path}/year={YYYY}/month={MM}/`
  - `check_column_conflicts(columns)`: 소문자로 바꿨을 때 중복이 있으면 충돌한 이름을 담아 `ValueError`
  - `convert(spark, input_path, output_path) -> dict`:
    - `spark.read.option("primitivesAsString","true").option("mode","PERMISSIVE").option("columnNameOfCorruptRecord","_corrupt_record").json(input_path)`
    - 스키마를 주지 않는다. `multiLine`을 쓰지 않는다.
    - 충돌 검사 → `withColumn("source_file", F.col("_metadata.file_path"))` → `repartition(2).write.mode("overwrite").option("compression","snappy").parquet(output_path)`
    - 행 필터, 값 변환, 추가 `count()`가 없어야 한다.
    - 반환: `{input_path, output_path, column_count, columns, spark_version}`
  - 입력 파일이 없으면 Spark 오류를 그대로 올려 Job을 실패시킨다.
  - `main(argv=None)`: 위 순서로 실행하고, `json.dumps` 요약 한 줄과 소요 시간(초)을 `print`한다. 데이터 값은 로그에 남기지 않는다.
  - `awsglue`를 import하지 않는다. `if __name__ == "__main__": main()`

**Checkpoint**: `terraform validate`가 통과하고, `python tw_cems_parquet.py --local …`이 fixture로 Parquet을 만든다.

---

## Phase 3: User Story 2 - A가 업로드 완료 후 24개월을 한 번에 변환한다 (Priority: P1) 🎯 MVP

**Goal**: Glue Job을 배포하고, 명령 하나로 대상 월 전체를 변환·재시도·요약한다.

**Independent Test**: `run_backfill.py --dry-run`이 2024-11~2026-10 중 원본에 있는 월만 출력하고 Job을 시작하지 않는다(mock 테스트, 실제 AWS에서는 사람이 실행).

### Tests for User Story 2

- [x] T013 [P] [US2] `services/tms-eda/tests/test_run_backfill.py`를 작성한다(boto3 클라이언트는 `unittest.mock`/가짜 객체).
  - `parse_months`:
    - `^\d{4}-\d{2}\.jsonl$`에 맞지 않는 키(`2025-3.jsonl`, `readme.txt`, `2025-03.jsonl.gz`)는 제외
    - 범위 `2024-11`~`2026-10` 경계 포함, `2024-10`·`2026-11` 제외
  - `plan_targets`: `--only-missing`이면 `_SUCCESS`가 있는 월은 `SKIPPED`
  - `--dry-run`이면 `start_job_run`이 0회 호출
  - `--concurrency`가 1~3을 벗어나면 종료 코드 2
  - 실패한 월은 정확히 1회 재시도하고, 두 번째 실패는 실패 목록에 들어간다. 종료 코드 1
  - 동시 실행 중인 월 수가 `concurrency`를 넘지 않는다.
  - `estimate_cost`:
    - `DPUSeconds`가 있으면 그 값 사용
    - 없으면 `ExecutionTime × NumberOfWorkers`
    - `est_usd = dpu_s / 3600 × 0.308`
  - `--start-crawler`: 실패한 월이 있으면 `start_crawler`를 호출하지 않는다.

### Implementation for User Story 2

- [x] T014 [US2] `infra/stacks/tms-eda/main.tf`에 Job map과 스크립트 업로드를 추가한다(plan "Job map").
  - `locals.glue_jobs`(`tms-eda-tw-cems-parquet` 항목 하나: `script`, `workers`, `timeout = 30`, `max_concurrent = 3`, `arguments`)와 `locals.glue_common_arguments`
  - `aws_s3_object.job_script` (`for_each = local.glue_jobs`):
    - `bucket = aws_s3_bucket.eda.id`, `key = "glue-scripts/${each.value.script}"`
    - `source = "${path.module}/../../../services/tms-eda/${each.value.script}"`, `etag = filemd5(...)`
  - `aws_glue_job.this` (`for_each = local.glue_jobs`):
    - `name = each.key`, `role_arn = aws_iam_role.glue.arn`
    - `glue_version = "6.0"`, `worker_type = "G.1X"`, `number_of_workers = each.value.workers`
    - `timeout = each.value.timeout`, `max_retries = 0`, `execution_class = "STANDARD"`
    - `execution_property { max_concurrent_runs = each.value.max_concurrent }`
    - `command { name = "glueetl", python_version = "3", script_location = "s3://${aws_s3_bucket.eda.id}/${aws_s3_object.job_script[each.key].key}" }`
    - `default_arguments = merge(local.glue_common_arguments, each.value.arguments)`
  - `--year`·`--month`를 `default_arguments`에 넣지 않는다.
- [x] T015 [US2] `services/tms-eda/run_backfill.py`를 작성한다([contracts/run-interface.md §2](contracts/run-interface.md), [data-model.md §4·§5](data-model.md)).
  - 옵션: `--from`(기본 `2024-11`), `--to`(기본 `2026-10`), `--concurrency`(기본 2, "1~3이 아니면 오류" → 종료 코드 2), `--only-missing`, `--dry-run`, `--start-crawler`, `--job-name`(기본 `tms-eda-tw-cems-parquet`), `--raw-bucket`, `--eda-bucket`, `--crawler-name`(기본 `tms-eda-tw-cems-crawler`), `--profile`, `--region`(기본 `ap-northeast-2`)
  - `list_raw_keys(s3, bucket, prefix)`: `list_objects_v2` 페이지 처리, 키·크기·LastModified 반환
  - `parse_months(objects, from, to)`: 정규식 `^(\d{4})-(\d{2})\.jsonl$`, 범위 필터, 정렬. 범위 안에서 원본에 없는 월 목록도 반환
  - `plan_targets(...)`: `--only-missing`이면 `head_object`로 `{output_prefix}/year=YYYY/month=MM/_SUCCESS`를 확인하고 있으면 `SKIPPED`
  - `--dry-run`: 대상 월·크기(GB)·LastModified·빠진 월·SKIPPED를 출력하고 종료 코드 0
  - `run_all(glue, months, concurrency, poll_seconds=30)`:
    - `start_job_run(JobName, Arguments={"--year": YYYY, "--month": MM})`
    - `get_job_run`으로 30초마다 상태 확인
    - `FAILED`/`ERROR`/`TIMEOUT`/`STOPPED`이면 1회만 다시 시작
    - 동시에 RUNNING인 월은 `concurrency` 이하
  - `estimate_cost(job_run)`: data-model §5 규칙
  - `render_table(results)`: `month | state | attempts | run_id | execution_s | dpu_s | est_usd`, 합계 줄, 실패 목록
  - `--start-crawler`: 실패 0건일 때만 `start_crawler`. 실패가 있으면 경고만 출력
  - 종료 코드: 모두 성공 또는 SKIPPED면 0, 실패가 있으면 1
  - 세션은 `boto3.Session(profile_name=args.profile, region_name=args.region)`로 만든다. 자격증명을 코드에 쓰지 않는다.
  - `main(argv=None)`, `if __name__ == "__main__"`
- [x] T016 [US2] `services/tms-eda/` 안에서 `ruff check .`와 `pytest tests/test_run_backfill.py`를 실행해 통과시킨다(T013).

**Checkpoint**: 백필 명령이 mock 기준으로 모든 시나리오를 통과한다. `terraform validate`도 통과한다.

---

## Phase 4: User Story 1 - 분석 담당이 24개월 원본을 SQL로 조회한다 (Priority: P1)

**Goal**: 변환 결과를 카탈로그에 등록하고, 한도가 걸린 Athena 작업 공간에서 조회할 수 있게 한다.

**Independent Test**: (apply·백필 후, 사람이 확인) `SHOW TABLES IN tms_eda`에 `tw_cems_raw` 하나만 있다. 한 달 조건을 붙인 집계가 1분 안에 끝난다. 10GB를 넘는 쿼리는 중단된다.

### Implementation for User Story 1

- [x] T017 [US1] `infra/stacks/tms-eda/main.tf`에 `aws_glue_catalog_database.eda`(`name = "tms_eda"`, 설명에 "Athena EDA 전용, Silver 입력 아님")를 추가한다.
- [x] T018 [US1] `infra/stacks/tms-eda/main.tf`에 `aws_glue_crawler.tw_cems_raw`를 추가한다(research R9).
  - `name = "tms-eda-tw-cems-crawler"`, `role = aws_iam_role.glue.arn`, `database_name = aws_glue_catalog_database.eda.name`
  - `s3_target { path = "s3://${aws_s3_bucket.eda.id}/tw_cems_raw/", exclusions = ["**/_SUCCESS"] }`
  - `schedule`를 두지 않는다.
  - `recrawl_policy { recrawl_behavior = "CRAWL_EVERYTHING" }`
  - `schema_change_policy { update_behavior = "UPDATE_IN_DATABASE", delete_behavior = "LOG" }`
  - `configuration = jsonencode({ Version = 1.0, Grouping = { TableGroupingPolicy = "CombineCompatibleSchemas" }, CrawlerOutput = { Partitions = { AddOrUpdateBehavior = "InheritFromTable" } } })`
- [x] T019 [US1] `infra/stacks/tms-eda/main.tf`에 `aws_athena_workgroup.eda`를 추가한다.
  - `name = "tms-eda"`
  - `configuration`: `enforce_workgroup_configuration = true`, `publish_cloudwatch_metrics_enabled = true`, `bytes_scanned_cutoff_per_query = var.athena_bytes_scanned_cutoff`
  - `result_configuration { output_location = "s3://${aws_s3_bucket.eda.id}/athena-results/", encryption_configuration { encryption_option = "SSE_S3" } }`
  - `force_destroy`는 쓰지 않는다.
- [x] T020 [US1] `infra/stacks/tms-eda/outputs.tf`를 작성한다. 각 출력에 `description`을 둔다.
  - `eda_bucket_name`, `glue_role_arn`, `glue_job_names`(map의 키 목록)
  - `crawler_name`, `athena_workgroup_name`, `glue_database_name`

**Checkpoint**: `terraform validate`가 통과한다. 스택에 계획한 리소스가 모두 정의되어 있다.

---

## Phase 5: User Story 3 - 변환 결과가 원본과 같다는 것을 확인한다 (Priority: P2)

**Goal**: 변환 스크립트가 키·값·행 수를 보존하는지 자동 테스트로 보장한다.

**Independent Test**: `pytest tests/test_tw_cems_parquet.py`가 통과한다.

### Tests for User Story 3

- [x] T021 [US3] `services/tms-eda/tests/conftest.py`를 작성한다.
  - 세션 범위 `spark` fixture: `local[2]`, `spark.ui.enabled=false`, `spark.sql.shuffle.partitions=2`, 세션 시간대 UTC
  - 끝나면 `stop()`
  - `fixtures_dir` fixture
- [x] T022 [US3] `services/tms-eda/tests/test_tw_cems_parquet.py`를 작성한다(`tmp_path`에 출력). 독스트링에 fixture가 **가짜 데이터**임을 적는다.
  - **행 수**: `synthetic_edge_cases.jsonl`의 비어 있지 않은 줄 수 = 출력 Parquet `count()`. 손상 줄 1개가 `_corrupt_record` 값이 있는 행 1개로 남는다.
  - **키 보존**: 입력 모든 줄의 키 합집합 ⊆ 출력 컬럼. `source_file` 컬럼이 있고 값이 입력 파일 경로로 끝난다.
  - **값 보존**:
    - `std == "nan"` 행이 문자열 `"nan"` 그대로
    - 빈 문자열이 `""` 그대로
    - 숫자 리터럴이 문자열 타입
    - 모든 원본 키 컬럼의 타입이 `StringType`
  - **중복 행 유지**: 같은 내용의 두 줄이 두 행으로 남는다.
  - **두 월**: `synthetic_month_b.jsonl`을 다른 월로 변환해도 각자의 키를 갖고, 두 결과를 `unionByName(allowMissingColumns=True)`로 합칠 수 있다.
  - **재실행**: 같은 월을 두 번 변환한 뒤 행 수가 한 번 실행했을 때와 같다(overwrite). 다른 월 폴더는 그대로다.
  - **완료 표지**: 성공한 출력 폴더에 `_SUCCESS`가 있다. 파일은 `part-*.parquet` 2개 이하다.
  - **대소문자 충돌**: `synthetic_case_conflict.jsonl`이면 `ValueError`가 나고 출력 폴더가 만들어지지 않는다.
  - **인자**:
    - `parse_args`가 Glue 추가 인자(`--JOB_NAME x --TempDir s3://…`)를 무시한다.
    - `--month 3`이나 `--month 13`은 오류다.
    - `--local`인데 경로가 없으면 오류다.
    - `resolve_paths`가 `year=2025/month=03/` 형태를 만든다.
- [x] T023 [US3] `services/tms-eda/` 안에서 `pytest tests/test_tw_cems_parquet.py`를 실행해 통과시킨다. 실패하면 T012를 고친다. Java 17이 없으면 사용자에게 설치를 요청하고 이 작업은 대기로 둔다.

**Checkpoint**: 로컬에서 `ruff check .`와 `pytest`가 전부 통과한다.

---

## Phase 6: Polish & Cross-Cutting

- [x] T024 [P] `services/tms-eda/README.md`를 작성한다(`tms-collector/README.md` 형식 참고).
  - 목적: Athena EDA 전용, Silver·ML 입력 아님
  - fixture가 가짜 데이터라는 표시
  - 로컬 준비: Java 17, `uv venv --python 3.13`
  - 테스트와 `--local` 실행
  - 백필 흐름: 업로드 완료 확인 → `--dry-run` → 실행 → `--only-missing` → 크롤러(콘솔 Run 또는 `--start-crawler`) → Athena
  - Athena 조회 요령: 워크그룹 `tms-eda`, 파티션 조건(`year='2025' AND month='03'`, 문자열), `try_cast`, 소문자 컬럼, `"_id"`·`"_corrupt_record"` 큰따옴표
  - 표본 행 수 확인 방법(quickstart §4)
  - 비용 확인, 되돌리기(월 단위 재실행)
- [x] T025 [P] `.github/workflows/tms-eda.yml`을 작성한다.
  - `on: push`/`pull_request`, `paths: ["services/tms-eda/**", ".github/workflows/tms-eda.yml"]`
  - `defaults.run.working-directory: services/tms-eda`
  - `actions/checkout@v4` → `actions/setup-java@v4`(`distribution: temurin`, `java-version: "17"`) → `actions/setup-python@v5`(`python-version: "3.13"`) → `pip install -e ".[dev]"` → `ruff check .` → `pytest -q`
  - `permissions: contents: read`
- [x] T026 [P] `.github/CODEOWNERS`의 A 섹션 아래 B 섹션 앞에 `/services/tms-eda/              @SungChul23`를 추가한다(`/infra/`는 이미 A).
- [x] T027 [P] `AGENTS.md`의 "저장소 구조" 트리에 아래 두 줄을 추가한다. 다른 규칙 문구는 바꾸지 않는다.
  - `infra/stacks/tms-eda/` (# TW CEMS Athena EDA: EDA 버킷 + Glue Job·크롤러 + Athena 워크그룹)
  - `services/tms-eda/` (# JSONL → Parquet 변환 Glue 스크립트 + 백필 명령)
- [x] T028 `infra/stacks/tms-eda`에서 아래를 실행한다. 에이전트는 WSL에서 `/mnt/c/terraform/terraform.exe`로 실행한다.
  - `terraform fmt -recursive`
  - `terraform init`: `.terraform.lock.hcl`이 생기면 커밋 대상에 포함
  - `terraform validate`
- [x] T029 `terraform plan`을 실행하고 결과를 사용자에게 보여 준다. **관문:**
  - 생성만 있고 change·destroy는 0건이다.
  - `glue_version = "6.0"`이 받아들여진다.
  - 원본 버킷에 붙는 리소스가 없다.
  - Job의 `default_arguments`에 `--year`·`--month`가 없다.
- [x] T030 `services/tms-eda/` 안에서 `ruff check .`와 `pytest -q`를 전체 실행해 통과를 확인한다. 이어서 [quickstart.md §1](quickstart.md)의 수동 로컬 실행을 한 번 돌려 결과 폴더(`part-*.parquet` 2개 + `_SUCCESS`)를 확인한다.
- [x] T031 🧑 사용자가 PowerShell에서 `terraform apply`를 실행한다.
- [x] T032 🧑 raw 업로드(2026-10분)가 끝난 뒤 사용자가 백필을 실행한다.
  - `run_backfill.py --dry-run`으로 대상이 24개월인지 확인
  - 실행
  - 필요하면 `--only-missing`으로 다시 실행
- [x] T034 🧑 (2026-11-06 범위 확장) 사용자가 2024-01~10을 추가로 변환한다.
  - `run_backfill.py --from 2024-01 --only-missing --dry-run`으로 대상이 10개월이고 나머지 24개월이 `SKIPPED`인지 확인
  - `run_backfill.py --from 2024-01 --only-missing --start-crawler`로 실행
- [x] T035 🧑 (2026-11-06 범위 확장) 사용자가 팀원이 다시 올린 2023-11·12 JSONL을 변환한다.
  - `run_backfill.py --from 2023-11 --only-missing --start-crawler`로 실행 (2023-10은 JSONL이 오면 같은 방식으로 추가)
- [ ] T033 🧑 사용자가 크롤러를 시작하고(T034의 `--start-crawler`로 대신할 수 있다), quickstart §4·§5를 확인한다.
  - 테이블이 하나인지, 월별 행 수가 36행으로 나오는지
  - 표본 1~2개월 행 수 비교(SC-002)
  - 쿼리 시간(SC-005)
  - 원본 객체 수가 그대로인지(SC-006)

---

## Dependencies & Execution Order

```
Phase 1 (T001 → T002~T006 병렬)
  └▶ Phase 2: Terraform 뼈대 (T007 → T008·T009 병렬 → T010 → T011)
              코드 (T012)  ← Terraform과 병렬 가능
        ├▶ Phase 3 US2: T013(테스트) ∥ T014(Job, T011 이후) ∥ T015(코드) → T016
        ├▶ Phase 4 US1: T017 → T018 → T019 → T020   (T010·T011 이후, US2와 병렬 가능)
        └▶ Phase 5 US3: T021 → T022 → T023          (T012 이후, Java 17 필요)
              └▶ Phase 6: T024~T027 병렬 → T028 → T029(관문) → T030 → 🧑 T031 → 🧑 T032 → 🧑 T033
```

- `main.tf`를 고치는 작업(T010, T011, T014, T017~T019)은 같은 파일이라 **순서대로** 한다.
- US1의 실제 확인(T033)은 US2의 실행 결과(T032)가 있어야 한다. 코드 작업은 서로 독립이다.

## Parallel Examples

- **Phase 1**: T002(pyproject), T003(.gitignore), T004~T006(fixtures)을 동시에 작성한다.
- **US2**: T013(`test_run_backfill.py`)과 T015(`run_backfill.py`)를 같이 쓰고, T014(`main.tf`)를 별도로 진행한다.
- **Phase 6**: T024(README), T025(CI), T026(CODEOWNERS), T027(AGENTS.md)을 동시에 진행한다.

## Implementation Strategy

1. **MVP = Phase 1~3 + T028~T029**: Job, 역할, 버킷, 백필 명령이 있으면 변환을 시작할 수 있다. 크롤러는 콘솔에서 임시로 만들 수도 있지만, 원칙 III에 따라 같은 PR에서 US1까지 Terraform으로 넣는다.
2. 업로드 완료(2026-11-05쯤) 전에 Phase 1~6의 코드·plan을 끝내고, 사용자가 apply한다.
3. 업로드가 끝나면 T032 → T033 순서로 진행한다.
4. **커밋 단위(작업별):**
   - ① Setup(.gitignore, pyproject, fixtures)
   - ② 변환 스크립트 + US3 테스트
   - ③ 백필 명령 + 테스트
   - ④ Terraform 스택
   - ⑤ CI·CODEOWNERS·AGENTS.md·README
   - ⑥ spec 문서
   - 커밋은 사용자가 요청할 때만 한다.
