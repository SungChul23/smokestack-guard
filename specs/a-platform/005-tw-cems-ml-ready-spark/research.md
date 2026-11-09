# Research: TW CEMS ML-ready Spark 이식

결정 → 이유 → 검토한 대안 순서로 적는다. pandas 기준 구현은 `src/smokestack_guard/silver/ml_ready.py`(`to_ml_ready`)다.

## R1. pandas 의미를 Spark로 옮기는 방법: 슬롯 번호 + 범위 윈도우

- **결정**
  - 굴뚝·항목별 시계열에서 `slot = unix_timestamp(measured_at) / 1800`(정수)을 만든다.
  - `Window.partitionBy(stack_code, item_code).orderBy(slot)`에 **`rangeBetween`** 프레임을 쓴다. 빈 칸(격자)은 만들지 않는다.
- **이유**
  - pandas는 그룹마다 첫 관측~마지막 관측 사이를 30분 격자로 `reindex`하고 `shift`·`rolling`한 뒤, 관측된 행만 남긴다.
  - 슬롯 번호를 기준으로 범위 프레임을 쓰면 "정확히 k칸 전 슬롯"과 "최근 n칸 안의 관측 개수"를 격자 없이 같은 의미로 얻는다.
  - `lag()`는 "바로 앞 **행**"이라 빈 칸이 있으면 의미가 달라진다(spec FR-004).
