# Contract: 대시보드 관측 적재 인터페이스

## 1. 상태 머신 `tms-dashboard-load` 입력

Scheduler와 사람(`run_dashboard_load.py`)이 같은 모양으로 시작한다.

```json
{"mode": "recent"}                                   // 30분 경로 (스케줄 :15, :45)
{"mode": "daily"}                                    // 매일 경로 (스케줄 03:20) = RDS 안에서 일일 요약 + 매핑 점검 (S3 안 읽음)
{"mode": "day", "date": "2026-11-12"}                // 다시 채우기: 그 KST 날짜 1일 (사람, 날짜마다 1번)
{"mode": "recent", "hours": 6}                       // 범위를 늘린 30분 경로 (사람, 장애 뒤)
```

| 키 | 값 | 기본 |
|---|---|---|
| `mode` | `recent` / `daily` / `day` | 필수 |
| `hours` | `recent`의 수집 시각 범위(시간) | 4 |
| `date` | `day`의 KST 날짜 | `day`에서 필수 |
| `notify` | false면 매핑 알림을 보내지 않음(시험용) | true |

## 2. 상태 머신 단계

```
CheckDb   rds:describeDBInstances(DBInstanceIdentifier="tms-db")
          ├─ DBInstanceNotFound → Skipped (Succeed, output {"skipped":"rds_off"})
          └─ 상태가 available 아님 → Skipped (Succeed, {"skipped":"rds_<상태>"})
Load      lambda:invoke tms-dashboard-load, payload = 입력 + {"db_host": <Endpoint.Address>, "db_port": <Endpoint.Port>}
          재시도: Lambda.TooManyRequestsException·ServiceException 30초 간격 2회
Notify    (mode=daily, new_names 1개 이상, notify≠false) sns:publish 운영 토픽
          제목 "[tms] dashboard load: new facility names"
Catch     모든 오류 → sns:publish 운영 토픽 "[tms] dashboard load failed" (실행 이름·mode·오류 첫 줄) → Fail
```

## 3. Lambda 응답

```json
{
  "mode": "recent",
  "run_id": "20261119T011500Z-recent",
  "source": {"prefix": "tms_cleansys/", "snapshots": 24, "ingest_from": "...", "ingest_to": "..."},
  "measured_range": {"min": "2026-11-19 06:30", "max": "2026-11-19 10:00"},
  "rows": {"read": 7480, "upserted": 3790, "unchanged": 3690},
  "new_stack_keys": 0,
  "summary_days": [],
  "new_names": [],
  "elapsed_s": 18.4
}
```

- `daily`는 `rows.read`·`upserted`가 0이고(관측을 쓰지 않음), `summary_days`에 다시 계산한 날짜(최근 2일 + 직전 `daily` 이후 관측이 바뀐 날짜)를, `new_names`에 처음 본 (지역, 사업장)을 넣는다.
- `day`는 그 날짜를 원본에서 UPSERT하고 그 날짜 요약을 다시 계산한다.
- `recent`·`day`의 `new_stack_keys`는 `ref.stack`에 자동 추가한 굴뚝 수다(메일 없음).
- 같은 내용이 `ops.load_run`에 한 행으로 남는다.

## 4. 사람이 실행하는 명령 (`services/dashboard-load/run_dashboard_load.py`)

| 명령 | 하는 일 | 접속 |
|---|---|---|
| `migrate [--dry-run]` | `migrations/*.sql`을 번호 순서로, 적용 안 된 것만 적용 | 베스천 터널 `localhost:5433`, `tms_admin` |
| `load-ref --sites <s3://… 또는 로컬 CSV> [--dry-run]` | 사업장 목록 → `ref.site`·`ref.site_name_map`·`ref.stack`(`source=site_list`). 같은 파일로 다시 실행해도 결과가 같다 | 같음 |
| `backfill --from 2026-10-30 --to 2026-11-19 [--dry-run]` | 날짜마다 상태 머신을 `{"mode":"day","date":…}`로 실행하고 결과 표를 출력. 이미 성공한 날도 다시 돌려도 결과가 같다 | AWS API(본인 IAM) |
| `status` | 최근 `ops.load_run` 10건과 날짜별 행 수 | 베스천 터널 |

### 사업장 목록 CSV (D에게 요청할 최소 컬럼)

`site_id`, `area_nm`, `fact_manage_nm`, `display_name`, `region_sigungu`, `address`, `lat`, `lon`, `coordinate_source`, `stack_code`, `frontend_stack_id`, `mapping_status`(`auto`/`confirmed`/`unobserved`).
한 줄 = 굴뚝 하나. 사업장 정보는 같은 `site_id`끼리 같아야 한다(다르면 `load-ref`가 거부).

## 5. 오류와 알림

| 상황 | 결과 |
|---|---|
| RDS 없음·정지 | Skipped(성공). 알림 없음, 실행 기록에 남음 |
| 원본 읽기·변환 실패 | Lambda 실패 → Catch → 운영 메일 |
| Silver에 없는 상태 문자열 | 실패(계약 위반) → 운영 메일 |
| DB 접속·쓰기 실패 | 실패 → 운영 메일. 같은 입력으로 다시 실행하면 된다(멱등) |
| 새 사업장 이름 | 성공 + 처음 본 이름만 운영 메일 1통 |
