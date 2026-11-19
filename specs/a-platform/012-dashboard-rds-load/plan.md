# Implementation Plan: 대시보드용 K-TMS 관측 RDS 적재

**Branch**: `62-a-대시보드용-k-tms-관측-rds-적재-파이프라인-30분-매일-정정` | **Date**: 2026-11-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/a-platform/012-dashboard-rds-load/spec.md`

## Summary

D의 화면과 에이전트가 읽을 K-TMS 관측(NOx·SOx, 30분)을 RDS에 채운다. Scheduler가 상태 머신을 30분마다(`recent`)와 매일 03:20(`daily`)에 시작하고, 상태 머신은 RDS가 있을 때만 VPC 안 Lambda를 부른다. Lambda는 원본 버킷의 Bronze를 S3 게이트웨이 엔드포인트로 읽어 C의 `read_bronze`·`to_silver`를 그대로 돌리고, 굴뚝 키·상태 번호만 더해 `obs.measurement_30m`에 UPSERT한다. 최근 4시간에 받은 스냅샷을 측정 시각과 상관없이 반영하므로 늦게 온 정정도 30분 경로가 처리한다. 매일 경로는 S3를 읽지 않고 RDS 안의 SQL로 일일 요약과 매핑 점검만 한다. 학습용 Silver 파이프라인과는 완전히 별개다. DB 접속은 RDS IAM 인증이라 비밀번호가 없고, NAT·인터페이스 엔드포인트도 없다. DB 구조와 사업장 목록 적재는 사람이 베스천 터널로 실행한다.

## Technical Context

**Language/Version**: Python 3.12(Lambda), 실행 명령은 Python 3.11+ · Terraform `~> 1.15.0`, AWS provider `~> 6.0`

**Primary Dependencies**: C의 `smokestack_guard.silver.ktms`(수정 없이), 008 `ktms_pipeline`의 범위 함수(`ingest_dates`, `in_range`), pandas(AWS SDK for pandas 관리형 레이어, 010과 같은 ARN), `pg8000`(순수 파이썬 PostgreSQL 드라이버), boto3(런타임 내장)

**Storage**: RDS PostgreSQL 16(`tms-db`, 009) — 스키마 `ref`·`obs`·`ops`·`app`·`rag`, pgvector 확장. 원본은 S3 `tms_cleansys/`(읽기만)

**Testing**: pytest — 순수 함수 단위 테스트, PostgreSQL 16 컨테이너로 UPSERT·권한 통합 테스트. CI 워크플로 `dashboard-load.yml`

**Target Platform**: AWS Lambda(x86_64, VPC 앱 프라이빗 서브넷 2개), Step Functions Standard, EventBridge Scheduler(Asia/Seoul)

**Project Type**: 데이터 적재 파이프라인(서버리스) + 사람이 쓰는 CLI

**Performance Goals**: `recent` 1회 60초 안(약 4천~2만 행), `daily` 1회 1분 안(SQL만), 다시 채우기 하루 1회 3분 안(전체 1시간 안, SC-006)

**Constraints**: NAT 없음 → Lambda 안에서 S3 외 AWS API 호출 없음(research R1). 비밀값 없음(IAM 인증). RDS는 평소 꺼져 있음. 수집 경로 변경 없음

**Scale/Scope**: 하루 약 18만~20만 행, 12월 중순까지 약 1,000만 행(2~2.5GB). 굴뚝 약 3,480, 사업장 909

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 판정 | 근거 |
|---|---|---|
| I. 수집 연속성 | 통과 | 원본은 읽기만 한다. 수집 Lambda·스케줄·`tms_cleansys/` 쓰기를 바꾸지 않는다(FR-022). 적재가 멈춰도 수집과 Silver는 영향 없고, 이 기능도 Silver에 의존하지 않는다 |
| II. 비밀값 비공개 | 통과 | RDS IAM 인증으로 적재·앱 계정에 비밀번호가 없다(R4). 관리자 비밀번호는 009의 Secrets Manager 그대로, 사람이 터널에서만 쓴다. 사업장 목록 CSV는 저장소에 넣지 않는다(R9) |
| III. 코드로 만들고 적용은 사람이 | 통과 | 모든 AWS 자원은 Terraform. 에이전트는 `fmt`·`validate`까지, `plan`·`apply`·DB 명령은 A. IAM 권한은 아래 표 |
| IV. 데이터 계약 우선 | 통과 | C의 규칙 함수를 수정 없이 호출한다. 새 계약(RDS 표·키·상태 번호)은 data-model과 contracts에 적고 D와 공유한다. Silver 계약은 바꾸지 않는다 |
| V. 같은 조건의 정직한 비교 | 해당 없음 | 학습·평가와 무관. 합성(`ktms_synth`)은 서비스 표에 넣지 않는다 |
| VI. 설명 가능한 결과 | 통과 | 상태 사유를 null + 상태 번호로 보존해 화면·에이전트가 빈칸 이유를 설명할 수 있다 |

### IAM 권한 (최소)

| 주체 | 권한 | 리소스 | 이유 |
|---|---|---|---|
| 적재 Lambda 역할 | `s3:ListBucket` | 원본 버킷, 접두사 `tms_cleansys/*` 조건 | 스냅샷 폴더 목록 |
| | `s3:GetObject` | `…/tms_cleansys/*` | 스냅샷·`_SUCCESS` 읽기 |
| | `rds-db:connect` | `arn:aws:rds-db:ap-northeast-2:952900391026:dbuser:*/tms_loader` | IAM DB 인증 |
| | `AWSLambdaVPCAccessExecutionRole`(관리형) | — | VPC ENI 생성, 로그 |
| 상태 머신 역할 | `rds:DescribeDBInstances` | `arn:aws:rds:…:db:tms-db` | RDS 존재 확인 |
| | `lambda:InvokeFunction` | 적재 Lambda | |
| | `sns:Publish` | `tms-collector-alerts` | 실패·새 이름 알림 |
| Scheduler 역할 | `states:StartExecution` | 상태 머신 | |

적재 역할에는 원본 버킷 쓰기·삭제, Glue, Athena, Secrets Manager 권한이 없다.

## Project Structure

### Documentation (this feature)

```text
specs/a-platform/012-dashboard-rds-load/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── load-interface.md
├── checklists/requirements.md
└── tasks.md            # /speckit-tasks
```

### Source Code (repository root)

```text
services/dashboard-load/
├── lambda_handler.py        # 진입점: mode 분기, 실행 요약
├── load.py                  # 순수 함수: Bronze 범위 → to_silver → 적재용 정리, 새 굴뚝 키 찾기
├── db.py                    # pg8000 접속(IAM 토큰·TLS), UPSERT, 일일 요약·매핑 점검 SQL, ops 기록
├── run_dashboard_load.py    # 사람 명령: migrate · load-ref · backfill · status
├── migrations/
│   ├── 001_schemas_roles.sql    # 스키마 5개, pgvector, 계정 tms_loader·tms_app(rds_iam), 권한
│   ├── 002_ref.sql              # ref 표·뷰 v_stack, status_code 고정값
│   ├── 003_obs_ops.sql          # obs 표 3개, ops 표 4개, 인덱스
│   └── 004_app_rag.sql          # D 제안 표(구조만)
├── certs/global-bundle.pem  # RDS 공용 CA (공개 인증서)
├── pyproject.toml
├── README.md
└── tests/
    ├── test_load.py         # 정리·요약·범위 (pandas만)
    ├── test_db.py           # UPSERT 멱등·오래된 행 미변경·null·권한 (PostgreSQL 컨테이너)
    └── test_handler.py      # mode 분기, RDS 주소 입력, 응답 모양

