---
description: "002 Bronze 슬롯 누락률 일일 리포트 작업 목록"
---

# Tasks: Bronze 슬롯 누락률 일일 리포트

**Input**: `specs/a-platform/002-missing-rate-report/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: spec에서 자동 테스트를 요구하지 않았다. 검증은 `terraform plan` 관문과 [quickstart.md](quickstart.md)의 수동 시나리오로 한다.

**Organization**: 사용자 스토리별 단계. 모든 스토리가 같은 핸들러 파일 하나를 공유하므로 병렬 가능한 작업은 적다.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 다른 파일이고 선행 작업이 없어 병렬 가능
- **[Story]**: US1(누락 알림), US2(날짜별 기록), US3(백필)
- 🧑 표시는 **사람이 하는 작업**(apply, AWS 확인). 에이전트는 실행하지 않는다.

## 경로

- 모듈: `infra/modules/scheduled-collector/`
- 스택: `infra/stacks/tms-collection/`
- 코드: `services/tms-missing-rate/`

---

## Phase 1: Setup

**Purpose**: B의 계산 로직을 저장소로 가져온다.

- [X] T001 `origin/k-tms-bronze`의 `k_tms_pipeline/lambda/missing_rate_lambda.py`(커밋 `124f079`)를 내용 변경 없이 `services/tms-missing-rate/handler.py`로 가져온다 (`git show origin/k-tms-bronze:k_tms_pipeline/lambda/missing_rate_lambda.py`). 출처를 파일 첫 주석에 남긴다.

---

## Phase 2: Foundational — 모듈 확장 (모든 스토리의 전제)

**Purpose**: `scheduled-collector`가 두 번째 함수를 만들 수 있게 한다. **기본값 = 현재 동작**이어야 한다.

**⚠️ CRITICAL**: T006 관문을 통과하기 전에는 Phase 3로 넘어가지 않는다.

- [X] T002 `infra/modules/scheduled-collector/variables.tf`: `api_key_parameter_name`과 `bucket_arn`에 `default = null`을 주고 설명에 "null이면 해당 권한을 만들지 않는다"를 적는다. 새 변수를 추가한다.
  - `additional_policy_statements`: `list(object({ sid = string, actions = list(string), resources = list(string), conditions = optional(list(object({ test = string, variable = string, values = list(string) })), []) }))`, 기본 `[]`
  - `maximum_retry_attempts`: `number`, 기본 `null`, `validation`: `null` 또는 0–2
  - `alarm_treat_missing_data`: `string`, 기본 `"breaching"`, `validation`: `breaching`·`notBreaching`·`ignore`·`missing` 중 하나
  - `alarm_description`: `string`, 기본 `null`
  - 모든 변수에 `description`과 `type`을 단다 (AGENTS.md)
- [X] T003 `infra/modules/scheduled-collector/main.tf` 권한부:
  - `data "aws_kms_alias" "ssm"`에 `count = var.api_key_parameter_name == null ? 0 : 1`
  - `local.parameter_arn`을 `api_key_parameter_name`이 `null`이면 `null`로
  - `data "aws_iam_policy_document" "lambda"`의 문장 **순서와 sid를 유지**한다: `WriteLogs` → `ReadWriteRawObjects`(`bucket_arn != null`일 때만, `dynamic`) → `ReadApiKey`·`DecryptApiKey`(`api_key_parameter_name != null`일 때만, `dynamic`) → `additional_policy_statements`(`dynamic`, `condition` 블록도 `dynamic`)
- [X] T004 `infra/modules/scheduled-collector/main.tf`: `aws_lambda_function_event_invoke_config` 리소스를 `count = var.maximum_retry_attempts == null ? 0 : 1`로 추가한다 (`function_name = aws_lambda_function.this.function_name`).
- [X] T005 `infra/modules/scheduled-collector/main.tf` 알람: `treat_missing_data = var.alarm_treat_missing_data`, `alarm_description = coalesce(var.alarm_description, "${var.name} 실행 실패 또는 호출 중단")`. 기존 주석은 "breaching일 때"로 보완한다.
- [X] T006 **관문 (원칙 I)**: `infra/`에서 `terraform fmt -recursive`, `infra/stacks/tms-collection`에서 `terraform validate`와 `terraform plan`을 실행해 **변경 0건(`No changes.`)**인지 확인한다. 변경이 있으면 원인을 고칠 때까지 다음 단계로 가지 않는다. `TF_VAR_alert_email`은 사용자 환경 변수로 받는다(값을 파일에 쓰지 않는다).

**Checkpoint**: 모듈은 확장됐고 수집기는 그대로다.

---

## Phase 3: User Story 1 — 매일 아침 전날 누락을 알림으로 받는다 (P1) 🎯 MVP

**Goal**: 매일 09:00 KST에 전날을 계산하고, 누락이 있으면 [alert-message.md](contracts/alert-message.md) 형식 메일을 보낸다.

**Independent Test**: quickstart V5·V6 — 자동 실행 후 리포트와 로그가 있고, 누락이 있는 날은 메일이 온다.

- [X] T007 [US1] `services/tms-missing-rate/handler.py` 정리: `boto3. client` → `boto3.client`, 내부 함수 `count`의 반환 타입 `-> list` → `-> int`, 한국어 주석 정리. **계산 함수(`expected_slots`, `kst_day_range_utc`, `run_ts_of`, `list_run_prefixes`, `get_bytes`, `summarize_run`, `build_report`)의 동작은 바꾸지 않는다.**
- [X] T008 [US1] `services/tms-missing-rate/handler.py` 알림: 환경 변수 `ALERT_TOPIC_ARN`을 읽고 `sns = boto3.client("sns")`를 핸들러 밖에 둔다. `build_alert(result, report) -> tuple[str, str]`을 추가해 제목 `"[TMS] {date} 슬롯 누락 {n}개"`(100자 이내)와 본문(대상 날짜, `n / 48 (x.x%)`, 슬롯 목록 전부, 상태별 폴더 수, 리포트 S3 경로)을 만든다. 원문 측정값·키·이메일은 넣지 않는다.
- [X] T009 [US1] `services/tms-missing-rate/handler.py` `lambda_handler`: 자동 실행(`from` 없음)에서 `missing_slots > 0`인 날짜마다 `sns.publish(TopicArn=…, Subject=…, Message=…)`를 호출하고 결과에 `alerted: true`를 넣는다. 기존 `raise RuntimeError("슬롯 누락 발생")`는 **제거**한다(research R2). 그 밖의 예외는 그대로 전파해 `Errors` 알람이 잡게 한다.
- [X] T010 [US1] `infra/stacks/tms-collection/main.tf`: `module "missing_rate"`를 plan.md "스택 추가"대로 추가한다.
  - `name = "tms-missing-rate"`, `source_dir = "${path.module}/../../../services/tms-missing-rate"`, `handler = "handler.lambda_handler"`, `runtime = "python3.13"`, `timeout_seconds = 180`, `memory_mb = 512`
  - `environment_variables = { BRONZE_BUCKET = module.raw_archive.bucket_name, ALERT_TOPIC_ARN = aws_sns_topic.alerts.arn }`
  - `additional_policy_statements` 4개(sid `ListRawPrefix`, `ReadRawObjects`, `WriteMissingRateReports`, `PublishAlerts`): `s3:ListBucket`은 `module.raw_archive.bucket_arn` + 조건 `StringLike s3:prefix ["tms_cleansys/*"]`, `s3:GetObject`는 `${bucket_arn}/tms_cleansys/*`, `s3:PutObject`는 `${bucket_arn}/reports/missing_rate/*`, `sns:Publish`는 `aws_sns_topic.alerts.arn`
  - `maximum_retry_attempts = 0`, `schedule_expression = "cron(0 9 * * ? *)"`, `schedule_timezone = "Asia/Seoul"`, `schedule_input = "{}"`
  - `alarm_topic_arn = aws_sns_topic.alerts.arn`, `alarm_period_seconds = 86400`, `alarm_treat_missing_data = "notBreaching"`, `alarm_description = "tms-missing-rate 계산 실패"`
  - 각 설정 위에 이유를 한 줄 주석으로 남긴다(001 스택 주석 형식)
- [X] T011 [P] [US1] `infra/stacks/tms-collection/outputs.tf`: `missing_rate_function_name` 출력 추가(`module.missing_rate.function_name`).
- [X] T012 [US1] `terraform fmt -recursive`, `validate`, `plan`: **`module.collector` 변경 0건**, `module.missing_rate`만 추가(Lambda 1, IAM 역할 2, 역할 정책 2, 로그 그룹 1, 스케줄 1, 알람 1, event invoke config 1)인지 확인하고 요약을 사용자에게 보여준다.
- [ ] T013 [US1] 🧑 사용자가 `terraform apply`를 실행한다.

**Checkpoint**: 다음 날 09:00부터 자동 실행과 누락 알림이 동작한다.

---

## Phase 4: User Story 2 — 날짜별 누락률 기록이 남는다 (P1)

**Goal**: 날짜마다 [report.schema.json](contracts/report.schema.json)을 만족하는 리포트가 남는다.

**Independent Test**: quickstart V2 — 리포트 하나가 스키마의 필드를 모두 가진다.

- [X] T014 [US2] `services/tms-missing-rate/handler.py` `build_report`가 스키마와 맞는지 확인한다: `slots.expected == 48`, `slots.missing`이 **시간 순**(`expected_slots` 순서), `inspect_fail`·`meta_missing`·`raw_missing`이 **대상 하루 폴더**(`in_day`) 기준. 다르면 맞춘다. 리포트 키는 `reports/missing_rate/date={KST 날짜}/report.json`.
- [ ] T015 [US2] 🧑 quickstart V2·V4 확인.

---

## Phase 5: User Story 3 — 지난 날짜를 다시 계산한다 (P2)

**Goal**: `{"from","to"}` 수동 호출로 기간 리포트를 만들고 알림은 보내지 않는다.

**Independent Test**: quickstart V1 — 백필 호출 후 날짜별 리포트가 생기고 메일이 없다.

- [X] T016 [US3] `services/tms-missing-rate/handler.py` `target_days`가 [invoke-event.md](contracts/invoke-event.md)와 맞는지 확인한다: `to` 생략 시 `from` 하루, `from > to`이면 빈 목록, 수동 실행은 `alerted`를 넣지 않고 SNS를 호출하지 않는다.
- [ ] T017 [US3] 🧑 001 배포일부터 어제까지 7일 이하 단위로 백필 호출 (quickstart V1, V3).

---

## Phase 6: Polish & Cross-Cutting

- [X] T018 [P] `services/tms-missing-rate/README.md` 작성: 구성도, 설정 표(런타임, 메모리 512MB, 시간 제한 180초, 스케줄, 환경 변수), 처리 흐름, 알림 두 종류(누락 메일 / 계산 실패 알람), 권한, 수동 백필 명령, 운영 확인. 형식은 `services/tms-collector/README.md`를 따른다.
- [X] T019 [P] `AGENTS.md` "저장소 구조"에 `services/tms-missing-rate/` 한 줄 추가, `scheduled-collector` 설명을 "주기 실행 함수"로 일반화.
- [X] T020 [P] `.github/CODEOWNERS`에 `/services/tms-missing-rate/  @SungChul23 @olchangiagi` 추가.
- [ ] T021 `specs/a-platform/002-missing-rate-report/spec.md` Status를 `Implemented`로 바꾸고, 이 파일의 완료 작업을 `[x]`로 표시.
- [ ] T022 🧑 quickstart V5–V8 확인 후 PR. PR 본문에 "수집기 모듈을 수정했으나 plan 변경 0건"과 B 로직에서 바꾼 점(예외 → SNS 발행)을 적고 B에게 리뷰 요청.

---

## Dependencies

```text
T001 ─┐
T002 → T003 → T004 → T005 → T006(관문) ─┬→ T007 → T008 → T009 ─┐
                                        │                      ├→ T010 → T012 → T013🧑
                                        │                T011 ─┘
                                        └→ T014 (T009 이후 같은 파일)
T016 (T009 이후 같은 파일)
T013 → T015🧑, T017🧑
T018, T019, T020 [P] 언제든 / T021 → T022🧑
```

- US2·US3는 코드상 US1과 같은 핸들러를 공유하므로 **같은 배포**로 나간다. 스토리별 확인만 따로 한다.
- 수집기에 영향이 갈 수 있는 작업은 T002–T005뿐이며, T006·T012 두 번의 관문으로 막는다.

## Parallel Opportunities

- T001 ∥ T002 (다른 파일)
- T011 ∥ T007–T009 (출력 파일 vs 핸들러)
- T018 ∥ T019 ∥ T020 (문서·설정 파일)

## Implementation Strategy

1. **MVP = Phase 1–3** (T001–T013): 모듈 확장, 알림까지 배포. 이것만으로 매일 리포트와 누락 메일이 동작한다.
2. Phase 4–5는 코드 확인 위주라 MVP와 같은 PR에 넣는다.
3. Phase 6 문서 정리 후 PR.

### 커밋 단위 (제안)

| 커밋 | 작업 |
|---|---|
| `docs: 002 누락률 리포트 spec·plan·tasks` | specs/ |
| `feat: scheduled-collector 모듈에 선택 권한·재시도·알람 변수 추가` | T002–T005 |
| `feat: 누락률 리포트 Lambda 코드 추가` | T001, T007–T009, T014, T016 |
| `feat: tms-collection 스택에 누락률 Lambda 연결` | T010–T011 |
| `docs: 누락률 Lambda 운영 문서와 저장소 구조 갱신` | T018–T021 |
