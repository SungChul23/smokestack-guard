# Research: 서비스 로그 수집·분석 (OpenSearch)

## R1. 도메인: 공개 엔드포인트, t3.small.search 1대, 1-AZ, 세분화된 접근 제어(FGAC)

- **Decision**: OpenSearch Service 도메인 `tms-logs`. `t3.small.search` × 1, gp3 10GB, 대기 모드 없음, AZ 1개, VPC 밖(공개 엔드포인트). FGAC 켬(내부 사용자 DB 끔, 마스터 = IAM 역할), HTTPS 강제(TLS 1.2), 저장 암호화·노드 간 암호화 켬. 엔진은 `OpenSearch_2.19`(2026-11-21 서울에서 쓸 수 있는 최신 2.x, 변수 `engine_version`).
- **Rationale**: 로그 저장소는 원본(CloudWatch)이 따로 있어 고가용성이 필요 없다. 공개 엔드포인트는 서브넷·보안그룹이 필요 없고, 팀원이 브라우저로 Dashboards에 들어올 수 있다. 보안은 IAM 서명 + Cognito 로그인 + FGAC 역할 매핑으로 지킨다.
- **Alternatives**: VPC 도메인(Firehose VPC 전송 28일 약 $9 + 터널 필요), Serverless(최소 OCU로 월 $170+), EC2 자체 설치(메모리 4GB 이상 필요, 관리형보다 싸지 않음).
- **비용**(서울 공식 가격표 2026-11-20): `t3.small.search` $0.056/h → 28일 $37.6, gp3 $0.1391/GB-월 → 10GB $1.3.
- **스위치**: `opensearch_enabled`(기본 true). false면 도메인·Firehose·구독 필터를 지운다. CloudWatch 원본·수집에는 영향 없음.

## R2. Dashboards 로그인 = 013 Cognito, 자격은 `members`

- **Decision**: 도메인 `cognito_options`에 사용자 풀 `tms-users` + **새 자격 증명 풀** `tms-logs`를 연결한다. 자격 증명 풀의 역할 규칙으로 `cognito:groups`에 `members`가 있으면 역할 `tms-logs-viewer`, 아니면 권한 없는 역할을 준다. FGAC에서 `tms-logs-viewer` → `readall` + `opensearch_dashboards_user`(대시보드·검색 보기·저장된 객체 읽기).
- **Rationale**: 로그인 체계를 하나로(Google + 초대 코드). 사용자 결정(2026-11-20): 팀원 전용 그룹은 두지 않고 `members` 전체.
- **알려진 수동 단계**: OpenSearch가 Cognito 연결 때 사용자 풀에 **자기 앱 클라이언트**(`AWSElasticsearch-tms-logs-…`)를 만든다. 이 클라이언트는 기본 공급자가 `COGNITO`라 Google을 더해야 한다(`aws cognito-idp update-user-pool-client`, quickstart §4). Terraform 밖에서 생기는 자원이라 문서로 남긴다.
- **필요한 역할**: `AmazonOpenSearchServiceCognitoAccess` 관리형 정책을 가진 서비스 역할(도메인이 Cognito를 설정할 때 씀).

## R3. 전달: 구독 필터 → 라우터 Lambda → Firehose 3개 → OpenSearch, 실패분 S3 (2026-11-21 수정)

- **처음 안의 문제**: 구독 필터 → Firehose(변환 Lambda) → OpenSearch로 설계했으나, **Firehose는 CloudWatch Logs를 OpenSearch 대상으로 보내지 못한다**(AWS 문서). CloudWatch가 로그 여러 건을 Firehose 레코드 하나로 묶어 보내고, OpenSearch 대상은 레코드 하나 = 문서 하나라서다. 변환 Lambda는 레코드를 1:1로만 돌려줘 여러 문서로 쪼갤 수 없다. Firehose의 압축 풀기·메시지 추출 기능도 S3·Splunk용이다.
- **Decision**:
  - 구독 필터의 대상을 **라우터 Lambda `tms-logs-router`**로 한다. 라우터가 CloudWatch 묶음(gzip)을 풀어 **로그 한 줄 = 레코드 하나**로 만들고, `log_group`·`service`·`@timestamp`·`level`·`json.*`를 붙여 알맞은 Firehose에 `PutRecordBatch`로 보낸다.
    - 서버 그룹(`/tms/app/api`·`/tms/app/agent`): `json.log_type == "activity"`면 `tms-logs-activity`, 나머지는 `tms-logs-app` (구독 필터 하나로 나눔)
    - Lambda 그룹 6개, Glue 오류 줄: `tms-logs-pipeline`
  - Step Functions 실행 상태 이벤트(EventBridge, R9)도 같은 라우터가 받아 `tms-logs-pipeline`에 넣는다.
  - Firehose 3개(Direct PUT, 변환 없음): `tms-logs-app` → `logs-app`, `tms-logs-pipeline` → `logs-pipeline`, `tms-logs-activity` → `activity`(하루 회전). 실패분은 새 버킷 `smokestack-tms-logs-952900391026`(수명 주기 28일)에 `FailedDocumentsOnly`.
  - 제어 메시지(CONTROL_MESSAGE)는 버린다. `PutRecordBatch` 부분 실패는 다시 보내고, 그래도 실패하면 예외로 끝내 구독 필터가 재시도하게 한다.
