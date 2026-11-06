# Implementation Plan: TMS 원본 수집 인프라

**Branch**: `infra/tms-collection-terraform` | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md) | **Issue**: #4

**Input**: Feature specification from `specs/a-platform/001-tms-collection/spec.md`

> **사후 문서화 plan.** 구현은 이미 이 브랜치에 있다. 이 문서는 "어떻게 만들었고 왜 그렇게 했는지"를 기록하고, spec의 요구사항(FR)이 어느 코드에 대응되는지 추적한다.

## Summary

CleanSYS 공개 API를 10분마다 호출하는 Lambda를 EventBridge Scheduler로 실행하고, 응답 SHA-256이 바뀔 때만 gzip 원문과 메타를 S3 원본 버킷에 추가 저장한다. 매 실행 `_state/latest.json`의 `last_checked_at`을 갱신해 "갱신 없음"과 "수집 중단"을 구분한다. 실패나 호출 중단은 CloudWatch `Errors` 알람(값 없음 = 경보)으로 SNS 이메일을 보낸다. 모든 리소스는 Terraform(공유 S3 backend, 잠금 파일)으로 정의하고, 적용은 사람이 한다.

## Technical Context

**Language/Version**: Python 3.13 (Lambda 런타임 `python3.13`), Terraform `~> 1.15.0` (`.terraform-version` 1.15.8)

**Primary Dependencies**: 표준 라이브러리(`urllib`, `gzip`, `hashlib`, `json`) + boto3(런타임 내장). Terraform provider `hashicorp/aws ~> 6.0`, `hashicorp/archive ~> 2.0`

**Storage**: S3 `smokestack-tms-raw-952900391026` (원본, 버전 관리, SSE-S3), S3 `smokestack-tfstate-952900391026` (Terraform 상태, `use_lockfile`)

**Testing**: 자동 테스트 없음. 검증은 `terraform validate`/`plan`과 배포 후 운영 확인([quickstart.md](quickstart.md))으로 한다.

**Target Platform**: AWS `ap-northeast-2`, 계정 `952900391026`

**Project Type**: 인프라 스택(IaC) + 서버리스 수집 함수

**Performance Goals**: 회차당 1회 호출이 10분 안에 끝남. 실제 소요는 API 응답 시간에 좌우되며, 재시도 포함 최악 약 3×60초 + 대기 7초.

**Constraints**: 외부 패키지 금지. 응답 본문·키는 로그 금지. `reserved_concurrent_executions` 미설정(계정 동시 실행 한도 10). 원본 삭제·만료 규칙 금지.

**Scale/Scope**: 하루 144회 호출, 응답 약 3,400건(사업장·배출구 단위). 원문 저장은 하루 약 48회(30분 갱신 기준).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 판정 | 근거 |
|---|---|---|
| I. 수집 연속성 | ✅ | 스케줄을 **새로 만드는** 변경이다. 끄거나 주기를 바꾸지 않는다. 원본은 추가만 하고(FR-004), 버킷은 `prevent_destroy` + 버전 관리 + 수명 주기 규칙 없음(FR-007). 매 실행 `last_checked_at` 기록(FR-008). B 확인: 수집 방식은 B의 `k-tms-bronze` 브랜치 Lambda와 동일한 로직이다. |
| II. 비밀값 비공개 | ✅ | API 키는 SSM SecureString에 콘솔로 등록, Terraform은 이름(`/tms/collector/api-key`)만 참조. `aws_ssm_parameter` 미사용. 알림 이메일은 `TF_VAR_alert_email` + `sensitive = true`. URL에 키가 들어가므로 예외 메시지에 유형만 기록. |
| III. 코드로 만들고 적용은 사람이 | ✅ | 전 리소스 Terraform. 콘솔 복제본은 개인 계정 검증용이었음. 에이전트는 `plan`까지. 최소 권한은 아래 권한 표 참조. |
| IV. 데이터 계약 우선 | ⚠️ 조건부 | 원본 경로·메타·상태 파일 형식을 [contracts/](contracts/)에 정의했다. Silver가 읽는 계약이므로 **C의 리뷰가 필요**하다(PR 리뷰어로 지정). |
| V. 같은 조건의 비교 | 해당 없음 | 모델·규칙 비교 기능 아님 |
| VI. 설명 가능한 결과 | ✅ | 메타 파일에 요청 시각·시도 횟수·해시·점검 결과를 남겨 원본마다 출처를 추적할 수 있다. |
| 운영 제약: 비용 | ✅ | 아래 비용 추정 참조 |
| 운영 제약: 외부 패키지 | ✅ | 없음 |

### 부여 권한과 이유

| 주체 | 권한 | 범위 | 이유 |
|---|---|---|---|
| Lambda 실행 역할 `tms-collector-lambda` | `logs:CreateLogStream`, `logs:PutLogEvents` | 로그 그룹 `/aws/lambda/tms-collector` | 실행 요약 기록. 로그 그룹은 Terraform이 만들므로 `CreateLogGroup` 불필요 |
| | `s3:GetObject`, `s3:PutObject` | 원본 버킷 `/*` | 상태 파일 읽기, 원문·메타·상태 쓰기 |
| | `ssm:GetParameter` | 파라미터 1개 | API 키 읽기 |
| | `kms:Decrypt` | `alias/aws/ssm`의 키 ARN | SecureString 복호화 |
| Scheduler 역할 `tms-collector-scheduler` | `lambda:InvokeFunction` | 수집 함수 1개 | 스케줄 호출. 신뢰 정책에 `aws:SourceAccount` 조건 |