infra/stacks/tms-dashboard-load/     # 새 스택
├── backend.tf  versions.tf  variables.tf  outputs.tf
├── main.tf                  # 레이어(규칙+pg8000), Lambda(VPC), 역할, 로그 그룹(14일)
└── state_machine.tf         # 상태 머신, Scheduler 2개(:15·:45, 03:20), 역할

infra/stacks/tms-network/security_groups.tf   # 보안그룹 tms-loader, DB 5432 ← tms-loader (추가)
infra/stacks/tms-database/main.tf             # iam_database_authentication_enabled = true (수정)
.github/workflows/dashboard-load.yml          # ruff + pytest (PostgreSQL 서비스 컨테이너)
.github/CODEOWNERS                            # /services/dashboard-load/, /infra/stacks/tms-dashboard-load/ (A, D)
AGENTS.md                                     # 저장소 구조에 새 스택·폴더, S3 경로 규칙에 ref/sites/
```

**Structure Decision**: 적재는 서비스 앱(`dashboard-api`)과 권한·배포 주기가 달라 `services/dashboard-load/`와 새 스택으로 둔다. C의 규칙 코드와 008의 범위 함수는 복사하지 않고 레이어로 묶어 import한다(010과 같은 방식). 다른 스택 변경은 A 소유인 `tms-network`(추가만)와 `tms-database`(설정 하나)뿐이다.

## Complexity Tracking

| 항목 | 필요한 이유 | 더 단순한 대안을 버린 이유 |
|---|---|---|
| Lambda 앞에 상태 머신 | RDS 존재 확인과 SNS 발행을 VPC 밖에서 해야 함(R1·R3) | Scheduler → Lambda 직접: RDS가 꺼졌을 때 연결 실패와 진짜 실패를 구분 못 하고 알림을 못 보냄 |
| 외부 패키지 `pg8000` | Lambda에서 PostgreSQL 접속 | 표준 라이브러리에는 드라이버가 없음. 수집 Lambda 규칙(외부 패키지 금지)과 무관 |
| `tms-database`·`tms-network` 수정 | IAM 인증, 적재 전용 보안그룹 | 비밀번호 방식은 엔드포인트나 NAT가 필요(R4). 앱 보안그룹 재사용은 불필요한 ALB 규칙이 따라옴(R6) |
