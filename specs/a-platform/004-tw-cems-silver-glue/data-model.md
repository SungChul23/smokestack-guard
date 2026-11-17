# Data Model: TW CEMS Silver 클라우드 실행

이 기능은 새 데이터 의미를 만들지 않는다. Silver 행의 의미는 C의 계약(`specs/c-contract/201-tw-cems-silver/spec.md`)을 따른다. 아래는 저장 위치·타입·실행 기록만 정의한다.

## 1. 원본 월 파일 (입력, 읽기 전용)

| 항목 | 값 |
|---|---|
| 위치 | `s3://smokestack-tms-raw-952900391026/bronze/tw_cems/historical/YYYY-MM.jsonl` |
| 형식 | JSON Lines. 원본 키 15개 |
| Silver가 읽는 키 (10) | `cno`, `polno`, `item`, `unit`, `m_time`, `m_value`, `std`, `code2`, `abbr`, `epb_county` |
| 읽지 않는 키 (5) | `importdate`, `_id`, `code2desc`, `itemdesc`, `std_s` |
| 규칙 | 파일 월 = `m_time` 월. 2026-11-09 Athena 확인 결과 섞인 행 0건 |

## 2. tw_cems (Silver)

**위치**: `s3://smokestack-tms-raw-952900391026/silver/tw_cems/year=YYYY/month=MM/*.parquet`

**카탈로그**: `tms_silver.tw_cems`. 파티션 프로젝션을 쓰며, Athena 전용이다.

**경로 규칙**: `silver/<테이블>/`, 카탈로그 `tms_silver.<테이블>`. 상세는 [research.md](research.md) R10.

| 컬럼 | 타입 | 출처 |
|---|---|---|
| `area_nm` | string | 계약(K-TMS) |
| `fact_manage_nm` | string | 계약(K-TMS) |
| `stack_code` | string | 계약(K-TMS) |
| `item` | string | 계약(K-TMS) |
| `unit` | string | 대만 전용 |
| `value` | double | 계약(K-TMS) |
| `limit` | double | 계약(K-TMS). SQL 예약어라 Athena에서는 `"limit"`으로 쓴다 |
| `status` | string | 계약(K-TMS). `ok`, `not_monitored`, `other_code`, `partial`, `invalid` |
| `ts_kst` | timestamp | 계약(K-TMS). 한국 시각의 벽시계 값, 시간대 없음 |
| `ratio` | double | 계약(K-TMS). 1.0 = 100% |
| `ts_local` | timestamp | 대만 전용. 대만 시각의 벽시계 값 |
| `code2` | string | 대만 전용 |
| `flag_code_ratio_mismatch` | boolean | 대만 전용 |
| `year` | string (파티션) | `ts_local`의 연도 4자리 |
| `month` | string (파티션) | `ts_local`의 월 2자리 |

- **행 단위**: `stack_code` × `item` × `unit` × `ts_kst`(30분 슬롯)
- **교체 단위**: (`year`, `month`) 파티션 하나. 한 실행은 정확히 한 파티션만 쓴다.
- **검증 규칙**:
  - 한 실행 결과의 (`year`, `month`)는 입력 월 하나뿐이어야 한다. 아니면 쓰기 전에 실패한다.
  - 결과가 0행이면 실패한다.
- **타임스탬프**: Spark 세션 시간대를 UTC로 두고 벽시계 값을 그대로 저장한다. Athena에서 읽으면 같은 벽시계 값이 보인다.

## 3. 월 실행 기록

**위치**: `s3://smokestack-tms-raw-952900391026/silver/_runs/tw_cems/YYYY-MM.json`. 같은 월을 다시 실행하면 덮어쓴다.

데이터 쓰기가 성공한 **뒤에만** 쓴다. 그래서 기록이 있으면 그 월은 완료된 것이다.

| 필드 | 타입 | 의미 |
|---|---|---|
| `month` | string | `YYYY-MM` |
| `job_run_id` | string | Glue 실행 ID |
| `source` | string | 입력 S3 경로 |
| `output` | string | 출력 파티션 S3 경로 |
| `input_rows` | int | 원본 줄 수(손상 줄 포함) |
| `silver_rows` | int | Silver 행 수 |
| `status_rows` | object | `status`별 행 수. 5개 키 |
| `package_md5` | string | 실행한 `smokestack_guard` zip의 MD5 |
| `versions` | object | `spark`, `python`, `pandas`, `numpy` 버전 |
| `started_at`, `finished_at` | string | UTC ISO 8601 |

- **불변식**: `silver_rows == sum(status_rows.values())`
- **로그**: 같은 요약을 Glue 연속 로그(`/aws-glue/tms-silver`)에도 한 줄로 남긴다. 데이터 값은 남기지 않는다.

## 4. 월 실행 상태 (일괄 실행 명령)

```
PLANNED ──시작──▶ RUNNING ──성공──▶ SUCCEEDED (실행 기록 있음)
   │                 └──실패──▶ 재시도 1회 ──▶ SUCCEEDED | FAILED
   └── --only-missing이고 실행 기록 있음 ──▶ SKIPPED
```
