# Data Model: 서비스 로그 (OpenSearch)

## 인덱스

| 인덱스 (하루 단위) | 들어오는 것 | 보관(ISM) | 쓰는 주체 |
|---|---|---|---|
| `logs-app-YYYY-MM-DD` | API·에이전트 서버 로그(요청 기록 포함) | 14일 | Firehose `tms-logs-app` |
| `logs-pipeline-YYYY-MM-DD` | 수집·누락률·대시보드 적재·합성 적재·계약 검사·학습 스냅샷 알림 Lambda, Step Functions 실행 결과(EventBridge), Glue 오류 줄 | 14일 | Firehose `tms-logs-pipeline` |
| `activity-YYYY-MM-DD` | 사용자 활동(`log_type=activity`) | 28일 | Firehose `tms-logs-activity` |

샤드 1, 복제 0(노드 1개). 나중의 `rag-law`는 ISM 대상이 아니다.

## 공통 필드 (라우터 Lambda가 붙임)

| 필드 | 형 | 뜻 |
|---|---|---|
| `@timestamp` | date | 로그 시각(CloudWatch 이벤트 시각, UTC) |
| `log_group` | keyword | 예: `/tms/app/api`, `/aws/lambda/tms-collector` |
| `log_stream` | keyword | 로그 스트림 |
| `service` | keyword | 짧은 이름: `api`, `agent`, `tms-collector`, … |
| `level` | keyword | `ERROR`·`WARNING`·`INFO`·`DEBUG`. JSON의 `level`, Lambda의 `[ERROR]`, `Traceback`, `Task timed out` 등으로 추정, 없으면 `INFO` |
| `message` | text (+ `message.keyword` 256자) | 원문 한 줄 |
| `json.*` | object | 원문이 JSON이면 필드를 펼친 것(동적 매핑, 문자열은 keyword) |

## 요청 기록 (`log_type = request`, `logs-app`)

| 필드 | 형 | 예 |
|---|---|---|
| `json.method` | keyword | `GET` |
| `json.path` | keyword | `/api/me` |
| `json.status` | integer | 200 |
| `json.duration_ms` | float | 12.4 |
| `json.sub` | keyword | 회원 id(로그인 전이면 없음) |

## 사용자 활동 (`log_type = activity`, `activity`)

| 필드 | 형 | 값 |
|---|---|---|
| `json.event` | keyword | `session`, `invite_ok`, `invite_fail`, `invite_limited`, `favorite_add`, `favorite_remove`, `agent_question` |
| `json.target` | keyword | 즐겨찾기 대상 id(`favorite_*`만) |
| `json.sub` | keyword | 회원 id |

이메일·이름·초대 코드 입력값·질문 원문은 없다(FR-021).

## 보관 정책 (ISM)

| 정책 | 대상 | 동작 |
|---|---|---|
| `logs-14d` | `logs-app-*`, `logs-pipeline-*` | 생성 후 14일 → 삭제 |
| `activity-28d` | `activity-*` | 생성 후 28일 → 삭제 |

## 접근 (FGAC 역할 매핑)

| OpenSearch 역할 | 매핑되는 IAM 역할 | 권한 |
|---|---|---|
| `all_access` | `tms-logs-admin`(마스터, 사람이 설정 스크립트 실행 때 맡음) | 전체 |
| `firehose_writer`(새로) | Firehose 전달 역할 `tms-logs-firehose` | `logs-*`·`activity-*` 색인 생성·쓰기 |
| `readall` + `opensearch_dashboards_user` | `tms-logs-viewer`(Cognito `members`) | 검색·대시보드 보기 |
| (없음) | `tms-logs-noaccess`(Cognito 회원이지만 `members` 아님) | 거부 |

## 저장 객체 (`services/log-search/dashboards/`)

- 인덱스 패턴 3개: `logs-app-*`, `logs-pipeline-*`, `activity-*` (시간 필드 `@timestamp`)
- 대시보드 `운영 상태`: 서비스별 로그 수, 시간대별 오류 수, 최근 오류 목록, 요청 상태 코드·응답 시간, 수집 Lambda 실행 요약
- 대시보드 `사용 현황`: 하루 접속자(`json.sub` 고유 수, `event=session`), 초대 코드 통과·실패·차단 수, 즐겨찾기 상위 대상, 에이전트 질문 수
- 대시보드 `운영 상태`에 상태 머신 실행 결과(성공·실패) 표 추가
- 모니터 `errors-burst`(5분 오류 ≥ 10 → SNS)
