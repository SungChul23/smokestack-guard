# Data Model: 대시보드용 K-TMS 관측 RDS 적재

DB `tms`(RDS PostgreSQL 16, 009). 스키마 5개: `ref`(기준 정보), `obs`(관측), `ops`(적재 운영 기록), `app`(사용자·대화, D), `rag`(문서 벡터, D). 시각은 모두 **KST 벽시계 `timestamp`(시간대 없음)**로 저장한다. Silver의 `ts_kst`와 같다. API가 응답할 때 `+09:00`을 붙인다.

## 1. `obs.measurement_30m` — 30분 관측

| 컬럼 | 타입 | null | 출처·규칙 |
|---|---|---|---|
| `stack_key` | text | 아니오 | `area_nm \|\| '\|' \|\| fact_manage_nm \|\| '\|' \|\| stack_code` (ML-ready `stack_code`와 같은 규칙) |
| `item` | text | 아니오 | `nox`, `sox`만 |
| `measured_at` | timestamp | 아니오 | Silver `ts_kst` |
| `value` | double precision | 예 | Silver `value`. 상태 행은 **null**(0으로 채우지 않음) |
| `limit_value` | double precision | 예 | Silver `limit` |
| `ratio_pct` | double precision | 예 | Silver `ratio × 100` (100 = 허용기준) |
| `status_code` | smallint | 아니오 | `ref.status_code.code` (Silver `status`를 번호로) |
| `load_path` | text | 아니오 | `recent`(30분) / `backfill`(다시 채우기) |
| `loaded_at` | timestamptz | 아니오 | 적재 시각 |

- 기본키 `(stack_key, item, measured_at)`. 보조 인덱스 `(measured_at)`(지도: 한 시각의 전국), `(stack_key, item, measured_at DESC)`는 기본키로 대신한다.
- UPSERT는 `value`, `limit_value`, `ratio_pct`, `status_code` 중 하나라도 다를 때만 갱신한다(`IS DISTINCT FROM`). 같으면 `loaded_at`도 바꾸지 않는다.
- 행 수: 하루 약 18만~20만, 12월 중순까지 약 1,000만. 분할 없음.

## 2. `obs.daily_stack_summary` — 굴뚝·물질·일

기본키 `(stack_key, item, obs_date)`. `obs_date`는 KST 날짜.

| 컬럼 | 규칙 |
|---|---|
| `slots_expected` | 48 |
| `n_ok`, `n_zero` | `ok` 칸 수, 그중 값 0 |
| `n_stopped`, `n_checking`, `n_no_signal`, `n_maintenance`, `n_inspection`, `n_not_monitored`, `n_ambiguous`, `n_other` | 상태별 칸 수 |
| `n_missing` | 48 − (그날 행 수). 행 자체가 없는 칸 |
| `mean_value`, `max_value`, `max_at`, `min_value` | `ok` 행만, 0 포함 |
| `mean_ratio_pct`, `max_ratio_pct` | `ok` 행만 |
| `n_ge_90`, `n_ge_100`, `n_gt_100` | `ok` 행 중 비율 ≥90, ≥100, >100 칸 수 |
| `limit_min`, `limit_max` | 그날 허용기준 범위(기준이 바뀐 날 구분) |
| `computed_at` | 계산 시각 |

`ok` 칸이 0개면 통계 컬럼은 null이다.

## 3. `obs.daily_national_summary` — 전국·물질·일

기본키 `(obs_date, item)`.

| 컬럼 | 규칙 |
|---|---|
| `max_ratio_pct`, `max_stack_key`, `max_at` | 그날 전국 최고 비율과 그 굴뚝·시각(동률이면 이른 시각, 그다음 키 순) |
| `max_value` | 그 행의 측정값 |
| `mean_ratio_pct` | 그날 전국 `ok` 행 평균 |
| `n_stacks_reporting` | `ok` 행이 하나라도 있는 굴뚝 수 |
| `n_stacks_ge_90`, `n_stacks_gt_100` | 그날 한 번이라도 ≥90, >100이었던 굴뚝 수 |
| `computed_at` | |

## 4. `ref` — 기준 정보

### `ref.status_code` (마이그레이션이 고정값으로 채움)

| `code` | `status` | 원문 | `display_ko` | `counts_in_stats` |
|---|---|---|---|---|
| 0 | `ok` | (숫자) | 값 | true |
| 1 | `stopped` | 측정자료확인중(가동중지) | 가동중지 | false |
| 2 | `checking` | 측정자료확인중 | 확인중 | false |
| 3 | `no_signal` | 미수신 | 미수신 | false |
| 4 | `maintenance` | 보수중 | 보수중 | false |
| 5 | `inspection` | 기기점검 | 점검중 | false |
| 8 | `not_monitored` | (값·기준 없음) | 미측정 | false |
| 9 | `ambiguous` | (같은 조합 충돌) | 확인 불가 | false |
| 99 | `other` | (그 밖의 문자열) | 기타 | false |

