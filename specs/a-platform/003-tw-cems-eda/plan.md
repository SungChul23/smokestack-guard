# Implementation Plan: TW CEMS Athena EDA 환경 (JSONL → Parquet 1회 변환)

**Branch**: `12-cems-athena-eda-환경-jsonl-parquet-1회-변환` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md) | **Issue**: #12

**Input**: Feature specification from `specs/a-platform/003-tw-cems-eda/spec.md`

## Summary

새 스택 `infra/stacks/tms-eda`에 아래 리소스를 만든다.
- EDA 전용 버킷
- Glue 실행 역할
- Glue DB `tms_eda`
- Glue 6.0 Job `tms-eda-tw-cems-parquet`
- 수동 크롤러
- Athena 워크그룹

Job은 원본 월 파일 하나를 고정 스키마 없이 문자열 그대로 읽는다. 손상된 줄도 남기고, `tw_cems_raw/year=/month=/`에 Parquet 2개로 덮어쓴다. 완료 표지는 Spark 기본 `_SUCCESS`를 쓴다. 행 수 일치는 표본 월만 사람이 확인한다(사용자 결정, R5). 사용자는 업로드가 끝난 뒤 `run_backfill.py`로 36개월(2023-11~2026-10)을 한 번에 돌리고, 크롤러를 수동으로 실행해 Athena에서 조회한다.

## Technical Context

**Language/Version**: Python 3.13 (Glue 6.0과 맞춤), Terraform `~> 1.15.0`

**Primary Dependencies**:
- Glue 런타임: PySpark 4.1.1, boto3 (Glue 기본 포함, 추가 패키지 없음)
- 로컬 dev: `pyspark==4.1.1`, `boto3`, `pytest`, `ruff`
- provider: `aws ~> 6.0` (6.71.0). `archive`는 불필요(스크립트 1개)

**Storage**:
- 원본 버킷 `smokestack-tms-raw-952900391026`: `bronze/tw_cems/` 읽기 전용
- 새 EDA 버킷 `smokestack-tms-eda-952900391026`

**Testing**: pytest + 로컬 SparkSession(Java 17), boto3는 mock. Terraform은 `fmt`/`validate`/`plan`. → [quickstart.md](quickstart.md)

**Target Platform**: AWS `ap-northeast-2` (Glue 6.0, Athena), 로컬 WSL, GitHub Actions(ubuntu)

**Project Type**: 인프라 스택(IaC) + 배치 변환 스크립트 + 운영 CLI

**Performance Goals**: 월당 10분 이내(timeout 30분), 24개월을 동시 실행 6개 × 10 DPU로 15분 안팎(추정, R7)

**Constraints**:
- 원본 쓰기·삭제 금지
- 고정 스키마 금지
- 값 해석 금지
- 기존 리소스 변경 금지
- AI 에이전트는 AWS에 대해 스크립트를 실행하지 않음

**Scale/Scope**:
- 입력: 36개 파일, 약 91GB, 월 약 300만 줄(2024-03 기준) × 36 (2026-11-06 범위 확장 전에는 24개, 약 60GB)
- 출력: 월 2개 파일

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 판정 | 근거 |
|---|---|---|
| I. 수집 연속성 | ✅ | 수집 스택·스케줄은 손대지 않는다. 원본 버킷은 `data`로 참조만 한다. 역할에는 `bronze/tw_cems/*` 읽기 권한만 준다(쓰기·삭제 없음). 수명 주기는 EDA 버킷에만 건다. |
| II. 비밀값 비공개 | ✅ | API 키가 필요 없다. 자격증명은 실행자 프로필에서 읽는다. 로그에는 요약 숫자만 남기고 데이터 값은 남기지 않는다. |
| III. 코드로, 적용은 사람이 | ✅ | 모든 리소스를 Terraform으로 만든다. 에이전트는 `plan`까지만 한다. 백필과 크롤러 실행은 사용자가 한다. 권한은 아래 표의 최소 범위다. |
| IV. 데이터 계약 우선 | ✅ | 새 산출물 계약을 [contracts/tw-cems-raw-parquet.md](contracts/tw-cems-raw-parquet.md)에 두었다. Silver 입력 계약은 아니다(EDA 전용 명시). C를 PR 리뷰어로 넣는다. |
| V. 같은 조건의 비교 | 해당 없음 | |
| VI. 설명 가능한 결과 | ✅ | 모든 행에 `source_file`이 있어 원본 파일까지 추적할 수 있다. 손상 줄은 `_corrupt_record`에 원문으로 남는다. |
| 비용 | ✅ | 아래 표 |
| 외부 패키지 | ✅ | Glue 런타임에 추가 패키지가 없다. dev 의존성(pyspark, pytest, ruff)은 테스트용이다. |

