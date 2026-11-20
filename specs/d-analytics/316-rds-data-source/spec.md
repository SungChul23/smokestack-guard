# 316 — 에이전트 RDS 데이터 소스

상태: **초안 (구현 전, 확인 대기)**. 작성 2026-11-20. 담당 D(`jaeyan42`). 부담당 E.
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

## 5. 결정이 필요한 것

| # | 항목 | 제안 | 비고 |
|---|---|---|---|
| 1 | 접속 계정 | **`tms_app`(IAM 인증)**. 관리자 계정은 쓰지 않는다 | 서버 역할에 `rds-db:connect .../tms_app`이 필요(PR #63 T039, A). 지금 계약 문서(app-runtime.md)는 관리자 비밀을 가리킨다 |
| 2 | `site_id`가 없는 굴뚝 | 에이전트에서 **제외**하고 기록만 남긴다 | 동명 사업장(한국주강㈜ 2곳) 등. 몇 개인지 확인 필요(§6) |
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

## 8. 하지 않는 것

- RDS에 쓰지 않는다. 마이그레이션을 만들지 않는다(A 소유, `services/dashboard-load/`).
- 관리자 비밀번호를 에이전트가 읽지 않는다.
- 이 spec 안에 접속 정보·비밀값을 적지 않는다.
