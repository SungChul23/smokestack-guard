# Quickstart: TW CEMS ML-ready Spark 검증

실행 주체:
- AI 에이전트: 로컬 테스트, `terraform fmt`/`validate`
- 사람(A): `terraform plan`/`apply`, Glue 실행, Athena 조회

## 0. 사전 조건

- 004 완료: `silver/tw_cems/` 36개월, `tms-silver` 스택 적용됨
- C의 정답지가 `s3://smokestack-cems-local-eda-952900391026/ml_ready/part.parquet`에 있음
- 로컬: Python 3.11 + Java 17 (`services/tms-silver` dev 의존성)

## 1. 로컬 테스트 (에이전트)

```bash
cd services/tms-silver
pytest -q tests/test_ml_ready_spark.py tests/test_glue_tw_cems_ml_ready.py tests/test_run_ml_ready.py
```

기대 결과:
- 공백·월 경계·진입 사례가 담긴 가짜 Silver에서 Spark 결과와 pandas `to_ml_ready` 결과가 35컬럼 모두 같다(SC-003).
- 같은 fixture에 "행 기준 `lag()`" 구현을 돌리면 결과가 **다르다**. fixture가 공백을 실제로 담고 있다는 확인이다.
- 출력 파일 수가 `--files`와 같고, 파일별 `measured_at` 범위가 겹치지 않는다.
- build가 실패하면 `latest.json`이 없다.

## 2. 인프라 (사람)

```powershell
cd infra\stacks\tms-silver
terraform plan    # 생성: 역할·정책·Job·카탈로그 테이블·스크립트 2개. 기존 004 리소스 변경 0
terraform apply
```

## 3. 생성 (사람)

```bash
cd services/tms-silver
uv run --python 3.11 --with boto3 python run_ml_ready.py --mode build
aws s3 cp s3://smokestack-tms-raw-952900391026/silver/_runs/tw_cems_ml_ready/latest.json -
aws s3 ls s3://smokestack-tms-raw-952900391026/silver/tw_cems_ml_ready/ --summarize --human-readable
```

기대 결과:
- `SUCCEEDED`
- `silver_rows` = 80,359,440
- `output_rows` = 17,643,361
- `duplicate_keys` = 0
- 파일 6개, 각 128~256MB

## 4. 정답지 비교 (사람, SC-002)

```bash
uv run --python 3.11 --with boto3 python run_ml_ready.py --mode compare
```

기대 결과:
- `passed: true`
- `only_ours = only_theirs = 0`
- 모든 컬럼 불일치가 0
- build 기록의 `eligible_positive_rows`가 133,726
- `max_abs_diff.ratio_rolling_std_3h`가 1e-5 미만

불일치가 있으면 `compare/<run_ts>.json`의 `column_mismatches`와 `mismatch_samples`로 어느 컬럼, 어느 키인지 확인한다.

## 5. 다시 생성 (사람, SC-004)

3을 한 번 더 실행해 `latest.json`의 건수가 모두 같은지 확인한다.

## 6. 조회 (사람, Athena `tms-eda`)

```sql
SELECT count(*) AS n,
       count_if(classification_eligible) AS eligible,
       count_if(classification_eligible AND label_entry_60m = 1) AS positives
FROM tms_silver.tw_cems_ml_ready;

-- 2023-11 공백 직후: 12-01 06:30~08:30은 feature_valid = false, 09:00부터 true
SELECT stack_code, item_code, measured_at, ratio_lag_30m, feature_valid
FROM tms_silver.tw_cems_ml_ready
WHERE measured_at BETWEEN TIMESTAMP '2023-12-01 06:30:00' AND TIMESTAMP '2023-12-01 09:30:00'
ORDER BY stack_code, item_code, measured_at
LIMIT 20;
```

기대 결과:
- 첫 쿼리 값이 실행 기록과 같다(SC-006).
- 두 번째 쿼리에서 06:30의 `ratio_lag_30m`이 null이다(11-27 값을 가져오지 않음).