`explanation_ko`(에이전트 설명 문구)는 비워 두고 C·B 확인 뒤 채운다. Silver에 없는 상태 문자열이 오면 적재는 실패한다(계약 위반, 알림).

### `ref.site` — 사업장

`site_id` text PK(CleanSYS 사업체 코드), `display_name`, `region_sido`, `region_sigungu`, `address`, `lat`, `lon`, `coordinate_source`, `source_version`(사업장 목록 버전), `loaded_at`.

### `ref.site_name_map` — 이름 이력

PK `(area_nm, fact_manage_nm, valid_from)`. `site_id` FK, `valid_to`(null = 현재), `confirmed_by`(`auto` 또는 사람), `note`. 이름이 바뀌면 행을 추가한다. 동명 사업장(한국주강)은 사람이 확인한 행만 둔다.

### `ref.stack` — 굴뚝

`stack_key` text PK, `area_nm`, `fact_manage_nm`, `stack_code`, `frontend_stack_id`(`KS-…`, null 허용), `collision_flag` boolean, `first_seen`, `source`(`site_list` = 사업장 목록에서 / `observed` = 적재 중 처음 본 키).

- 사업장 코드는 이 표에 저장하지 않고 `ref.site_name_map`(현재 유효한 행)으로 찾는다. 뷰 `ref.v_stack`이 `stack_key → site_id`를 계산해 준다. 이름 이력에 한 줄을 추가하면 과거 관측까지 바로 이어진다(US3-3).
- 적재가 처음 본 굴뚝 키는 `source = observed`로 이 표에 추가한다(사업장 코드 없이). 그래서 화면은 모든 관측 굴뚝을 표에서 찾을 수 있다.

읽기 예(화면·에이전트):
```sql
SELECT m.*, s.site_id, s.frontend_stack_id, si.lat, si.lon
FROM obs.measurement_30m m
LEFT JOIN ref.v_stack s USING (stack_key)
LEFT JOIN ref.site si ON si.site_id = s.site_id
WHERE m.measured_at >= $1 AND m.measured_at < $2;
```

## 5. `ops` — 적재 운영 기록

- `ops.schema_migrations(version text PK, applied_at)`
- `ops.load_run(run_id PK, path, started_at, finished_at, source_range jsonb, rows_upserted, rows_unchanged, skipped_reason, result)`: 실행 요약(FR-021). 로그와 같은 내용을 DB에도 남긴다.
- `ops.mapping_report(report_date, check_type, detail jsonb, PK(report_date, check_type))`: 매일 점검. `check_type` = `A`(관측에는 있는데 `ref`에 없는 이름) / `B`(`ref`에는 있는데 그날 관측이 없는 굴뚝)
- `ops.unmapped_name(area_nm, fact_manage_nm, first_seen, alerted_at, resolved_at, PK(area_nm, fact_manage_nm))`: 같은 이름 반복 알림 방지(FR-010)

## 6. `app`·`rag` — 구조만 (D 앱이 채움)

D 제안(2026-11-18)의 표를 그대로 만든다. `app.user_favorite`, `app.conversation`, `app.message`, `app.query_log`, `rag.doc_chunk`(`embedding vector(1024)`, 차원은 D가 고르는 임베딩 모델에 맞춰 바꿀 수 있음, `text_tsv` + GIN, 벡터 인덱스 HNSW). LangGraph 체크포인트 표는 D 앱이 라이브러리로 만든다(`app` 스키마 쓰기 권한).

## 7. 계정과 권한

| 계정 | 로그인 | 권한 |
|---|---|---|
| `tms_admin` | 비밀번호(Secrets Manager, 009) | 소유자. 마이그레이션·초기 적재(사람, 베스천 터널) |
| `tms_loader` | IAM 인증(`rds_iam`) | `obs`·`ops` 읽기·쓰기, `ref` 읽기, `ref.stack` 추가(새 키만) |
| `tms_app` | IAM 인증(`rds_iam`) | `ref`·`obs` 읽기, `app` 읽기·쓰기·표 생성, `rag` 읽기·쓰기(문서 색인은 D가 채움) |

팀원 계정(009 `db_user_names`)은 그대로 둔다.

## 8. 상태 흐름 (한 칸)

```
(없음) ─recent─▶ 상태 행(value null, status 3 미수신)
       ─recent(나중 스냅샷에 정정이 옴, 며칠 뒤여도)─▶ 정상 행(value 45.2, status 0)
       ─recent(같은 값이 반복해서 옴)─▶ 그대로(loaded_at 유지)
       ─daily─▶ 관측 행은 건드리지 않음. 그 날짜 요약만 다시 계산
       ─backfill(그 날짜)─▶ 같은 규칙으로 덮어씀. 같으면 그대로
```