- **대안**
  - 격자 생성 후 `lag`: 기각. 그룹마다 첫~마지막 사이 모든 슬롯 행을 만들어야 한다. 2023-11 같은 며칠짜리 공백이 많으면 행 수가 불필요하게 커진다.
  - 키 기준 자기 조인 7회(t−30…t−150, t+30, t+60): 기각. 셔플이 여러 번 생기고 코드가 길어진다.
  - `applyInPandas`로 pandas 함수를 그대로 실행: 운영 구현으로는 기각(이슈 #32 결정 1). 대신 **로컬 테스트의 정답지로** 쓴다(R5).

## R2. 컬럼별 계산 대응표

`r` = 현재 행의 `ratio_pct`, `v(k)` = 정확히 `slot + k` 슬롯의 `ratio_pct`(없으면 null).

| pandas | Spark (같은 의미) | 비고 |
|---|---|---|
| `r.shift(k)` (lag, k=1..5) | `first(r)` over `rangeBetween(-k, -k)` | 프레임이 비면 null |
| `r.diff()` = `r − r.shift(1)` | `r − v(−1)` | |
| `r − r.shift(2)` | `r − v(−2)` | |
| `d − d.shift(1)` | `(r − v(−1)) − (v(−1) − v(−2))` | 셋 중 하나라도 null이면 null |
| `rolling(2, min_periods=2).mean()` | `count over [−1,0] = 2`일 때 `avg` | |
| `rolling(6, min_periods=6)` mean/std/max/min | `count over [−5,0] = 6`일 때 `avg`/`stddev_samp`/`max`/`min` | std는 표본(ddof=1) |
| `ratio_range_3h` = max − min | 위 max − min | |
| `ratio_slope_3h` = Σ wⱼ·r.shift(j) / 17.5 | Σ wⱼ·v(−j) / 17.5, w = (2.5, 1.5, 0.5, −0.5, −1.5, −2.5) | 6개 중 하나라도 null이면 null |
| `rise_count_3h` | 5개 차이(r−v(−1), v(−1)−v(−2), …, v(−4)−v(−5))가 모두 있을 때 `>0` 개수 | double |
| `feature_valid` | `count over [−5,0] = 6` | 처음 5슬롯은 false |
| `label_ratio_60m` = `r.shift(−2)` | `v(+2)` | |
| `label_entry_60m` | `below = r < 90`, `reached = v(+1) ≥ 90 or v(+2) ≥ 90`, `known = reached or (v(+1), v(+2) 둘 다 있음)` → `below and known`이면 `reached ? 1.0 : 0.0`, 아니면 null | null 비교는 false로 다룬다 |
| `classification_eligible` | `feature_valid and label_entry_60m is not null` | |
| `regression_eligible` | `feature_valid and label_ratio_60m is not null and below` | |
| `hour`·`month` sin/cos | `hour(measured_at)`, `month(measured_at)` | 분은 쓰지 않는다(pandas와 같음) |
| `day_of_week` (월=0) | `weekday(measured_at)` (월=0) | Spark `dayofweek`는 일=1이라 쓰지 않는다 |
| `headroom_pct` | `90 − r` | |

- 상수(`ENTRY_PCT`, `WINDOW`, `LAGS`, `COLUMNS`, 버전)는 `ml_ready.py`에서 import한다.
- slope 분모 17.5와 가중치는 `WINDOW`로부터 같은 식으로 계산한다. 숫자를 하드코딩하지 않는다.
- **같은 시각 중복**: pandas는 정렬 뒤 `drop_duplicates("measured_at")`로 첫 행을 남긴다.
  - Spark는 (`stack_code`, `item_code`, `measured_at`) 중복 건수를 세어 실행 기록에 남긴다.
  - 남기는 행은 `ratio_pct`가 가장 작은 행으로 고정한다(결정적).
  - Silver 계약상 `ok`·`ppm`에는 중복이 없어야 하므로 0이 기대값이다. 0이 아니면 pandas와 다를 수 있음을 기록한다.

## R3. 입력 정규화 분리 (시나리오 B 대비)

- **결정**: `normalize(silver) -> DataFrame[stack_code, item_code, measured_at, ratio_pct, measure_value, standard_value]`를 피처 계산과 분리한다. #30의 `ml_ready.py` 규칙을 따른다.

  | 입력 | 고르기 | 시각 | `stack_code` |
  |---|---|---|---|
  | tw_cems (`ts_local` 있음) | `status = ok`, `item ∈ ML_ITEMS`, `unit = ppm` | `ts_local` | 그대로 |
  | ktms (`ts_local` 없음) | `status = ok`, `item ∈ ML_ITEMS` (`unit` 컬럼 없음) | `ts_kst` | `area_nm|fact_manage_nm|stack_code` |

- **이유**: 시나리오 B는 대만과 국내를 섞어 학습한다. 두 테이블의 피처가 같은 코드로 계산되어야 비교가 정직하다(원칙 V). 이 기능은 tw_cems만 실행하지만, ktms 분기는 단위 테스트로 형태만 확인한다.
- **주의**: #30이 머지되기 전 `main`의 `ml_ready.py`에는 ktms 분기가 없다. pandas와의 비교 테스트는 tw_cems 입력으로만 한다.

## R4. 출력: 파티션 없음 + 시간 범위 분할 + 정렬

- **결정**
  - `repartitionByRange(N, "measured_at")` → `sortWithinPartitions("measured_at", "stack_code", "item_code")` → `write.mode("overwrite").parquet`.
  - `N`은 `--files`(기본 6). 파일마다 연속된 시간 구간이 들어간다.
  - 타임스탬프는 `TIMESTAMP_MICROS`로 쓴다(`spark.sql.parquet.outputTimestampType`). pandas·pyarrow·Athena 모두 바로 읽는다.
- **이유**
  - spec FR-007(4~8개, 128~256MB, `measured_at` 정렬).
  - 파일과 row group의 `measured_at` 최소·최대가 겹치지 않아, 기간 조건(예: Validation 3개월)으로 읽을 때 해당 파일만 읽는다.
  - C의 pandas 결과가 924MB이므로 6개면 파일당 약 150MB다.
- **대안**: 전역 `orderBy` 후 `coalesce(N)`. 기각했다. `coalesce`는 정렬된 파티션을 임의로 합쳐 파일별 시간 범위가 섞일 수 있다.

## R5. 정답지 두 단계

| 단계 | 정답지 | 어디서 |
|---|---|---|
| ① 로컬 테스트 | 같은 가짜 Silver에 pandas `to_ml_ready`를 실행한 결과 | pytest (Spark 3.5.4) |
| ② 실데이터 | C의 결과 `s3://smokestack-cems-local-eda-952900391026/ml_ready/part.parquet` | 같은 Glue Job의 `compare` 모드 |

- **로컬 테스트 fixture**에 넣을 경우:
  - 며칠짜리 공백(2023-11-27 16:30 ~ 2023-12-01 06:30을 줄인 형태, Athena 확인)
  - 30분 한 칸 공백
  - 월 경계(9/30 23:30 → 10/1 00:00)
  - 90% 이상 진입·미진입·현재 90% 이상
  - +30만 있고 +60 없음
  - 시리즈 처음 5슬롯
- **민감도 확인**: 같은 fixture에 "행 기준 `lag()`" 구현을 돌려 결과가 **달라지는 것**도 테스트로 둔다. fixture가 공백 사례를 실제로 포함한다는 증거다(spec SC-003).
- **비교 허용 오차**
  - 실수는 `|a−b| ≤ 1e-9 + 1e-9·|b|`
  - null은 null끼리 같다
  - 이동 표준편차는 pandas(온라인 알고리즘)와 Spark(stddev_samp) 계산 순서가 달라 매우 작은 차이가 날 수 있다. 그래서 절대 오차 항을 둔다.

## R6. C의 결과 파일 읽기

- **확인할 것**: pandas가 쓴 `measured_at`이 `TIMESTAMP(NANOS)`이면 Spark 3.5는 기본 설정으로 읽지 못한다.
- **결정**
  - `compare` 모드는 `spark.sql.legacy.parquet.nanosAsLong=true`로 읽는다.
  - 컬럼이 long이면 `timestamp_micros(col / 1000)`으로 바꾼다. 이미 timestamp면 그대로 쓴다.
  - 첫 실행 로그에 원래 타입을 남긴다.
- **권한**: C의 버킷은 같은 계정(952900391026)이지만 Terraform 밖이다. 역할에 `ml_ready/*` 읽기와 `ListBucket`(prefix `ml_ready/`)만 준다.

## R7. 실패 시 "완료로 오인" 방지

- **문제**
  - 전체 덮어쓰기(`overwrite`)는 먼저 기존 파일을 지운다. 그래서 도중에 실패하면 결과가 비거나 일부만 남는다.
  - 이때 이전 실행의 기록이 남아 있으면 완료된 것처럼 보인다.
- **결정**
  - 실행 시작 시 `silver/_runs/tw_cems_ml_ready/latest.json`을 지운다.
  - 쓰기가 성공한 뒤 `runs/<run_ts>.json`과 `latest.json`을 쓴다.
  - **`latest.json`이 없으면 마지막 실행은 실패했거나 진행 중**이다. Athena나 학습에서 읽기 전에 이 파일로 확인한다.
- **대안**: 실행별 경로(`run=…/`)에 쓰고 카탈로그 위치를 바꾸는 방식. 기각했다. 1GB짜리 테이블을 1회 실행하는 데 비해 복잡하고, SageMaker 입력 경로가 매번 바뀐다.

## R8. 실행 단위와 자원

- 한 번 실행에 Silver 36개월 전체(8,036만 행)를 읽는다. 대상 선택 뒤 약 1,769만 행이 된다.
- 윈도우 그룹은 굴뚝×항목(수백 개)이고, 그룹당 최대 약 5만 행이다. 그룹이 작아 G.1X 10워커로 충분하다.
- Job 설정: `max_concurrent_runs = 1`, 제한 시간 60분, 재시도 0.
- 비용 추정
  - 실행 1회 5~10분 × 10 DPU ≈ 1~1.7 DPU시간, 약 $0.3~0.5($0.308 기준)
  - `compare` 실행도 비슷하다.
  - 첫 실행 뒤 실측으로 고친다.

## R9. 역할 분리

- **결정**: 새 역할 `tms-glue-silver-ml-ready`를 만든다. 004의 `tms-glue-silver`와 나눈다.
  - 읽기: `silver/tw_cems/*`, `ops/glue-*/*`, C의 버킷 `ml_ready/*`
  - 쓰기·삭제: `silver/tw_cems_ml_ready/*`, `silver/_runs/tw_cems_ml_ready/*`, `silver/tw_cems_ml_ready_$folder$`
  - 상위 표시 파일 `silver_$folder$`: 004에서 이미 생겼지만, 지워졌을 수 있으므로 Put·Get을 허용한다(Delete는 주지 않는다)
- **이유**: AGENTS.md S3 경로 규칙 5(역할마다 자기 테이블 경로에만 쓴다). Silver Job이 ML-ready를 지우거나, 그 반대가 되지 않게 한다.

## R10. 코드 배치

- `services/tms-silver/ml_ready_spark.py`: 규칙(정규화, 피처, 라벨). Glue에 `--extra-py-files`로 함께 올린다.
- `services/tms-silver/glue_tw_cems_ml_ready.py`: 진입 스크립트. `--mode build|compare`.
- `services/tms-silver/run_ml_ready.py`: 사람이 실행하는 명령. 시작 → 대기 → 실행 기록·비용 출력.
  - `run_silver.py`의 `estimate_cost`·`_log`를 import한다. 같은 폴더라 import할 수 있다.
- C의 `src/`는 수정하지 않는다. 상수만 import한다(spec FR-012, 2026-11-09 사용자 결정).
