# Data Model: K-TMS Silver·ML-ready

컬럼의 **의미**는 C의 코드가 정한다(`ktms.to_silver`, `ml_ready.to_ml_ready`). 이 문서는 저장 형식과 이 파이프라인이 더하는 규칙만 적는다. 읽는 법은 [contracts/ktms-tables.md](contracts/ktms-tables.md)에 있다.

## 1. 원본 스냅샷 폴더 (입력, 읽기만)

- 경로: `tms_cleansys/ingest_date=YYYY-MM-DD/hour=HH/run_ts=YYYYMMDDTHHMMSSZ/` (UTC)
- 완성 판정: 같은 폴더에 `_SUCCESS`가 있음(007 계약). C의 `read_bronze`가 판정한다.
- 이 파이프라인이 정하는 것: 읽을 수집일 범위 `[start − 1, min(end + 1, 오늘 UTC)]` (research R6)

## 2. Silver: `tms_silver2.ktms`

| 항목 | 값 |
|---|---|
| 위치 | `s3://smokestack-tms-raw-952900391026/silver2/ktms/` (`data/`, `metadata/`) |
| 형식 | Iceberg v2, Parquet(zstd) |
| 파티션 | `days(ts_kst)` = KST 측정일 |
| 키(중복 없음) | `area_nm`, `fact_manage_nm`, `stack_code`, `ts_kst`, `item` |

컬럼은 `to_silver` 출력 순서와 같다(9개).

| # | 컬럼 | Iceberg 타입 | null | 의미 (C 규칙) |
|---|---|---|---|---|
| 1 | `area_nm` | string | 아니오 | 시도 |
| 2 | `fact_manage_nm` | string | 아니오 | 사업장 |
| 3 | `stack_code` | string | 아니오 | 굴뚝 번호. 사업장 안에서만 유일하다 |
| 4 | `item` | string | 아니오 | `nox`, `sox`, `tsp`, `hcl`, `co`, `nh3`, `hf` |
| 5 | `value` | double | 예 | 측정값. 문구이면 null |
| 6 | `limit` | double | 예 | 배출허용기준. SQL 예약어라 Athena에서는 `"limit"`으로 쓴다 |
| 7 | `status` | string | 아니오 | `ok`, `stopped`, `checking`, `no_signal`, `maintenance`, `inspection`, `other`, `not_monitored`, `ambiguous` |
| 8 | `ts_kst` | timestamp (시간대 없음) | 아니오 | 측정 시각, KST 벽시계, 30분 격자 |
| 9 | `ratio` | double | 예 | `value / limit` (`limit > 0`일 때만) |

규칙:
- 한 실행은 `ts_kst`가 `[start 00:00, end + 1일 00:00)`인 행을 통째로 교체한다.
- 진행 중인 오늘(KST)의 행은 없다.

## 3. ML-ready: `tms_silver2.ktms_ml_ready`

| 항목 | 값 |
|---|---|
| 위치 | `s3://smokestack-tms-raw-952900391026/silver2/ktms_ml_ready/` |
| 형식 | Iceberg v2, Parquet(zstd) |
| 파티션 | `days(measured_at)` = KST 날짜 |
| 키 | `stack_code`, `item_code`, `measured_at` |

- **컬럼**: `ml_ready.COLUMNS`를 그대로 따른다. 지금은 35개이고, 순서와 타입은 `tw_cems_ml_ready`와 같다(005 data-model §2, `infra/stacks/tms-silver/main.tf`의 `ml_ready_columns`).
  - C의 PR #48이 머지되면 맨 끝에 `data_source`(string)가 붙어 36개가 된다. K-TMS 실측은 `ktms`, 합성은 `ktms_synth`이고, 값 계산은 바뀌지 않는다.
  - 잡은 실행할 때마다 `COLUMNS`에 있고 테이블에 없는 컬럼을 끝에 추가한다(`ALTER TABLE ... ADD COLUMNS`). 추가 전 행의 새 컬럼은 null이므로 `rerun --stage ml_ready`로 다시 계산해 채운다.
  - `stack_code`, `item_code`: string
  - `measured_at`: timestamp(시간대 없음)
  - 피처, 라벨 26개: double
  - `feature_valid`, `classification_eligible`, `regression_eligible`: boolean
  - 버전 3개: string
- **K-TMS에서 다른 점**(C 규칙):
  - `stack_code`는 `area_nm|fact_manage_nm|stack_code`다.
  - `measured_at`은 KST 벽시계다.
  - 단위 컬럼이 없어 NOx·SOx를 ppm으로 본다.
- **학습 때 처리**(E): `month_sin`, `month_cos`는 드랍한다. 테이블에는 `COLUMNS` 전체를 그대로 둔다(tw_cems와 같은 구조).
- **규칙**:
  - 한 실행은 `measured_at`이 `[start, end + 1일)`인 행을 교체한다.
  - 계산 입력은 Silver `[start 00:00 − 150분, end + 1일 00:00 + 30분]`(양 끝 포함)이다. 마지막 칸 23:30의 60분 뒤가 다음날 00:30이기 때문이다.
  - 매일 실행 직후에는 `end`일 마지막 1시간의 라벨이 비어 있을 수 있다. 다음 날 실행에서 채워진다.

## 4. 합성 테이블 (예정, B 진행에 따라 바뀜)

- 이름: `tms_silver2.ktms_synthetic`, `tms_silver2.ktms_synthetic_ml_ready`
- 위치: `silver2/ktms_synthetic/`, `silver2/ktms_synthetic_ml_ready/`
- 구조는 2·3과 같다. **이번 기능에서는 만들지 않는다**(research R9).

## 5. 처리 범위

| 필드 | 값 |
|---|---|
| `start_date`, `end_date` | KST 측정일 `YYYY-MM-DD` 또는 `auto` |
| `auto` | `end = last_complete_day()`(C), `start = end − 1` |
| 검사 | `start ≤ end ≤ last_complete_day()` |
| 일수 제한 | Silver는 `end − start + 1 ≤ max_days`(기본 7). ML-ready는 제한이 없다 |

## 6. 실행 기록

- 경로: `silver2/_runs/<테이블>/<시작 UTC YYYYMMDDTHHMMSSZ>_<job_run_id>.json`
- 형식: JSON. 필드는 [contracts/run-interface.md](contracts/run-interface.md) §3에 있다.

상태 변화:

```
시작 ──(검사 실패·원본 0행·결과 0행)──▶ failed 기록, 테이블 그대로
  └──▶ 계산 ──▶ Iceberg 커밋 ──(커밋 실패)──▶ failed 기록, 테이블 그대로
                    └──▶ succeeded 기록(snapshot_id 포함)
```

성공한 실행 하나는 Iceberg 스냅샷 하나와 짝이다. 스냅샷 요약의 `job_run_id`로 둘을 잇는다.

## 7. 테이블 버전

- Iceberg `snapshot_id`(정수)가 버전 번호다. 성공한 실행마다 테이블당 1개씩 생긴다.
- 오래된 스냅샷 정리는 범위 밖이다. 정리하기 전까지는 모든 버전을 읽을 수 있다.
