# 계약: 실행 인터페이스 (ML-ready Glue Job, 실행 명령)

## 1. Glue Job `tms-silver-tw-cems-ml-ready`

- 스크립트: `services/tms-silver/glue_tw_cems_ml_ready.py` → `s3://smokestack-tms-raw-952900391026/ops/glue-scripts/glue_tw_cems_ml_ready.py`
- `--extra-py-files`
  - `ops/glue-packages/smokestack_guard.zip` (004와 같은 zip)
  - `ops/glue-scripts/ml_ready_spark.py`
- Glue 5.0, G.1X 10, 제한 시간 60분, 재시도 0, 동시 실행 1

| 인자 | 기본값 | 뜻 |
|---|---|---|
| `--mode` | `build` | `build`(ML-ready 생성) 또는 `compare`(정답지와 비교) |
| `--bucket` | `smokestack-tms-raw-952900391026` | 입력·출력 버킷 |
| `--source_prefix` | `silver/tw_cems` | Silver 경로 |
| `--table_prefix` | `silver/tw_cems_ml_ready` | 출력 경로 |
| `--runs_prefix` | `silver/_runs/tw_cems_ml_ready` | 실행 기록 경로 |
| `--files` | `6` | 출력 파일 수 (1~32) |
| `--reference` | `s3://smokestack-cems-local-eda-952900391026/ml_ready/part.parquet` | `compare`의 정답지 |
| `--package_md5` | Terraform이 넣는 zip MD5 | 실행 기록용 |
| `--local`, `--source_path`, `--output_path`, `--runs_path`, `--reference_path` | (로컬 테스트) | 로컬 Spark 실행 |

### build 순서
1. `runs_prefix/latest.json`을 삭제한다.
2. `source_prefix`를 경로로 읽는다(카탈로그 아님). Silver 월 목록과 행 수를 센다.
3. `normalize` → 중복 키를 세고 제거한다 → `add_features` (research R1·R2·R3).
4. `repartitionByRange(files, measured_at)` → `sortWithinPartitions` → 전체 덮어쓰기.
5. 건수를 집계하고 `runs/<run_ts>.json`, `latest.json`을 쓴다.

**실패 조건**
- 입력 0행: `empty silver input`
- 대상 선택 뒤 0행: `no ml-ready target rows`
- 출력 컬럼이 `ml_ready.COLUMNS`와 다름: `column contract mismatch`

### compare 순서
1. 출력(`table_prefix`)과 `reference`를 읽는다. 정답지 `measured_at`이 정수(ns)면 timestamp로 바꾼다.
2. 키로 full outer join → 한쪽에만 있는 키 수, 컬럼별 불일치 수(허용 오차 abs 1e-9 + rel 1e-9, null = null)를 계산한다.
3. `runs_prefix/compare/<run_ts>.json`을 쓴다. 불일치가 있어도 Job은 성공으로 끝나고, `passed: false`로 남긴다.

**로그**: 경로, 건수, 버전, 소요 시간만 남긴다. 피처·라벨 값은 남기지 않는다.

## 2. 실행 명령 `services/tms-silver/run_ml_ready.py`

```
python run_ml_ready.py [--mode build|compare] [--files N] [--profile NAME] [--region ap-northeast-2]
```

1. Job을 시작하고 30초마다 상태를 확인한다. 자동 재시도는 하지 않는다. 1회 실행이고 덮어쓰기라 사람이 판단한다.
2. 끝나면 출력한다.
   - 상태, 실행 시간, DPU초, 추정 비용
   - build: `latest.json`의 건수
   - compare: `compare/<run_ts>.json`의 `passed`와 컬럼별 불일치 수
3. 종료 코드
   - 0: 성공(compare는 `passed: true`)
   - 1: 실패 또는 `passed: false`
   - 2: 인자 오류
