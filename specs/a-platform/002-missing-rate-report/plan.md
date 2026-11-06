# Implementation Plan: Bronze 슬롯 누락률 일일 리포트

**Branch**: `feat/tms-missing-rate-report` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md) | **Issue**: #5

**Input**: Feature specification from `specs/a-platform/002-missing-rate-report/spec.md` · 사용자 지시: "모듈 확장 버전으로 시작"

## Summary

B의 `missing_rate_lambda.py` 계산 로직을 `services/tms-missing-rate/`로 옮겨 **별도 Lambda**로 배포한다. 매일 09:00 KST에 전날 48슬롯 누락을 계산해 `reports/missing_rate/date=…/report.json`에 저장하고, 누락이 있으면 기존 SNS 토픽으로 **직접 알림 메시지**를 보낸다. 계산 실패는 Lambda `Errors` 알람으로 따로 알린다.

인프라는 001의 `scheduled-collector` 모듈을 **확장해 재사용**한다. 새 변수는 모두 기본값이 현재 동작과 같아서, **수집기(`tms-collector`)의 plan 결과는 "변경 없음"이어야 한다.**

## Technical Context

**Language/Version**: Python 3.13, Terraform `~> 1.15.0`

**Primary Dependencies**: 표준 라이브러리 + boto3(런타임 내장). provider `aws ~> 6.0`, `archive ~> 2.0` (001과 동일, 추가 없음)

**Storage**: 원본 버킷 `smokestack-tms-raw-952900391026` — `tms_cleansys/` 읽기 전용, `reports/missing_rate/` 쓰기

**Testing**: 자동 테스트 없음(001과 동일). `terraform validate`/`plan`, 수동 호출(백필)로 검증 → [quickstart.md](quickstart.md)

**Target Platform**: AWS `ap-northeast-2`, 계정 `952900391026`

**Project Type**: 인프라 스택(IaC) + 서버리스 배치 함수

**Performance Goals**: 하루치 계산이 3분 안에 끝남. 읽는 양: UTC 이틀치 원본 폴더(정상 운영 시 약 96개)의 메타 + 원문

**Constraints**: 원본 경로 쓰기·삭제 금지. 외부 패키지 금지. 원문 내용 로그 금지. 수집기 리소스 변경 금지(plan으로 확인)

**Scale/Scope**: 하루 1회 실행. 백필은 한 번에 7일 이하 권장(시간 제한)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 판정 | 근거 |
|---|---|---|
| I. 수집 연속성 | ✅ 조건부 | 수집기 **모듈 코드**를 수정한다. 새 변수의 기본값이 현재 값과 같아 수집기 리소스는 바뀌지 않아야 하며, **plan에서 `module.collector` 변경 0건을 확인하는 것을 구현 관문으로 둔다**. 스케줄·주기 변경 없음. 원본 경로는 읽기만 한다(FR-012). 모듈 수정 사실은 PR에서 B에게 알린다. |
| II. 비밀값 비공개 | ✅ | API 키 불필요(SSM 권한 없음). 알림 메시지에는 날짜·슬롯·리포트 경로만 넣는다. 이메일은 기존 구독 재사용. |
| III. 코드로, 적용은 사람이 | ✅ | 전부 Terraform. 에이전트는 `plan`까지. 권한은 아래 표, 최소 범위. |
| IV. 데이터 계약 우선 | ✅ | 원본은 [001 계약](../001-tms-collection/contracts/raw-layout.md)대로 읽는다. 새 산출물(리포트)과 수동 호출 입력을 [contracts/](contracts/)에 정의한다. |
| V. 같은 조건의 비교 | 해당 없음 | |
| VI. 설명 가능한 결과 | ✅ | 리포트에 누락 슬롯 목록과 폴더 상태별 수를 남겨, 누락률 숫자를 원본까지 추적할 수 있다. |
| 비용 | ✅ | 아래 표 |
| 외부 패키지 | ✅ | 없음 |

### 부여 권한 (새 역할 `tms-missing-rate-lambda`)