- **Rationale**: 요구사항(CloudWatch → Firehose → OpenSearch)을 지키면서 문서를 한 줄씩 만든다. 나누는 규칙이 라우터 한 곳에 있어 서버 그룹에 구독 필터를 두 개 걸 필요가 없다. 라우터 Lambda는 무료 범위 안.
- **Alternatives**: CloudWatch Logs → OpenSearch 직접 구독(콘솔이 만드는 Lambda) — 요구사항의 Firehose가 빠지고 실패 보관이 없음. Firehose → S3 → 다른 적재 — 지연·구성 증가.
- **비용**: Firehose $0.036/GB(Direct PUT, 레코드 5KB 단위 올림 — 로그 한 줄은 작아 GB당보다 레코드 수 영향이 커질 수 있으나 하루 수 MB·수만 줄 수준이라 28일 $1 미만). 라우터 Lambda 무료 범위.
- **수집 영향 없음**: 구독 필터는 로그 그룹에만 붙고 수집 Lambda 코드·역할·스케줄을 바꾸지 않는다(SC-008).
- 참고: [Send CloudWatch Logs to Firehose](https://docs.aws.amazon.com/firehose/latest/dev/writing-with-cloudwatch-logs.html)

## R4. 서버 요청·활동 기록 (구조화 로그)

- **Decision**: API·에이전트에 요청 미들웨어를 둔다. 요청마다 JSON 한 줄 `{"log_type":"request","method","path","status","duration_ms","sub"}`. `/health`·`/api/health`·`/agent/health`는 남기지 않는다. uvicorn 기본 접근 로그는 끈다(`--no-access-log`). 활동은 `log_activity(event, sub)` → `{"log_type":"activity","event","sub"}`.
  - `session`: `/api/me` 호출(로그인 후 화면 진입) — 하루 접속자는 `sub` 고유 수
  - `invite_ok`: 초대 코드 통과
  - `agent_question`: 에이전트 질문(D가 질문 라우트에서 호출, 계약 문서로 전달)
- **개인 정보**: `sub`만. 이메일·이름·코드 입력값·질문 원문은 남기지 않는다(FR-021). 경로에 개인 정보가 들어가는 라우트는 쓰지 않는다.
- **형식 계약**: `contracts/log-format.md`.

## R5. 인덱스 템플릿·보관(ISM)·초기 설정은 스크립트로

- **Decision**: `services/log-search/setup_opensearch.py`(사람이 실행, SigV4, 표준 라이브러리 + botocore)가 멱등으로 적용한다: 인덱스 템플릿 3개, ISM 정책 2개(14일·28일 삭제), FGAC 역할 매핑(Firehose 쓰기, 뷰어 읽기, 관리자), 알림 채널(SNS) + 모니터, Dashboards 저장 객체(`dashboards/*.ndjson`) 가져오기.
- **Rationale**: 이 설정들은 OpenSearch REST API에만 있다. Terraform용 OpenSearch provider를 더하면 provider가 도메인에 접속해야 해서 같은 스택에서 순서가 꼬인다. 저장소의 정의 파일 + 멱등 스크립트면 도메인을 지웠다 다시 만들어도 복구된다(SC-007).
- **Alternatives**: `opensearch-project/opensearch` Terraform provider(위 순서 문제), 콘솔 수작업(복구 불가).

## R6. 오류 알림 = OpenSearch Alerting → SNS 운영 토픽

- **Decision**: 모니터 `errors-burst`: `logs-app-*`·`logs-pipeline-*`에서 최근 5분 `level:ERROR` 수 ≥ 10 → 알림 채널(SNS `tms-collector-alerts`). OpenSearch가 SNS에 발행할 역할 `tms-logs-sns`.
- **Rationale**: 요구사항이 OpenSearch 모니터링이고, 운영 메일은 기존 토픽 하나로 모은다.
- 기준 10회·5분은 변수로 두고 운영하며 조정.

## R7. 실제 로그 양 (2026-11-21 확인)

| 로그 그룹 | 저장 바이트 (14일 보관) |
|---|---|
| `/aws/lambda/tms-collector` | 1,395,352 |
| `/tms/app/api` | 1,064,518 |
| `/tms/app/agent` | 1,046,494 |
| `/aws/lambda/tms-synthetic-train` | 137,077 |
| `/aws/lambda/tms-dashboard-load` | 82,275 |
| `/aws/lambda/tms-ktms-ml-ready-check` | 17,946 |
| `/aws/lambda/tms-missing-rate` | 9,898 |
| `/aws/lambda/tms-training-snapshot-notice` | 1,469 |
| **합계** | **약 3.8MB** |

- 저장 바이트는 압축된 크기라 실제 수집량은 몇 배 크지만, 그래도 **하루 수 MB 수준**이다(가정했던 하루 100MB보다 훨씬 작음).
- 그래서 디스크 10GB(도메인 최소에 가까움)·보관 14일로 충분하고, Firehose·CloudWatch 수집 비용은 28일 $1 미만이다. 비용은 사실상 **도메인 인스턴스($37.6) + 디스크($1.3) ≈ $39**.
- 서버 요청 기록(JSON)을 더하면 서버 로그가 늘지만 화면 사용량(팀·시연자) 기준 하루 수십 MB를 넘지 않는다.
- 대상에 `tms-training-snapshot-notice`(015)도 넣는다.

## R9. Step Functions 실행 결과와 Glue 오류도 모은다 (2026-11-21 결정)

- **Decision**:
  - Step Functions: EventBridge 규칙(`aws.states`, `Step Functions Execution Status Change`, 상태 `SUCCEEDED`·`FAILED`·`TIMED_OUT`·`ABORTED`, 상태 머신 `tms-silver2-ktms`·`tms-dashboard-load`) → 라우터 Lambda → Firehose `tms-logs-pipeline`. 라우터가 EventBridge 이벤트(JSON 한 건)를 문서로 바꾼다(`service = <상태 머신>`, `level = ERROR`(실패·시간 초과·중단) / `INFO`, `json.status`, `json.execution`, 시작·종료 시각).
  - Glue: `/aws-glue/tms-silver`에 구독 필터 `?ERROR ?Exception ?Traceback` → `tms-logs-pipeline`.
- **Rationale**: 상태 머신은 로그 설정이 없어 지금은 콘솔에서만 결과를 본다. 상태 머신 로그를 켜는 대신 실행 상태 이벤트를 받으면 정의를 바꾸지 않고 양도 하루 수십 건이다. Glue(Spark) 전체 로그는 양이 많고 쓸모가 적어 오류 줄만 받는다.
- **Alternatives**: 상태 머신 `logging_configuration`(ALL) — 단계마다 로그가 생겨 양이 늘고 두 스택을 고쳐야 함.

## R10. 사용자 활동 사건 확장 (2026-11-21 결정)

- `session`(`/api/me`), `invite_ok`·`invite_fail`·`invite_limited`(`/api/invite`), `favorite_add`·`favorite_remove`(D의 `/api/favorites` PUT·DELETE), `agent_question`(D, 질문 기능 연결 때).
- 서버가 확실히 아는 사건만 남긴다. 화면 클릭·페이지 이동은 GA4(요구사항 2) 몫.
- 초대 코드 실패·차단은 무차별 시도 감시용 보안 지표다.

## R8. 나중의 법령 RAG

- 이 기능 범위 밖(문서 준비 뒤 별도 이슈). 같은 도메인에 `rag-law` 인덱스를 더할 수 있게 ISM은 `logs-*`·`activity-*`에만 걸고, FGAC 역할 매핑에 RAG 역할을 더할 자리만 둔다. 한국어 분석기(nori)는 OpenSearch Service에 기본 포함.

## 참고

- [Amazon OpenSearch Service 요금](https://aws.amazon.com/ko/opensearch-service/pricing/), [지원 인스턴스 유형](https://docs.aws.amazon.com/ko_kr/opensearch-service/latest/developerguide/supported-instance-types.html)
- [Amazon Data Firehose 요금](https://aws.amazon.com/firehose/pricing/), [Amazon CloudWatch 요금](https://aws.amazon.com/en/cloudwatch/pricing)
- 서울 가격은 AWS 공개 가격표(`pricing.us-east-1.amazonaws.com/offers/v1.0/aws/<서비스>/current/ap-northeast-2/index.json`, 2026-11-20)에서 읽었다.
