# Tasks: 서비스 로그 수집·분석 (CloudWatch → Firehose → OpenSearch)

**Input**: `specs/a-platform/014-log-opensearch/` (spec, plan, research R1~R10, data-model, contracts/log-format.md, quickstart)

**표시**: [P] 다른 파일이라 같이 해도 됨 · [US1]~[US3] spec의 사용자 스토리 · 🧑 사람(A)이 AWS에서 · 📨 다른 담당과 공유

테스트는 라우터 Lambda(입력 모양이 여러 가지)와 서버 미들웨어(개인 정보 제외)에 둔다.

## Phase 1: Setup

- [X] T001 `services/log-search/` 뼈대: `pyproject.toml`(Python 3.12, 의존 없음, 개발 `pytest`·`ruff`), `README.md`(무엇을, 명령, 수동 단계), `tests/`.
- [X] T002 [P] `.github/workflows/log-search.yml`: `services/log-search/**` 변경 시 ruff·pytest.
- [X] T003 [P] `.github/CODEOWNERS`: `/services/log-search/ @SungChul23`, `/infra/stacks/tms-log-search/ @SungChul23`.
- [X] T004 `infra/stacks/tms-log-search/`: `backend.tf`(키 `stacks/tms-log-search/terraform.tfstate`), `versions.tf`(`~> 1.15.0`, aws `~> 6.0`, archive, `default_tags` stack=`tms-log-search`), `variables.tf`(`opensearch_enabled` 기본 true, `engine_version` 기본 `OpenSearch_2.19`, `instance_type` 기본 `t3.small.search`, `volume_gb` 10, `log_groups_app`·`log_groups_pipeline` 목록, `glue_log_group`, `state_machines` 목록), `outputs.tf`(도메인 주소·Dashboards 주소).

## Phase 2: Foundational (도메인·로그인·전달 기반)

- [X] T005 `infra/stacks/tms-log-search/domain.tf`: 도메인 `tms-logs`(t3.small.search ×1, gp3 10GB, 1-AZ, 공개, HTTPS 강제 TLS 1.2, 저장·노드 간 암호화, FGAC 켬·내부 DB 끔·마스터 = `tms-logs-admin` 역할), 접근 정책(Firehose 역할·뷰어 역할·관리자 역할·SNS 역할만), `count = var.opensearch_enabled ? 1 : 0` (research R1).
- [X] T006 `domain.tf`: Cognito 연결 — 자격 증명 풀 `tms-logs`(사용자 풀 `tms-users`, 클라이언트는 OpenSearch가 만듦), 역할 `tms-logs-viewer`(인증·`members`), `tms-logs-noaccess`(그 밖), 역할 규칙(`cognito:groups` Contains `members`), 서비스 역할(`AmazonOpenSearchServiceCognitoAccess`), 도메인 `cognito_options` (R2). 사용자 풀 ID는 SSM `/tms/app/config/cognito-user-pool-id`에서.
- [X] T007 [P] `domain.tf`: SNS 발행 역할 `tms-logs-sns`(`tms-collector-alerts`). 관리자 역할은 두지 않고 도메인 마스터 = apply한 IAM 사용자로 바꿈.
- [X] T008 `infra/stacks/tms-log-search/delivery.tf`: 실패분 버킷 `smokestack-tms-logs-952900391026`(공개 차단, 암호화, 수명 주기 28일), Firehose 역할 `tms-logs-firehose`(도메인 `es:ESHttp*`·`DescribeDomain*`, 버킷 쓰기), 라우터 역할 `tms-logs-router`(Firehose 3개 `PutRecordBatch`, 기본 로그) (R3).

## Phase 3: US1 - 로그를 한곳에서 검색 (P1) 🎯

**목표**: 대상 로그가 5분 안에 검색된다. **독립 확인**: quickstart §6 시나리오 1·2·5.

- [X] T009 [P] [US1] `services/log-search/tests/test_router.py`: CloudWatch 구독 이벤트(`awslogs.data` gzip+base64) → 줄마다 문서(`@timestamp`·`log_group`·`service`·`message`), JSON 줄은 `json.*`로 펼침, 수준 추정(JSON `level`, `[ERROR]`, `Traceback`, `Task timed out`, 상태 코드 ≥500), 서버 그룹의 `log_type=activity`는 activity 스트림·나머지는 app, Lambda·Glue는 pipeline, 제어 메시지 버림, EventBridge 상태 머신 이벤트 → pipeline 문서(실패면 `ERROR`), `PutRecordBatch` 500건 단위·부분 실패 재전송·끝내 실패면 예외 (가짜 Firehose).
- [X] T010 [US1] `services/log-search/router.py`: 라우터 Lambda(표준 라이브러리 + boto3). 입력 두 종류(CloudWatch 구독, EventBridge)를 문서로 바꿔 Firehose 3개로 `PutRecordBatch` (research R3·R9). Firehose 이름은 환경 변수.
- [X] T011 [US1] `delivery.tf`: 라우터 Lambda(+로그 그룹 14일, 자기 로그는 구독하지 않음), Firehose 3개(Direct PUT, 변환 없음: `tms-logs-app`→`logs-app`, `tms-logs-pipeline`→`logs-pipeline`, `tms-logs-activity`→`activity`, 하루 회전, 버퍼 60초·1MB, 실패분 S3).
- [X] T012 [US1] `delivery.tf`: 구독 필터(대상 = 라우터 Lambda, `aws_lambda_permission` logs.amazonaws.com) — 서버 그룹 2개·Lambda 그룹 6개(패턴 없음), Glue `/aws-glue/tms-silver`(`?ERROR ?Exception ?Traceback`) (R3·R9).
- [X] T013 [US1] `delivery.tf`: EventBridge 규칙(Step Functions 실행 상태 변경, 상태 머신 2개, SUCCEEDED·FAILED·TIMED_OUT·ABORTED) → 라우터 Lambda(+ `aws_lambda_permission` events.amazonaws.com) (R9).
- [X] T014 [P] [US1] `services/log-search/opensearch/`: 인덱스 템플릿 3개(`logs-app-*`, `logs-pipeline-*`, `activity-*`: 샤드 1·복제 0, 공통 필드 매핑, `json` 동적, 문자열 keyword), ISM `logs-14d`·`activity-28d` (data-model).
- [X] T015 [US1] `services/log-search/setup_opensearch.py`: SigV4(botocore) + urllib, 멱등 PUT, `--dry-run`: 템플릿·ISM·역할(`firehose_writer`)·역할 매핑(관리자·Firehose·뷰어) 적용 (R5).
- [X] T016 [P] [US1] `services/log-search/tests/test_setup.py`: dry-run이 적용 목록을 순서대로 출력, 정의 파일 JSON이 유효, 역할 매핑에 실제 역할 이름.

