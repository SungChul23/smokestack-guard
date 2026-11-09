# Data Model: TW CEMS ML-ready Spark 이식

컬럼의 **의미**는 `src/smokestack_guard/silver/ml_ready.py`와 `specs/c-contract/201-tw-cems-silver/spec.md` FR-011~015가 정한다. 이 문서는 입력·출력 위치, 타입, 실행 기록만 정한다.

## 1. 입력: tw_cems (Silver, 읽기만)

- 위치: `s3://smokestack-tms-raw-952900391026/silver/tw_cems/` (36개 월 파티션, 80,359,440행)
- 읽는 컬럼: `stack_code`, `item`, `unit`, `status`, `value`, `limit`, `ratio`, `ts_local`
- 대상 선택: `status = 'ok'` and `item in ('nox','sox')` and `unit = 'ppm'` → 약 1,769만 행

## 2. 출력: tw_cems_ml_ready

- 위치: `s3://smokestack-tms-raw-952900391026/silver/tw_cems_ml_ready/part-*.parquet` (파티션 없음)
- 카탈로그: `tms_silver.tw_cems_ml_ready` (파티션 없음, Athena·Spark 모두 경로로 읽음)
- 행 단위: `stack_code` × `item_code` × `measured_at`
- 정렬: 파일마다 연속된 `measured_at` 구간. 파일 안에서는 `measured_at`, `stack_code`, `item_code` 순서
- 파일: `--files`개(기본 6, 4~8 권장), 파일당 128~256MB 목표
- 타임스탬프: Parquet `TIMESTAMP_MICROS`, 벽시계 값(대만 현지)

| # | 컬럼 | 타입 | 출처 |
|---|---|---|---|
| 1 | `stack_code` | string | Silver `stack_code` |
| 2 | `item_code` | string | Silver `item` (`nox`, `sox`) |
| 3 | `measured_at` | timestamp | Silver `ts_local` |
| 4 | `ratio_pct` | double | `ratio × 100` |
| 5 | `headroom_pct` | double | `90 − ratio_pct` |
| 6 | `measure_value` | double | Silver `value` |
| 7 | `standard_value` | double | Silver `limit` |
| 8–12 | `ratio_lag_30m` … `ratio_lag_150m` | double | 정확히 30·60·90·120·150분 전 슬롯 |
| 13 | `ratio_diff_30m` | double | |
| 14 | `ratio_diff_60m` | double | |
| 15 | `ratio_rolling_mean_1h` | double | 2슬롯 모두 있을 때 |
| 16–18 | `ratio_rolling_mean_3h`, `_std_3h`, `_max_3h` | double | 6슬롯 모두 있을 때, std는 표본 |
| 19 | `ratio_range_3h` | double | |
| 20 | `ratio_slope_3h` | double | |
| 21 | `rise_count_3h` | double | |
| 22 | `ratio_acceleration` | double | |
| 23–26 | `hour_sin`, `hour_cos`, `month_sin`, `month_cos` | double | `measured_at`의 시·월 |
| 27 | `day_of_week` | double | 월=0 … 일=6 |
| 28 | `label_entry_60m` | double | 1.0 / 0.0 / null |
| 29 | `label_ratio_60m` | double | 정확히 60분 뒤 슬롯 |
| 30 | `feature_valid` | boolean | |
| 31 | `classification_eligible` | boolean | |
| 32 | `regression_eligible` | boolean | |
| 33–35 | `feature_version`, `label_version`, `quality_policy_version` | string | `ml_ready.py` 상수 (`v1`) |

컬럼 순서와 이름은 `ml_ready.COLUMNS`와 같아야 한다. 계산 규칙은 [research.md](research.md) R2에 있다.

## 3. 정답지: pandas ML-ready (읽기만)

- 위치: `s3://smokestack-cems-local-eda-952900391026/ml_ready/part.parquet` (924MB, C 업로드)
- 키: (`stack_code`, `item_code`, `measured_at`)
- `measured_at`이 ns 정수로 읽히면 마이크로초 timestamp로 바꿔 비교한다(R6).

## 4. 실행 기록

위치: `s3://smokestack-tms-raw-952900391026/silver/_runs/tw_cems_ml_ready/`

| 파일 | 언제 | 내용 |
|---|---|---|
| `runs/<run_ts>.json` | build 성공 뒤 | 아래 필드 |
| `latest.json` | build 시작 때 **삭제**, 성공 뒤 같은 내용으로 씀 | 없으면 마지막 build가 실패했거나 진행 중 |
| `compare/<run_ts>.json` | compare 끝 | 비교 결과 |

**build 기록 필드**

| 필드 | 의미 |
|---|---|
| `run_ts`, `job_run_id`, `mode` | 실행 정보 (`mode = build`) |
| `source`, `output` | 입력·출력 경로 |
| `silver_months` | 읽은 Silver 월 목록 (`YYYY-MM`) |
| `silver_rows` | Silver 입력 행 수 |
| `selected_rows` | 대상 선택 뒤 행 수 |
| `duplicate_keys` | 같은 키 중복 건수 (기대값 0) |
| `output_rows` | 출력 행 수 |
| `feature_valid_rows`, `classification_eligible_rows`, `regression_eligible_rows` | 각 플래그가 true인 행 수 |
| `positive_rows` | `label_entry_60m = 1` 행 수 |
| `eligible_positive_rows` | `classification_eligible and label_entry_60m = 1` 행 수 (C의 기록 135,978과 비교) |
| `by_item` | 위 건수의 `nox`/`sox`별 값 |
| `files` | 출력 파일 수 |
| `package_md5`, `versions` | 코드·런타임 버전 |
| `started_at`, `finished_at` | UTC ISO 8601 |

**compare 기록 필드**

| 필드 | 의미 |
|---|---|
| `ours_rows`, `theirs_rows` | 두 결과의 행 수 |
| `only_ours`, `only_theirs` | 한쪽에만 있는 키 수 |
| `column_mismatches` | 컬럼별 불일치 행 수 (35개 키, 키 컬럼 제외 32개) |
| `mismatch_samples` | 컬럼별 최대 5개 키 (값은 남기지 않음) |
| `tolerance` | `abs 1e-9, rel 1e-9` |
| `theirs_measured_at_type` | 정답지 `measured_at`의 원래 Parquet 타입 |
| `passed` | `only_* = 0`이고 모든 컬럼 불일치가 0 |

## 5. 상태

```
build 시작 ── latest.json 삭제 ── 계산 ── 쓰기 성공 ── runs/<ts>.json + latest.json
     └────────── 실패 ──▶ latest.json 없음 (= 실패 또는 진행 중)
```
