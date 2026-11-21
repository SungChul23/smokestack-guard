# 316 — 에이전트 RDS 데이터 소스

상태: **구현 완료, 실제 RDS 확인 대기**(§9). 작성 2026-11-20. 담당 D(`jaeyan42`). 부담당 E.
관련: `specs/a-platform/012-dashboard-rds-load/`(A, PR #63 머지), `specs/a-platform/009-service-infra/contracts/app-runtime.md`

## 1. 왜

에이전트는 지금 하루치 정적 JSON(`JsonDayDataSource`)이나 빈 데이터(`InMemoryDataSource`)로만 뜬다. 서버(EC2)에는 데이터가 없어서 그대로 올리면 모든 사업장이 "찾을 수 없음"이 된다.
A가 K-TMS 관측을 RDS(`obs.*`, `ref.*`)에 채웠다(2026-10-30 15:00 ~ 2026-11-20 09:30, 3,806,119행, 30분마다 갱신). 에이전트가 이를 읽게 한다.

## 2. 범위

- `DataSource` 프로토콜(`app/agent/tools.py`, 메서드 5개)의 **RDS 구현 하나**를 추가한다. 에이전트의 다른 코드(관문, 계획기, 도구 계산, 검증)는 바꾸지 않는다.
- 접속은 **읽기 전용**이다. 에이전트는 `obs`·`ref`에 쓰지 않는다.
- 범위 밖: 체크포인터를 RDS로 옮기기(별도), 즐겨찾기 서버 저장(별도), 법령 벡터를 `rag.doc_chunk`로 옮기기(별도), 화면 연결.

## 3. 메서드별 대응

| `DataSource` 메서드 | RDS 쪽 |
|---|---|
| `list_stacks()` | `ref.v_stack`(굴뚝 → 사업장 코드) + `ref.site`(이름·시도·시군구). 에이전트 키는 `"{site_id}:{stack_code}"` |
| `get_stack(stack_key)` | 위 목록에서 키로 찾기(시작 때 한 번 읽어 메모리에 둔다. 굴뚝 약 3천 개) |
| `find_stacks(business, code)` | 메모리 목록에서 `norm_name` 비교(지금 구현과 같음) |
| `observations(stack_key, item, start, end)` | `obs.measurement_30m`을 `(stack_key, item, measured_at)` 기본키로 구간 조회. 상태·기준값은 같은 행에 있다 |
| `as_of()` | `max(measured_at)`(`measured_at` 인덱스 사용). 일정 시간 캐시 |

- **상태 코드는 변환이 필요 없다.** RDS `ref.status_code`(0 ok, 1~5, 8 미측정, 9 확인 불가, 99 기타)와 에이전트 `tools.py`의 코드가 같다.
- 상태 행의 `value`는 RDS에서 null이다. 에이전트의 `Observation.value`는 `float | None`이라 그대로 받는다(JSON 소스는 0.0으로 넣었다. 계산 도구가 상태 코드로 거르므로 영향이 없는지 시험으로 확인한다).
- 시각: RDS는 KST 벽시계(시간대 없음) → 에이전트 쪽은 `tzinfo=KST`를 붙인다.

## 4. 확인한 사실 (DBeaver, admin, 2026-11-20)

- 범위·행 수는 위와 같다.
- 성주군 생활폐기물 소각시설(`130554`): `ref.site`에 있고 위도 35.925547, 경도 128.310255. CleanSYS 웹 좌표를 변환한 값과 소수 6자리까지 일치.
- `obs.v_measurement_site` 형태: `stack_key`, `area_nm`, `fact_manage_nm`, `stack_code`, `site_id`, `frontend_stack_id`(비어 있음), `item`, `measured_at`, `obs_date`, `value`(상태 행은 null), `limit_value`, `ratio_pct`, `status_code`, `status`, `status_display`, `status_explanation`(비어 있음), `counts_in_stats`, `loaded_at`, `semantic_version`(v1).

- 사업장에 연결되지 않은 굴뚝: 2,925개 중 **0개**(2026-11-20, `ref.stack` ↔ `ref.v_stack`).
- 굴뚝 키 형식 예: `강원도|㈜KCC 문막공장|1`(`지역|사업장|굴뚝번호`). 에이전트 키 `"{site_id}:{굴뚝번호}"`와 다르므로 변환은 `ref.v_stack`의 `site_id`로 한다.

## 5. 결정이 필요한 것

| # | 항목 | 제안 | 비고 |
|---|---|---|---|
| 1 | 접속 계정 | **`tms_app`(IAM 인증)**. 관리자 계정은 쓰지 않는다 | 서버 역할에 `rds-db:connect .../tms_app`이 필요(PR #63 T039, A). 지금 계약 문서(app-runtime.md)는 관리자 비밀을 가리킨다 |
| 2 | `site_id`가 없는 굴뚝 | 에이전트에서 **제외**하고 기록만 남긴다(방어용 규칙) | 2026-11-20 확인: 굴뚝 2,925개 중 연결 안 된 것 **0개**. 지금은 해당 없고, 새 굴뚝이 생길 때를 위한 규칙이다. 동명 사업장(한국주강㈜ 2곳)은 관측이 생기면 사람이 연결 |
| 3 | DB 드라이버 | `psycopg`(v3) | 이후 LangGraph 체크포인터(`langgraph-checkpoint-postgres`)와 같은 드라이버. A의 적재 Lambda는 `pg8000`(레이어 사정) |
| 4 | 연결 방식 | 연결 풀 + 토큰 15분 만료 시 재발급 | IAM 토큰은 15분 유효 |
| 5 | 시작 시 목록 읽기 | 굴뚝 목록은 시작 때 1회 + 1시간 갱신 | 새 굴뚝이 생겨도 재시작 없이 반영 |

## 6. 먼저 확인할 것 (DBeaver, 읽기 전용)

```sql
-- (a) 사업장에 연결되지 않은 굴뚝이 몇 개인가
SELECT count(*) FILTER (WHERE s.site_id IS NULL) AS unmapped, count(*) AS total
FROM ref.stack st LEFT JOIN ref.v_stack s USING (stack_key);

-- (b) 한 굴뚝 하루 조회 시간 (실행 시간만 본다)
SELECT measured_at, value, limit_value, status_code
FROM obs.measurement_30m
WHERE stack_key = '<아무 굴뚝 키>' AND item = 'nox'
  AND measured_at >= '2026-11-19' AND measured_at < '2026-11-20';

-- (c) 시도 이름 표기 (에이전트의 지역 질문과 맞는지)
SELECT region_sido, count(*) FROM ref.site GROUP BY 1 ORDER BY 2 DESC;
```

## 7. 시험 계획

- 같은 `DataSource` 계약 시험을 `InMemoryDataSource`, `JsonDayDataSource`, `RdsDataSource` 세 구현에 돌린다.
- RDS 구현은 A의 마이그레이션(`services/dashboard-load/migrations/001~006`)을 올린 PostgreSQL 컨테이너에서 시험한다(A도 같은 방식, 30개 통과). Docker 데몬이 필요하다.
- 실제 RDS 확인은 사람이 베스천 터널로 한 번(`tms_app` IAM 접속이 열린 뒤).

## 9. 구현 결과 (2026-11-20)

**파일**: `app/agent/rds_data.py`(`RdsDataSource`), `app/agent/rds_connect.py`(IAM 접속 풀), `app/agent/api.py`(`AGENT_DATA_SOURCE=rds`, 503 처리), 시험 3개(`tests/test_rds_data.py`, `test_rds_connect.py`, `test_rds_data_pg.py`), 의존성 `psycopg[binary,pool]`·`boto3`.

**§5 결정은 제안대로 구현했다**: `tms_app` + IAM 인증, 사업장 코드 없는 굴뚝 제외(JOIN), `psycopg`, 풀 + 연결마다 새 토큰, 굴뚝 목록 1시간 캐시(관측 최신 시각 `as_of`는 60초).

**추가로 정한 것**
- 연결마다 `default_transaction_read_only=on`, `statement_timeout=8000`ms를 건다(권한과 별개의 이중 방어).
- DB 장애는 `DataSourceUnavailable` → HTTP **503**(안내 문구만, 접속 정보는 응답·로그에 없음). 서비스 조립 단계 실패도 같다.
- 접속 풀은 프로세스에서 하나만 만든다(`_rds_pool`). 조립이 실패해 다시 시도돼도 풀이 늘지 않는다.
- 상태 행의 `value`는 null 그대로 넘긴다(계산 도구가 이미 `value is None` 행을 거른다).

**서버 환경 변수** (서버가 뜰 때 SSM `/tms/app/config/<이름>`에서 `<이름 대문자, - 는 _>`로 들어간다)

| 환경 변수 | SSM 이름 | 값 | 비고 |
|---|---|---|---|
| `AGENT_DATA_SOURCE` | `agent-data-source` | `rds` | 없으면 지금처럼 빈 데이터 |
| `DB_HOST` | `db-host` | (이미 있음) | |
| `DB_USER` | `db-user` | `tms_app` | 없으면 기본값 `tms_app` |
| `DB_NAME`, `DB_PORT` | (고정값이 이미 들어감) | `tms`, `5432` | |
| `DB_SSLROOTCERT` | `db-sslrootcert` | RDS 인증서 묶음 경로 | 없으면 `sslmode=require`. 있으면 `verify-full`. 인증서를 이미지에 넣는 일은 아직 안 했다 |
| `AGENT_LLM_BACKEND` | `agent-llm-backend` | `none` | Bedrock은 켜기 전까지 `none` |

**시험 결과**
- CI 조건(DB 없음, 깨끗한 Python 3.11 환경): ruff 통과, **369 통과 / 18 건너뜀**.
- PostgreSQL 16 + pgvector 컨테이너에 A의 마이그레이션 001~006을 올리고, 기준 데이터를 심어 **실제 `tms_app` 역할**로 읽은 시험 포함: **387 통과**.
  - 굴뚝×물질 전체(하루치, 200건 넘게)가 InMemory 결과와 한 줄씩 같다(상태 행 `value`의 null/0.0 차이만 제외).
  - 같은 질문 6개와 후속 질문("그럼 SOx는?")의 **응답 전체**가 InMemory와 RDS에서 같다(요청 id·소요 시간·카드 id 제외).
  - `tms_app`은 읽을 수 있고 `obs`·`ref`에 쓰면 거부된다. 세션 옵션만으로도 `app` 스키마 쓰기가 막힌다.
- 실제 `docker build`(linux/amd64) 성공. 컨테이너에서 DB가 닫혀 있을 때: `/health` 200, 질문은 약 10초 뒤 503.
- 실제 RDS 조회 속도(DBeaver, admin): 한 굴뚝 하루 `Execution Time` **9.3ms**(기본키 인덱스).

**아직 하지 않은 것**
- **실제 RDS에 `tms_app` IAM으로 접속**(서버 역할에 `rds-db:connect` 필요, T039, A).
- RDS 인증서 묶음을 이미지에 넣어 `verify-full`로 접속.
- 체크포인터를 RDS로 옮기기, 즐겨찾기 서버 저장, 법령 벡터 `rag.doc_chunk` 이전(범위 밖).
- 시험이 읽는 마이그레이션은 `services/dashboard-load/migrations/`다. 이 폴더가 병합으로 들어오기 전에는 `TMS_MIGRATIONS_DIR`로 위치를 지정해야 한다.

## 8. 하지 않는 것

- RDS에 쓰지 않는다. 마이그레이션을 만들지 않는다(A 소유, `services/dashboard-load/`).
- 관리자 비밀번호를 에이전트가 읽지 않는다.
- 이 spec 안에 접속 정보·비밀값을 적지 않는다.