## Phase 4: US1 보강 - 서버 요청 기록 (P1)

- [X] T017 [P] [US1] `services/dashboard-api/tests/test_logging.py`: 요청 미들웨어가 JSON 한 줄(`log_type=request`, method·path·status·duration_ms·sub), 상태 확인 경로 제외, 500 이상 `ERROR`·400대 `WARNING`, 쿼리 문자열·본문 없음.
- [X] T018 [US1] `services/dashboard-api/app/logging_mw.py`(+ `services/dashboard-agent/app/logging_mw.py` 같은 내용): 미들웨어, `log_activity(event, sub, **extra)`. 두 앱 `main.py`에 등록, Dockerfile `--no-access-log` (contracts/log-format.md).
- [X] T019 [P] [US1] `services/dashboard-agent/tests/test_logging.py`: T017과 같은 시험.

## Phase 5: US2 - 운영 대시보드·알림 (P1)

- [X] T020 [P] [US2] (인덱스 패턴·저장된 검색까지. 그래프·대시보드는 데이터가 들어온 뒤 Dashboards에서 만들고 내보내 커밋) `services/log-search/dashboards/ops.ndjson`: 인덱스 패턴 3개, `운영 상태`(서비스별 로그 수, 시간대별 오류 수, 최근 오류 표, 요청 상태 코드·응답 시간, 상태 머신 실행 결과 표).
- [X] T021 [P] [US2] `services/log-search/opensearch/monitors/errors-burst.json` + 알림 채널(SNS, 역할 `tms-logs-sns`): `logs-app-*`·`logs-pipeline-*` 최근 5분 `level:ERROR` ≥ 10 (R6).
- [X] T022 [US2] `setup_opensearch.py`: 알림 채널·모니터·저장 객체 가져오기(`_dashboards/api/saved_objects/_import?overwrite=true`).

## Phase 6: US3 - 사용 현황 (P2)

- [X] T023 [US3] `services/dashboard-api/app/main.py`: `/api/me` → `session`, `/api/invite` → `invite_ok`·`invite_fail`·`invite_limited` (R10). 시험 추가.
- [X] T024 [US3] `services/dashboard-api/app/dashboard.py`: 즐겨찾기 PUT·DELETE → `favorite_add`·`favorite_remove`(`target`). 시험 추가. 📨 D에게 공유(D 소유 파일).
- [X] T025 [P] [US3] (인덱스 패턴·저장된 검색까지, 그래프는 T020과 같이) `services/log-search/dashboards/usage.ndjson`: `사용 현황`(하루 접속자, 초대 코드 통과·실패·차단, 즐겨찾기 상위, 에이전트 질문 수).
- [X] T026 [P] [US3] 시험: 활동 기록에 이메일·이름·초대 코드 입력값이 없음(caplog).

## Phase 7: 적용·확인 (사람)

- [ ] T027 🧑 `tms-log-search` plan·apply(도메인 15~30분).
- [ ] T028 🧑 OpenSearch가 만든 Cognito 앱 클라이언트에 Google 추가(quickstart §4).
- [ ] T029 🧑 `setup_opensearch.py --dry-run` → 실행.
- [ ] T030 🧑 서버 앱 배포(T018·T023·T024가 main에 머지되면 CI).
- [ ] T031 🧑 quickstart §6 시나리오 1~8 + 상태 머신 실행 결과가 `logs-pipeline-*`에 들어오는지.
- [ ] T032 🧑 비용 확인: 하루 뒤 Cost Explorer에서 OpenSearch·Firehose 금액.

## Phase 8: Polish

- [X] T033 [P] `AGENTS.md`: 저장소 구조(`tms-log-search`, `services/log-search`), 로그 버킷(수명 주기 28일, 원본 버킷과 별개).
- [ ] T034 [P] 📨 D 공유: `contracts/log-format.md`(요청·활동 기록, `agent_question`), Dashboards 주소·로그인.
- [ ] T035 spec Status 갱신, 이슈 #65 체크.

## Dependencies

- T004 → T005~T008 → T011~T013. T010(라우터)은 T011 전에.
- T014~T016(OpenSearch 내부 설정)은 코드로 먼저, 실행(T029)은 도메인 생성(T027) 뒤.
- T017~T019·T023·T024(서버 코드)는 인프라와 독립. 배포되면 로그가 JSON으로 바뀐다.
- 적용 순서: T027 → T028 → T029 → T030 → T031.

## Parallel Example

```
T002 | T003 | T009 | T014 | T017 | T020 | T021 | T025
```