| 권한 | 범위 | 이유 |
|---|---|---|
| `logs:CreateLogStream`, `logs:PutLogEvents` | 로그 그룹 `/aws/lambda/tms-missing-rate` | 모듈 기본 |
| `s3:ListBucket` | 원본 버킷, 조건 `s3:prefix` = `tms_cleansys/*` | 날짜별 회차 폴더 목록 조회 |
| `s3:GetObject` | `…/tms_cleansys/*` | 메타·원문 읽기 (`_state/` 포함, 사용하지 않음) |
| `s3:PutObject` | `…/reports/missing_rate/*` | 리포트 저장. 원본 경로에는 쓰기 권한이 없다 |
| `sns:Publish` | 토픽 `tms-collector-alerts` | 누락 알림 |
| (없음) | SSM, KMS | 모듈 확장으로 API 키 권한을 빼는 경우 |

Scheduler 호출 역할 `tms-missing-rate-scheduler`: `lambda:InvokeFunction` 함수 1개 (모듈 기본).

### 비용 추정 (월)

| 항목 | 사용량 | 예상 |
|---|---|---|
| Lambda | 30회 × 수십 초 × 512MB | 프리 티어 범위 |
| S3 요청 | LIST 약 60회, GET 약 6,000회, PUT 30회 | 0.01달러 미만 |
| S3 저장 | 리포트 30개 × 수 KB | 무시 가능 |
| CloudWatch 알람 1개, 로그 | | 약 0.1달러 |
| Scheduler, SNS | 30회, 알림 시만 | 무료 범위 |

**합계: 월 0.2달러 미만 예상.**

## 설계

### 모듈 확장: `infra/modules/scheduled-collector`

| 새 변수 | 타입 / 기본값 | 수집기 | 누락률 | 동작 |
|---|---|---|---|---|
| `api_key_parameter_name` | `string` / **`null`** (기존 필수 → 선택) | `/tms/collector/api-key` | 생략 | `null`이면 SSM·KMS 문장과 KMS 별칭 조회를 만들지 않는다 |
| `bucket_arn` | `string` / **`null`** (기존 필수 → 선택) | 원본 버킷 | 생략 | `null`이면 기본 S3 문장(`ReadWriteRawObjects`)을 만들지 않는다 |
| `additional_policy_statements` | `list(object({sid, actions, resources, conditions = optional(list(object({test, variable, values})), [])}))` / `[]` | 생략 | 위 권한 표의 S3·SNS 문장 | 실행 역할 정책에 문장 추가 |
| `maximum_retry_attempts` | `number` / `null` | 생략 | `0` | `null`이 아니면 `aws_lambda_function_event_invoke_config` 생성 |
| `alarm_treat_missing_data` | `string` / `"breaching"` | 생략 | `"notBreaching"` | 알람의 값 없음 처리 |
| `alarm_description` | `string` / `null` | 생략 | "계산 실패" | `null`이면 기존 문구 `"${name} 실행 실패 또는 호출 중단"` |

- 기존 문장의 **순서와 sid는 바꾸지 않는다.** 수집기 정책 JSON이 바이트 단위로 같아야 plan이 "변경 없음"이 된다.
- `aws_kms_alias` data와 `parameter_arn` local은 `api_key_parameter_name != null`일 때만 쓴다(`count`).
- 변수 설명 문구를 "수집기"에서 "주기 실행 함수"로 바꾸는 정도는 리소스에 영향이 없다.

### 스택 추가: `infra/stacks/tms-collection/main.tf`

```hcl
module "missing_rate" {
  source     = "../../modules/scheduled-collector"
  name       = "tms-missing-rate"
  source_dir = "${path.module}/../../../services/tms-missing-rate"
  handler    = "handler.lambda_handler"
  runtime    = "python3.13"
  timeout_seconds = 180
  memory_mb       = 512
  environment_variables = {
    BRONZE_BUCKET   = module.raw_archive.bucket_name
    ALERT_TOPIC_ARN = aws_sns_topic.alerts.arn
  }
  additional_policy_statements = [ /* 권한 표 */ ]
  maximum_retry_attempts       = 0
  schedule_expression  = "cron(0 9 * * ? *)"
  schedule_timezone    = "Asia/Seoul"
  schedule_input       = "{}"
  alarm_topic_arn          = aws_sns_topic.alerts.arn
  alarm_period_seconds     = 86400
  alarm_treat_missing_data = "notBreaching"
}
```

출력 추가: `missing_rate_function_name`.

### 코드: `services/tms-missing-rate/handler.py`