### 부여 권한 (새 역할 `tms-glue-eda`, 신뢰 대상 `glue.amazonaws.com`)

| 권한 | 범위 | 이유 |
|---|---|---|
| 관리형 `AWSGlueServiceRole` | (AWS 정의) | Glue 카탈로그, `/aws-glue/*` 로그, 지표. `aws-glue-*` 버킷 접근이 포함되지만 이 기능은 쓰지 않는다 |
| `s3:ListBucket` | 원본 버킷, 조건 `s3:prefix` = `bronze/tw_cems/*` | Spark가 입력 파일 상태를 확인 |
| `s3:GetObject` | `raw/bronze/tw_cems/*` | 원본 읽기. **쓰기·삭제 권한 없음** |
| `s3:ListBucket` | EDA 버킷 전체 | 덮어쓰기 경로 조회, 크롤러 탐색. EDA 전용 버킷이라 범위 제한 이득이 작다(Complexity Tracking) |
| `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, `s3:AbortMultipartUpload` | `eda/tw_cems_raw/*`, `eda/glue-temp/*` | Parquet·`_SUCCESS` 쓰기, 월 단위 덮어쓰기에 필요한 삭제, 임시 파일 |
| `s3:GetObject` | `eda/glue-scripts/*` | Job 스크립트 내려받기 |

크롤러도 같은 역할을 쓴다. 사람의 `iam:PassRole`은 팀 정책의 `tms-*` 허용 범위 안이다.

### 비용 추정

| 항목 | 사용량 | 예상 |
|---|---|---|
| Glue Job (1회 백필) | 24회 × 10 DPU × 약 3분, $0.308/DPU-시간 | **약 $4~6** (재실행 포함 $20 이하) |
| 크롤러 (1~2회) | 최소 10분 과금, $0.44/DPU-시간 | 약 $0.1~0.4 |
| Athena | Parquet 조회, 쿼리당 10GB 상한 | EDA 기간 $1 미만(추정) |
| S3 저장 | Parquet 약 5~10GB(추정) + 결과·임시 | 월 $0.3 미만 |
| CloudWatch Logs | 로그 그룹 1개, 14일 | 무시 가능 |

**합계: 1회 약 $5~10, 이후 월 $1 미만(추정).**

## 설계

### 스택 `infra/stacks/tms-eda/`

| 파일 | 내용 |
|---|---|
| `backend.tf` | key `stacks/tms-eda/terraform.tfstate`, 나머지는 `tms-collection`과 같음 |
| `versions.tf` | `required_version ~> 1.15.0`, `aws ~> 6.0`, `default_tags { project="tms", managed_by="terraform", stack="tms-eda" }` |
| `variables.tf` | `raw_bucket_name`, `eda_bucket_name`, `glue_worker_count`(10), `athena_bytes_scanned_cutoff`(10737418240). 모두 `description`·`type`·기본값 |
| `main.tf` | 아래 리소스 |
| `outputs.tf` | `eda_bucket_name`, `glue_role_arn`, `glue_job_names`, `crawler_name`, `athena_workgroup_name`, `glue_database_name` |

`main.tf` 구성:

| 리소스 | 이름·설정 |
|---|---|
| `data.aws_s3_bucket.raw` | 원본 버킷 참조 |
| `aws_s3_bucket.eda` + ownership/versioning/SSE/public access block | `prevent_destroy`, `force_destroy` 없음 |
| `aws_s3_bucket_lifecycle_configuration.eda` | R10 표 |
| `aws_iam_role.glue` + 정책 부착 + `aws_iam_role_policy.glue_data` | 권한 표 |
| `aws_cloudwatch_log_group.glue` | `/aws-glue/tms-eda`, 14일 |
| `aws_glue_catalog_database.eda` | `tms_eda` |
| `aws_s3_object.job_script` (`for_each = local.glue_jobs`) | `glue-scripts/<script>`, `etag = filemd5()` |
| `aws_glue_job.this` (`for_each = local.glue_jobs`) | 아래 map |
| `aws_glue_crawler.tw_cems_raw` | R9 |
| `aws_athena_workgroup.eda` | `tms-eda`, 결과 `s3://…/athena-results/`(SSE_S3), `enforce_workgroup_configuration = true`, `bytes_scanned_cutoff_per_query = 10GB` |

Job map (`locals`). Job을 늘릴 때는 항목 하나만 추가한다.

```hcl
locals {
  glue_jobs = {
    "tms-eda-tw-cems-parquet" = {
      script         = "tw_cems_parquet.py"
      workers        = var.glue_worker_count   # G.1X
      timeout        = 30
      max_concurrent = 6
      arguments = {
        "--raw_bucket"    = var.raw_bucket_name
        "--raw_prefix"    = "bronze/tw_cems/historical"
        "--eda_bucket"    = var.eda_bucket_name
        "--output_prefix" = "tw_cems_raw"
      }
    }
  }
  glue_common_arguments = {
    "--job-language"                     = "python"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--TempDir"                          = "s3://${var.eda_bucket_name}/glue-temp/"
    "--enable-continuous-cloudwatch-log" = "true"
    "--continuous-log-logGroup"          = aws_cloudwatch_log_group.glue.name
    "--enable-metrics"                   = "true"
  }
}
```

공통 설정: `glue_version = "6.0"`, `worker_type = "G.1X"`, `max_retries = 0`, `execution_class = "STANDARD"`, `script_location`은 `aws_s3_object` 참조(업로드 뒤 Job 생성). `--year`·`--month`는 넣지 않는다.

### 코드 `services/tms-eda/`

`tms-collector`(스크립트 + README)와 같은 평평한 구조다.

**`tw_cems_parquet.py`** (Glue Job 스크립트, 로컬 겸용)
1. `parse_args(argv)`: `parse_known_args`로 처리하고, `--local`이면 입출력 경로가 필수다 (R12).
2. `build_spark(local)`: 로컬은 `local[2]`, 세션 시간대 UTC.
3. `convert(spark, input_path, output_path) -> dict`:
   - R3 옵션으로 읽는다.
   - `source_file` 컬럼을 추가한다.
   - R6 컬럼 충돌을 검사한다.
   - `repartition(2)` 후 overwrite로 쓴다 (R4). Spark가 `_SUCCESS`를 남긴다.
   - 요약 dict(컬럼 목록 등)를 반환한다. 추가 `count()`는 하지 않는다 (R5).
4. `main()`: 경로를 조립(`s3://raw/prefix/YYYY-MM.jsonl` → `s3://eda/tw_cems_raw/year=YYYY/month=MM/`)하고, convert를 실행한 뒤 요약 로그 한 줄을 남긴다.

**`run_backfill.py`**: [run-interface §2](contracts/run-interface.md). 핵심 함수는 테스트할 수 있게 나눈다.
- `parse_months(keys, from, to)`
- `plan_targets(...)`
- `run_all(glue, months, concurrency)`: 시작·폴링·재시도 1회
- `estimate_cost(run)`
- `render_table(results)`

**`tests/`**
- `conftest.py`: 세션 범위 로컬 SparkSession
- `fixtures/synthetic_edge_cases.jsonl`: **가짜 데이터**, 파일 첫 줄 아님. README와 테스트 독스트링에 표시한다. 다음을 담는다.
  - 키 15개 기본 행
  - `flareno`·`locationno` 행
  - 시각 형식 3종
  - `std:"nan"`
  - 같은 키 중복 행
  - 손상 줄 1개
  - 빈 줄 1개
- `fixtures/synthetic_month_b.jsonl`: 키 구성이 다른 두 번째 월
- `fixtures/synthetic_case_conflict.jsonl`: `ImportDate`와 `importdate`가 같이 있는 샘플
- `test_tw_cems_parquet.py`, `test_run_backfill.py`

**`pyproject.toml`**:
- `requires-python = ">=3.13,<3.14"`
- `[project.optional-dependencies] dev`
- `[tool.pytest.ini_options] pythonpath = ["."]`
- `[tool.ruff]` line-length 100, target py313

**`README.md`**:
- 목적: EDA 전용이며 Silver 입력이 아님
- 로컬 테스트·실행
- 백필 흐름: dry-run → 실행 → 크롤러 → Athena
- Athena 조회 요령: 파티션 조건, `try_cast`, 소문자 컬럼, `"_id"`
- 비용 확인
- 되돌리기

### 저장소 공통

| 파일 | 변경 |
|---|---|
| `.github/workflows/tms-eda.yml` | 신규. `services/tms-eda/**`와 자기 자신이 바뀌는 push·PR에서 실행. Temurin 17 + Python 3.13 → `pip install -e ".[dev]"` → `ruff check` → `pytest` |
| `.github/CODEOWNERS` | `/services/tms-eda/ @SungChul23` 추가 (`/infra/`는 이미 A) |
| `AGENTS.md` | 저장소 구조에 `infra/stacks/tms-eda/`, `services/tms-eda/` 추가 |
| `.gitignore` | `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `spark-warehouse/`, `metastore_db/`, `derby.log` 추가 |

## Project Structure

### Documentation (this feature)

```text
specs/a-platform/003-tw-cems-eda/
├── spec.md
├── plan.md                         # 이 파일
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── tw-cems-raw-parquet.md      # EDA 테이블 계약 (C·E가 읽음)
│   └── run-interface.md            # Job 인자, 백필 명령
├── checklists/requirements.md
└── tasks.md                        # /speckit-tasks
```

### Source Code (repository root)

```text
infra/stacks/tms-eda/               # 신규
├── backend.tf
├── versions.tf
├── variables.tf
├── main.tf
├── outputs.tf
└── .terraform.lock.hcl             # init 후 커밋
services/tms-eda/                   # 신규
├── tw_cems_parquet.py
├── run_backfill.py
├── pyproject.toml
├── README.md
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   ├── synthetic_edge_cases.jsonl
    │   ├── synthetic_month_b.jsonl
    │   └── synthetic_case_conflict.jsonl
    ├── test_tw_cems_parquet.py
    └── test_run_backfill.py
.github/workflows/tms-eda.yml       # 신규
.github/CODEOWNERS, AGENTS.md, .gitignore   # 수정 (한두 줄)
```

**Structure Decision**: 별도 스택으로 둔다.
- 수집(`tms-collection`)과 업무 단위가 다르다(EDA, 1회성).
- 원본 버킷은 이름 하나로 `data` 참조하면 충분하다.
- 목적이 끝나면 스택째 정리할 수 있다.

모듈은 만들지 않는다. 재사용 대상이 아직 없다. Job은 `for_each` map으로 늘릴 수 있다.

## 요구사항 추적

| FR | 구현 |
|---|---|
| FR-001 월 목록·범위 | `run_backfill.parse_months` (S3 목록 + 정규식 + 범위) |
| FR-002 키 보존 | `convert`: 스키마 없이 추론, 전체 샘플링 |
| FR-003 값 보존 | `primitivesAsString`, 변환·필터 없음 |
| FR-004 손상 줄·행 수 | PERMISSIVE + `_corrupt_record`. 로컬 테스트로 행 수 일치 확인, 운영은 표본 월 수동 확인 (R5) |
| FR-005 출처 | `source_file = _metadata.file_path` |
| FR-006 월 파티션·교체 | 월 경로 overwrite |
| FR-007 완료 표지 | Spark 기본 `_SUCCESS` |
| FR-008 일괄 실행 | `run_backfill.py` 옵션 |
| FR-009 결과 표 | `render_table`, `estimate_cost` |
| FR-010 수동 카탈로그 | 크롤러 스케줄 없음, `--start-crawler` |
| FR-011 로컬 실행 | `--local`, pytest |
| FR-012 자동 검사 | `.github/workflows/tms-eda.yml` |
| FR-013 테이블·파티션 | 크롤러 → `tms_eda.tw_cems_raw` |
| FR-014 스캔 한도 | 워크그룹 `bytes_scanned_cutoff_per_query`, 설정 강제 |
| FR-015 만료 | EDA 버킷 수명 주기 (R10) |
| FR-016 원본 읽기 전용 | 역할 권한 표 |
| FR-017 최소 권한 | 역할 권한 표 |
| FR-018 기존 리소스 불변 | 새 스택, `data` 참조, plan 생성만 확인 |
| FR-019 이름에 eda | 모든 리소스 이름 |

## Constitution Check (Phase 1 이후 재점검)

설계 후에도 위반은 없다. 지시서와 달라진 점은 아래 표에 기록했다.

## Complexity Tracking

| 위반·예외 | 필요한 이유 | 더 단순한 대안을 택하지 않은 이유 |
|---|---|---|
| `coalesce(2)` 대신 `repartition(2)` | `coalesce`는 읽기·파싱 병렬도까지 2로 줄여 느려진다 | 셔플 비용이 병렬 파싱 이득보다 작다 |
| EDA 버킷 `ListBucket`에 경로 조건 없음 | Spark 덮어쓰기와 크롤러가 상위 경로(접두어 `/` 없는 형태 포함)를 조회한다 | 조건을 걸면 실패 위험이 있고, EDA 전용 버킷이라 노출되는 것은 객체 이름뿐이다 |
| Glue 공용 로그 그룹(`/aws-glue/jobs/output`·`error`)의 보존 기간을 관리하지 않음 | 계정에 이미 있고 테스트 리소스와 공유한다 | 가져오면 다른 리소스에 영향이 간다. 연속 로그는 전용 그룹(14일)으로 보낸다 |
