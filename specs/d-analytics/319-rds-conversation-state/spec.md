# 319 — 대화 상태와 재시도 응답을 RDS에 저장 (서버 2대 대비)

상태: **구현 완료, 실제 RDS 확인 대기**. 작성 2026-11-20. 담당 D(`jaeyan42`). 부담당 E.
관련: spec 316(RDS 읽기), A의 `specs/a-platform/012-dashboard-rds-load/data-model.md` §6·§7(`app` 스키마, `tms_app`)

## 1. 왜

에이전트는 대화 상태를 `InMemorySaver`(서버 프로세스 메모리)에 두었다. 서버(EC2)를 1대만 켜면 문제가 없지만, ALB는 요청을 라운드로빈으로 나눈다(대상 그룹에 고정 세션 설정 없음). 서버가 2대 이상이거나 재시작하면 두 가지가 깨진다.

1. **카드 응답이 다른 서버로 가면 카드를 못 찾는다.** 카드 대기 상태가 메모리에 있다.
2. **재시도가 거짓 오류가 된다.** `service.py`의 `request_id` 캐시(`_done`)도 프로세스 메모리에 있다. 클라이언트가 응답을 못 받고 같은 `request_id`로 다시 보냈을 때, 다른 서버는 캐시가 없어 다시 실행한다. 카드 선택은 첫 호출이 이미 카드를 소비했으므로 **"이 카드는 만료되었습니다"**라는 거짓 오류가 난다(시험으로 재현: `test_without_the_shared_store_the_retry_would_look_expired`).

## 2. 설계

| 항목 | 내용 |
|---|---|
| 대화 상태 | LangGraph 공식 `PostgresSaver`(`langgraph-checkpoint-postgres`)를 `app` 스키마에서 쓴다. 표(`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`)는 라이브러리가 `setup()`으로 만든다(A의 data-model §6이 정한 방식). 이미 있으면 그대로 |
| 재시도 응답 | `app.chat_response(user_sub, request_id, response jsonb, created_at)`, 기본키 `(user_sub, request_id)`. 먼저 쓴 응답이 이긴다(`ON CONFLICT DO NOTHING`). 10분 안의 재시도만 인정하고, 50번 저장할 때마다 24시간 지난 행을 지운다 |
| 접속 | 쓰기 풀 하나(`make_pool(read_only=False, search_path="app")`)를 둘이 함께 쓴다. 계정은 `tms_app`(IAM). `obs`·`ref`는 읽기만, `app`은 쓰기 가능(A의 권한 설정) |
| 켜는 법 | `AGENT_CHECKPOINT=postgres`. 없으면 메모리(지금과 같음) |
| 끊어진 연결 | 풀이 연결을 꺼내 쓰기 전에 점검해서 버린다(`check=check_connection`). DB 점검·장애·Multi-AZ 전환 뒤에도 서버가 살아 있다 |
| 장애 응답 | 대화 저장소 오류는 `DataSourceUnavailable`로 바꿔 **503**과 안내 문구로 응답한다(접속 정보 없음) |
| 재시도 저장 실패 | **최선 노력**이다. 저장이 안 돼도 이미 만든 답은 사용자에게 돌려주고 경고 로그만 남긴다. 읽기 실패는 처음 보는 요청으로 처리한다 |

**고르지 않은 것**: Redis 등 별도 저장소(운영 부담과 비용), 고정 세션(서버 장애 시 대화가 사라지고, ALB 설정은 A 영역).

## 3. 서버 환경 변수 (SSM `/tms/app/config/<이름>`)

spec 316 §9의 표에 이것이 추가된다.

| 환경 변수 | SSM 이름 | 값 |
|---|---|---|
| `AGENT_CHECKPOINT` | `agent-checkpoint` | `postgres` (서버를 2대 이상 켜기 전에 필수) |

## 4. RDS가 Multi-AZ가 아니라는 점 (2026-11-20 확인)

실제 RDS는 `MultiAZ=False`, 가용 영역 `ap-northeast-2c` 하나, `db.t4g.micro` 한 대다(A: 시연 전 Multi-AZ). 2개 AZ에 걸쳐 있는 것은 DB 서브넷 그룹과 앱 서버이고 DB 인스턴스는 하나다.
- 지금은 DB 점검·재시작 때 대화 상태 저장이 잠시 끊긴다 → 503, 복구되면 이어진다(끊어진 연결 점검).
- Multi-AZ를 켜면 failover 때 엔드포인트가 새 인스턴스를 가리킨다. 풀의 연결 점검과 `max_lifetime=3000`초로 새로 맺는다. 시험은 `pg_terminate_backend`로 연결을 끊는 방식으로 했고, **실제 failover는 확인하지 못했다.**

## 5. 시험 결과 (2026-11-20)

- CI 조건(DB 없음, 깨끗한 Python 3.11): ruff 통과, **381 통과 / 28 건너뜀**.
- PostgreSQL 16 + pgvector 컨테이너(A의 마이그레이션 001~006, **실제 `tms_app` 역할**)를 포함하면 **409 통과**. 이 중 새 시험은 DB 단위 10개, DB 실제 10개, 접속 설정 2개.
- 실제 DB로 "서버 2대"(각자 새 풀·체크포인터·저장소)를 흉내 내 확인한 것:
  - 서버 1에서 카드를 묻고 서버 2에서 답하면 `ANSWERED`.
  - 서버를 닫고 새로 띄운 뒤에도 카드 답이 이어진다.
  - 다른 사용자는 남의 카드를 이어받지 못한다(`만료`).
  - 후속 질문("그럼 SOx는?")이 서버가 달라도 한 서버의 결과와 같다.
  - 카드 선택 **재시도가 다른 서버로 가도** 같은 답을 돌려준다(저장소 없으면 거짓 `만료`).
  - 질문(메시지) 재시도는 다른 서버가 해석하지도 않는다.
  - 10분 넘은 재시도 응답은 무시하고, 24시간 넘은 행은 정리된다.
  - 모든 표가 `app` 스키마에만 있고(`setup` 반복 실행도 안전), DB가 연결을 끊어도 다음 호출이 성공한다.
- `docker build`(linux/amd64) 성공. 기본은 지금과 같고, `AGENT_CHECKPOINT=postgres`에 DB가 닫혀 있으면 질문은 약 10초 뒤 503.

## 6. 아직 하지 않은 것·한계

- **실제 RDS에서 실행**: `tms_app` IAM 접속(서버 역할 `rds-db:connect`, #63 T039)과 서버 켜기가 필요하다. 시험의 접속은 로컬 컨테이너의 시험용 비밀번호다.
- **체크포인트 정리(보관 정책)**: LangGraph는 단계마다 체크포인트를 쌓는다. 지금은 오래된 대화를 지우지 않는다. `delete_thread`나 SQL로 N일 지난 대화를 지우는 작업이 필요하다(별도 작업).
- **같은 대화에 동시 요청 2개**(더블클릭 등)가 서로 다른 서버로 가면 LangGraph가 서버 사이에서 잠그지 않는다. 드문 경우라 다루지 않았다.
- 대화·질문 **기록 저장**(`app.conversation`, `app.message`, `app.query_log`)은 별개 작업이다.
- 설정 오류(`DB_HOST` 없음)는 503이 아니라 500이다. 잘못된 배포를 숨기지 않으려는 의도다.