`s3:ListBucket`은 일부러 주지 않았다. 그래서 상태 파일이 없을 때 S3가 `AccessDenied`를 반환하며, 코드는 이를 첫 실행으로 처리한다([research.md](research.md) R5).

### 비용 추정 (월)

| 항목 | 사용량 | 예상 |
|---|---|---|
| Lambda | 약 4,320회 × 수 초 × 256MB | 프리 티어 범위 |
| EventBridge Scheduler | 약 4,320회 | 프리 티어 범위 |
| S3 저장 | 원문 하루 약 48개 (크기 실측 필요) | 월 1달러 미만 예상 |
| S3 요청 | PUT 월 약 1만 회, GET 약 4,300회 | 0.1달러 미만 |
| CloudWatch 알람 1개, 로그 14일 | | 약 0.1달러 + 소량 |
| SNS 이메일 | 경보 시에만 | 무료 범위 |

**합계: 월 1–2달러 미만 예상.** 원문 크기는 첫 주 운영 후 메타의 `gz_bytes`로 실측해 갱신한다.

## Project Structure

### Documentation (this feature)

```text
specs/a-platform/001-tms-collection/
├── spec.md              # 무엇을·왜
├── plan.md              # 이 파일
├── research.md          # 설계 결정과 대안
├── data-model.md        # 스냅샷·메타·상태 파일 구조
├── quickstart.md        # 배포·운영 확인 절차
├── contracts/
│   ├── raw-layout.md    # 원본 경로 계약 (Silver·002가 읽음)
│   ├── snapshot-meta.schema.json
│   └── state.schema.json
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks 출력 (사후 문서화: 완료 표시)
```

### Source Code (repository root)

```text
infra/
├── bootstrap/                    # Terraform 상태 버킷 (로컬 상태, 최초 1회)
│   └── main.tf
├── modules/
│   ├── raw-archive/              # 원본 보존 버킷: 버전 관리·암호화·공개 차단·prevent_destroy
│   └── scheduled-collector/      # Lambda + 실행 역할 + 로그 그룹 + Scheduler + 호출 역할 + Errors 알람
└── stacks/
    └── tms-collection/           # raw-archive + scheduled-collector + SNS 토픽·이메일 구독
        ├── backend.tf            # S3 backend 하드코딩
        ├── versions.tf           # provider + default_tags
        ├── main.tf
        ├── variables.tf          # alert_email(sensitive), api_key_parameter_name
        └── outputs.tf
services/
└── tms-collector/
    ├── handler.py                # 수집 Lambda
    └── README.md                 # 운영 문서
```

**Structure Decision**: 스택 = 독립 apply 단위(`tms-collection`), 모듈 = 재사용 역할 단위(`raw-archive`, `scheduled-collector`). `scheduled-collector`는 002 누락률 리포트 Lambda에서 재사용할 것을 염두에 두고 분리했다. 폴더 이름은 기술명이 아닌 하는 일 기준이다(AGENTS.md).

## 요구사항 추적

| FR | 구현 위치 |
|---|---|
| FR-001 10분 주기, 유연 창 OFF | `scheduled-collector/main.tf` `aws_scheduler_schedule` + 스택의 `cron(0/10 * * * ? *)`, `Asia/Seoul` |
| FR-002 재시도 3회 | `handler.py` `fetch_snapshot` (`RETRY_STATUS`, `BACKOFF_SECONDS`) |
| FR-003 예정 시각 기준 경로 | 스택 `schedule_input` `<aws.scheduler.scheduled-time>` + `handler.py` `resolve_run_ts` |
| FR-004 변경 시에만 원문 저장 | `handler.py` `lambda_handler` 해시 비교, `gzip.compress(..., mtime=0)` |
| FR-005 메타 | `handler.py` `build_meta` |
| FR-006 경로 | `handler.py` `build_prefix` → [contracts/raw-layout.md](contracts/raw-layout.md) |
| FR-007 원본 보호 | `raw-archive/main.tf` |
| FR-008 상태 파일 | `handler.py` `save_state` (변경 없음 분기 포함) |
| FR-009 응답 점검 | `handler.py` `inspect_payload`, 실패 시 `RuntimeError` |
| FR-010 상태는 마지막에 | `handler.py` `lambda_handler` 순서 |
| FR-011 경보 | `scheduled-collector/main.tf` `aws_cloudwatch_metric_alarm` (`treat_missing_data = "breaching"`, 900초) + 스택 SNS |
| FR-012 요약 로그 14일 | `handler.py` `print(json.dumps(요약))`, 로그 그룹 `retention_in_days = 14` |
| FR-013 비밀값 | 스택 `variables.tf`, `handler.py` `get_api_key` |
| FR-014 최소 권한 | 위 권한 표 |
| FR-015 재현성 | `backend.tf`, `.terraform.lock.hcl`, `bootstrap/` |

## Complexity Tracking

| 위반·예외 | 필요한 이유 | 더 단순한 대안을 택하지 않은 이유 |
|---|---|---|
| 동시 실행 1 미고정 (AGENTS.md는 한도 상향 후 1로 설정을 요구) | 계정 동시 실행 한도가 10이면 예약 동시 실행을 설정할 수 없다 | 한도 상향 요청 후 `reserved_concurrent_executions = 1` 추가. 그때까지 실행이 겹쳐도 스냅샷이 한 번 더 저장될 뿐 원본은 사라지지 않는다 |
| DLQ 없음 | 재시도까지 실패한 회차는 다시 받을 수 없어, DLQ에 이벤트를 남겨도 복구할 데이터가 없다 | 알람으로 즉시 알고, 하루 단위 누락은 002에서 집계한다 |