B의 `k_tms_pipeline/lambda/missing_rate_lambda.py`(`origin/k-tms-bronze`, 커밋 `124f079`)를 가져와 아래만 바꾼다.

1. **누락 알림을 예외 대신 SNS 직접 발행으로** ([research.md](research.md) R2): 자동 실행에서 누락이 있으면 `sns.publish`로 요약 메시지를 보내고 정상 종료한다. 예외는 진짜 계산 실패에만 남는다.
2. 사소한 정리: `boto3. client` 공백, `count`의 반환 타입(`-> int`), 주석.
3. 계산 로직(슬롯 생성, UTC 이틀 읽기, 최신 `mesure_dt` 판정, 상태 분류)은 **바꾸지 않는다.**

`services/tms-missing-rate/README.md`에 운영 문서를 둔다(001의 `tms-collector/README.md`와 같은 형식).

## Project Structure

### Documentation (this feature)

```text
specs/a-platform/002-missing-rate-report/
├── spec.md
├── plan.md                  # 이 파일
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── report.schema.json   # 일일 리포트 (D·B가 읽을 수 있음)
│   ├── invoke-event.md      # 자동·수동 호출 입력
│   └── alert-message.md     # 누락 알림 메시지 형식
├── checklists/requirements.md
└── tasks.md                 # /speckit-tasks
```

### Source Code (repository root)

```text
infra/
├── modules/scheduled-collector/
│   ├── main.tf          # 수정: 조건부 SSM·S3 문장, 추가 문장, event invoke config, 알람 변수
│   ├── variables.tf     # 수정: 새 변수 4개, 기존 2개 선택화
│   └── outputs.tf       # (필요 시) function_arn
└── stacks/tms-collection/
    ├── main.tf          # 수정: module "missing_rate" 추가
    └── outputs.tf       # 수정: missing_rate_function_name
services/
└── tms-missing-rate/    # 신규
    ├── handler.py
    └── README.md
```

**Structure Decision**: 같은 스택(`tms-collection`)에 둔다. 원본 버킷과 SNS 토픽을 공유하고, 수집과 같은 업무 단위(원본 품질)이기 때문이다. 별도 스택으로 나누면 버킷·토픽을 `terraform_remote_state`나 이름 하드코딩으로 넘겨야 한다.

## 요구사항 추적

| FR | 구현 |
|---|---|
| FR-001~004 계산 | `handler.py` `expected_slots`, `kst_day_range_utc`, `list_run_prefixes`, `summarize_run`, `build_report` (B 로직 유지) |
| FR-005, 006 리포트 | `handler.py` `save_report` → [contracts/report.schema.json](contracts/report.schema.json) |
| FR-007 요약 로그 | `handler.py` `print(json.dumps(요약))` |
| FR-008 09:00 실행 | 스택 `schedule_expression`, `schedule_timezone` |
| FR-009 누락 알림 | `handler.py` SNS 발행 + `ALERT_TOPIC_ARN` + `sns:Publish` |
| FR-010 수동 백필 | `handler.py` `target_days` (`from`/`to`) → [contracts/invoke-event.md](contracts/invoke-event.md) |
| FR-011 반복 방지 | `maximum_retry_attempts = 0`, 누락은 예외가 아니므로 재실행 대상 아님 |
| FR-012 원본 읽기 전용 | 권한 표: `PutObject`는 `reports/missing_rate/*`만 |
| FR-013 권한 분리 | 별도 역할, `api_key_parameter_name` 생략 |

## Complexity Tracking

| 위반·예외 | 필요한 이유 | 더 단순한 대안을 택하지 않은 이유 |
|---|---|---|
| 수집기 모듈 코드 수정 (원칙 I 주의 대상) | 두 함수가 같은 틀을 쓰되 권한·알람이 달라야 한다 | 리소스를 따로 작성하면 약 150줄 중복. 수집기 영향은 plan "변경 없음"으로 검증 가능하다 |
| B 로직 일부 변경 (예외 → SNS 발행) | 누락 알림과 계산 실패를 구분하라는 spec 요구(Edge Cases), 하루 1회 함수의 Errors 알람 의미 정리 | 예외 방식을 유지하면 메일에 누락 내용이 없고 실패와 구분되지 않는다 |
