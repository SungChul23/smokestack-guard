# Implementation Plan: K-TMS Silver·ML-ready 매일 갱신 파이프라인

**Branch**: `46-a-k-tms-silverml-ready-매일-갱신-파이프라인-glue-iceberg-silver2` | **Date**: 2026-11-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/a-platform/008-ktms-silver-pipeline/spec.md`

## Summary

K-TMS 원본(`tms_cleansys/`, `_SUCCESS` 있는 폴더)으로 Iceberg 테이블 두 개를 매일 갱신한다.

- `tms_silver2.ktms`: Silver, 9컬럼, `days(ts_kst)` 파티션
- `tms_silver2.ktms_ml_ready`: ML-ready, 35컬럼, `days(measured_at)` 파티션

매일 03:00 KST에 EventBridge Scheduler가 Step Functions를 시작하고, Step Functions가 Glue 5.0 잡 두 개(Silver → ML-ready)를 차례로 실행한다. 각 잡은 다음 순서로 동작한다.

1. driver에서 C의 pandas 함수(`read_bronze`, `to_silver`, `to_ml_ready`)를 수정 없이 부른다.
2. 결과를 Spark DataFrame으로 바꾼다.
3. 대상 날짜 범위만 Iceberg 커밋 1번으로 교체한다.

실패하면 1회 재시도하고, 그래도 실패하면 기존 SNS 토픽으로 알린다. 처음 전체 생성은 같은 흐름을 사람이 범위를 지정해 실행한다. 합성은 이번에 인자 입구만 둔다(research R9).

## Technical Context

**Language/Version**: Python 3.11 (Glue 5.0), Terraform 1.15.8 / AWS provider ~> 6.0

**Primary Dependencies**:
- Glue 5.0: Spark 3.5.4, Iceberg 1.7.1 내장(`--datalake-formats iceberg`), pandas·numpy·boto3 기본 제공
- C의 `smokestack_guard.silver`(zip, `--extra-py-files`)
- 새 런타임 패키지 없음
- 개발용: 기존 `services/tms-silver` dev 의존성 + `iceberg-spark-runtime-3.5_2.12:1.7.1`(테스트 때 Maven에서 받음)

**Storage**: S3 원본 버킷 `smokestack-tms-raw-952900391026`
- 입력: `tms_cleansys/` 읽기만
- 테이블: `silver2/ktms/`, `silver2/ktms_ml_ready/` (Iceberg v2, Glue Data Catalog `tms_silver2`)
- 실행 기록: `silver2/_runs/ktms*/`

**Testing**: pytest
- 단위: 범위 계산, ML-ready 앞뒤 범위 동등성
- Iceberg 통합: 로컬 Hadoop 카탈로그, 표시 `iceberg`
- CI: `.github/workflows/tms-silver.yml`
- 실제 데이터 비교: quickstart

**Target Platform**: AWS Glue 5.0(G.1X × 2), Step Functions Standard, EventBridge Scheduler (ap-northeast-2)

**Project Type**: 데이터 파이프라인(배치 잡 + 오케스트레이션 + IaC)

**Performance Goals**: 매일 실행이 수 분 안에 끝난다(잡 제한 시간 60분). 2일치 Silver 약 60만 행이다.

**Constraints**:
- C의 `src/smokestack_guard/silver/`는 수정하지 않는다.
- 원본에 쓰기·삭제를 하지 않는다.
- 같은 테이블에는 동시에 하나만 쓴다.
- `terraform apply`와 AWS 실행은 사람이 한다.

**Scale/Scope**:
- 원본: 10분 스냅샷, 하루 최대 144개
- Silver: 하루 약 30만 행, 2026-10-30부터 프로젝트 끝(12월 중순)까지 약 1,500만 행
- 파티션: 50개 안팎

## Constitution Check

*GATE: Phase 0 전 확인, Phase 1 뒤 다시 확인.*

| 원칙 | 확인 | 결과 |
|---|---|---|
| **I. 수집 연속성** | 수집 Lambda·스케줄을 건드리지 않는다. `tms_cleansys/`는 읽기 권한만 준다(권한 표). Iceberg 파일은 `silver2/ktms*/`에만 쓰고, 오래된 버전 정리(삭제)는 범위 밖이다. 원본 버킷에 수명 주기 규칙을 두지 않는다. | 통과 |
| **II. 비밀값 비공개** | 비밀값이 없다. 알림 메일 주소는 기존 tms-collection 스택의 구독을 그대로 쓰고, 이 스택은 토픽 이름만 참조한다. | 통과 |
| **III. 코드로 만들고 적용은 사람이** | 잡·역할·상태 머신·스케줄은 Terraform이 만든다. **Iceberg 테이블은 잡의 DDL(`CREATE TABLE IF NOT EXISTS`)이 만든다**(Complexity Tracking). 에이전트는 `fmt`·`validate`까지만 한다. 권한 목록은 아래에 있다. | 조건부 통과 |
| **IV. 데이터 계약 우선** | 계약: [contracts/ktms-tables.md](contracts/ktms-tables.md)(읽는 법), [data-model.md](data-model.md)(저장 형식), [contracts/run-interface.md](contracts/run-interface.md)(실행). 컬럼 의미는 C의 코드가 정한다. **테이블 형식·파티션은 C의 리뷰를 받는다.** E에게는 PR로 알린다. | 통과(리뷰 필요) |
| **V. 같은 조건의 정직한 비교** | 학습 데이터는 `snapshot_id`로 고정할 수 있다. 합성은 별도 테이블이라 실측 평가에 섞이지 않는다. | 통과 |
| **VI. 설명 가능한 결과** | 실행 기록에 `snapshot_id`와 `package_md5`(규칙 코드 버전)가 같이 남고, Iceberg 스냅샷 요약에 `job_run_id`가 남는다. | 통과 |
| 운영: 비용 | Glue 월 약 $2.5~3.5. 나머지는 무료 한도 안이거나 월 $0.1 미만이다(research R12). | 기록함 |
| 운영: 외부 패키지 | 런타임 추가 없음. 테스트용 Iceberg jar만 추가(Glue와 같은 버전). | 기록함 |

**Phase 1 뒤 재확인**: 설계 문서에서 원칙 위반이 새로 생기지 않았다. III의 예외는 그대로 Complexity Tracking에 둔다.

### IAM 권한 목록 (원칙 III)

| 역할 | 권한 | 범위 | 이유 |
|---|---|---|---|
| `tms-glue-silver2-ktms` (Silver 잡) | `AWSGlueServiceRole` 관리형 | | 다른 Glue 잡과 같다 |
| | `s3:ListBucket` | 원본 버킷, 접두어 `tms_cleansys/*`, `silver2/ktms/*`, `silver2/_runs/ktms/*`, `ops/glue-*` | `read_bronze`의 폴더 목록, Iceberg 파일 목록 |
| | `s3:GetObject` | `tms_cleansys/*`, `ops/glue-scripts/*`, `ops/glue-packages/*` | 원본, 스크립트, C 코드 zip 읽기 |
| | `s3:GetObject`, `PutObject`, `DeleteObject` | `silver2/ktms/*`, `silver2/_runs/ktms/*` | 테이블 쓰기. 삭제는 실패한 커밋의 미사용 파일을 지울 때만 쓴다 |
| | `glue:GetDatabase`, `GetTable`, `CreateTable`, `UpdateTable` | `tms_silver2` DB, `ktms` 테이블 | Iceberg 카탈로그 갱신 |
| | `logs:*` (로그 그룹 1개) | `/aws-glue/tms-silver` | 기존 그룹 |
| `tms-glue-silver2-ktms-ml-ready` (ML-ready 잡) | 위와 같은 형태 | 읽기: `silver2/ktms/*` / 쓰기: `silver2/ktms_ml_ready/*`, `silver2/_runs/ktms_ml_ready/*` / 카탈로그: `ktms` 읽기, `ktms_ml_ready` 생성·갱신 | 원본(`tms_cleansys/`) 권한 없음 |
| `tms-sfn-silver2-ktms` (상태 머신) | `glue:StartJobRun`, `GetJobRun`, `GetJobRuns`, `BatchStopJobRun` | 잡 2개 | `.sync` 실행 |
| | `sns:Publish` | `tms-collector-alerts` | 실패 알림 |
| `tms-scheduler-silver2-ktms` (스케줄) | `states:StartExecution` | 상태 머신 1개 | 매일 실행 |

- 원본 버킷 정책이나 다른 스택의 리소스는 바꾸지 않는다. SNS 토픽은 `data "aws_sns_topic"`으로 이름만 참조한다.
- `ListBucket`의 접두어 조건이 부족하면 첫 실행 로그의 `AccessDenied`를 보고 읽기 접두어만 넓힌다. 쓰기는 넓히지 않는다.

## Project Structure

### Documentation (this feature)

```text
specs/a-platform/008-ktms-silver-pipeline/
├── spec.md
├── plan.md              # 이 파일
├── research.md          # R1~R13 결정
├── data-model.md        # 테이블 2개, 범위, 실행 기록
├── quickstart.md        # 배포·검증 순서 (SC-001~007)
├── contracts/
│   ├── ktms-tables.md   # 읽는 법 (E·D·C)
│   └── run-interface.md # Step Functions 입력, Glue 인자, 실행 기록, run_ktms.py
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks에서 만든다
```

### Source Code (repository root)

```text
services/tms-silver/                  # 기존 폴더에 추가 (CEMS와 같은 패키징·CI)
├── ktms_pipeline.py                  # 공통: 범위 계산, Iceberg 세션·DDL, 범위 교체 쓰기, 실행 기록
├── glue_ktms_silver.py               # Silver 잡 진입 스크립트 (로컬 겸용)
├── glue_ktms_ml_ready.py             # ML-ready 잡 진입 스크립트 (로컬 겸용)
├── run_ktms.py                       # 사람이 실행: backfill / rerun / runs
├── pyproject.toml                    # py-modules에 추가, pytest 표시 iceberg
├── README.md                         # K-TMS 절 추가
└── tests/
    ├── test_ktms_pipeline.py         # 단위
    ├── test_ktms_iceberg.py          # Iceberg 통합 (표시 iceberg)
    └── test_run_ktms.py              # 묶음 계획, 상태 확인 (가짜 boto3)

infra/stacks/tms-silver/
├── ktms.tf                           # Glue 잡 2, 역할 4, 상태 머신, 스케줄, 스크립트 업로드
├── ktms_pipeline.asl.json            # 상태 머신 정의 (templatefile)
└── variables.tf                      # ktms_schedule_enabled, ktms_worker_count 추가

AGENTS.md                             # S3 경로 규칙에 Iceberg 예외, 저장소 구조 설명 (research R13)
.github/workflows/tms-silver.yml      # 테스트를 두 단계로: 일반(not iceberg) → Iceberg(jar가 필요해 SparkSession을 따로 띄운다)
```

**Structure Decision**: 기존 `tms-silver` 스택과 `services/tms-silver/`에 넣는다.
- C 코드 zip(`ops/glue-packages/smokestack_guard.zip`), `tms_silver2` DB, Glue 로그 그룹, CI를 그대로 쓸 수 있다.
- K-TMS 리소스는 `ktms.tf` 한 파일에 모아 CEMS 리소스와 섞지 않는다.
- 새 스택으로 나누면 zip 패키징과 DB를 두 스택이 나눠 가져야 해서 오히려 복잡하다.

## Complexity Tracking

| 위반 | 필요한 이유 | 더 단순한 대안을 쓰지 않은 이유 |
|---|---|---|
| 원칙 III: Iceberg 테이블(Glue 카탈로그 항목)을 Terraform이 아니라 잡의 DDL이 만든다 | Iceberg는 커밋마다 카탈로그의 `metadata_location`을 바꾼다. Terraform이 관리하면 매일 상태가 달라지고, `apply`하면 테이블이 옛 버전으로 되돌아갈 수 있다. Terraform 입력으로는 Iceberg 숨은 파티션도 지정할 수 없다. | Terraform + `ignore_changes`: 파티션 없는 테이블이 된다. 사람이 Athena DDL을 한 번 실행: 수동 단계가 남는다. DDL은 `ktms_pipeline.py`에 있어 리뷰·재현은 코드로 된다(research R3). |
| AGENTS.md 규칙 예외: `year=/month=` 폴더 파티션 대신 Iceberg 날짜 파티션, 경로가 아닌 카탈로그로 읽기 | 매일 2일을 교체하고 버전으로 학습 데이터를 고정하려면 테이블 형식이 필요하다(이슈 #46 결정). | Parquet 폴더 + 일 단위 덮어쓰기: 교체 도중 읽으면 반쯤 쓰인 상태가 보이고, 과거 버전을 다시 읽을 수 없다(US3). AGENTS.md에 예외를 적는다(FR-021). |

## 구현 순서 (tasks의 뼈대)

1. `ktms_pipeline.py`
   - 범위 계산(`auto`, 수집일 범위, `max_days`)
   - ML-ready 입력 범위
   - 합성 경로 검사
   - 실행 기록
   - 단위 테스트, 특히 ML-ready 앞뒤 범위 동등성
2. Iceberg 부분
   - DDL, `overwrite(범위)`, `snapshot_id` 조회
   - 로컬 Hadoop 카탈로그 통합 테스트
3. `glue_ktms_silver.py`, `glue_ktms_ml_ready.py`: 실패 기록, 요약 출력
4. `infra/stacks/tms-silver/ktms.tf`와 ASL
   - 스케줄은 `DISABLED`로 시작
   - `terraform fmt`, `validate`
5. `run_ktms.py`(backfill, rerun, runs), README
6. AGENTS.md 예외
7. 사람이 실행: `plan`과 `apply`, 하루치 시험, 전체 생성, SC 확인, 스케줄 켜기 (quickstart 1~8)

## 남은 확인 (구현을 막지 않음)

- **C 리뷰**: 테이블 형식·파티션(원칙 IV). 합성 데이터를 올릴 때 `read_bronze`에 경로 인자를 추가하는 것도 요청한다.
- **E 공유**: `contracts/ktms-tables.md`(카탈로그로 읽기, `snapshot_id` 기록, `month_*` 드랍).
- **첫 실행으로 확인**: Glue 5.0 pandas 버전, driver 메모리(`max_days` 7과 묶음 5일이 적당한지), 실제 실행 시간과 비용.
