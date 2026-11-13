# tms-silver

대만 CEMS 원본 월 파일(`bronze/tw_cems/historical/YYYY-MM.jsonl`)을 Glue 5.0에서 Silver(`silver/tw_cems/`)로 변환한다.
규칙은 C의 `src/smokestack_guard/silver/tw_cems_spark.py`를 수정 없이 쓴다.

- spec·plan: [`specs/a-platform/004-tw-cems-silver-glue/`](../../specs/a-platform/004-tw-cems-silver-glue/)
- 인프라: [`infra/stacks/tms-silver/`](../../infra/stacks/tms-silver/)

| 파일 | 하는 일 |
|---|---|
| `glue_tw_cems_silver.py` | Glue 진입 스크립트(로컬 겸용). 한 달을 변환하고, 다른 달 행·0행이면 쓰기 전에 실패한다. 실행 기록을 남긴다 |
| `run_silver.py` | 사람이 실행하는 일괄 실행 명령. 월별 Job 시작, 1회 재시도, 결과·비용 표 |

## 로컬 테스트

Python 3.11, Java 17이 필요하다(Glue 5.0과 같은 Spark 3.5.4).

```bash
cd services/tms-silver
python3.11 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest -q
```

CI는 `.github/workflows/tms-silver.yml`에서 같은 순서로 돈다. C의 규칙 코드(`src/smokestack_guard/silver/`)가 바뀌어도 실행된다.

## 실행 (사람)

자격증명은 각자 환경 변수나 `--profile`에서 읽는다.

```bash
python run_silver.py --from 2025-10 --to 2025-10 --dry-run   # 대상과 실행 기록 유무 확인
python run_silver.py --from 2025-10 --to 2025-10             # 한 달 시험
python run_silver.py --dry-run                               # 36개월(2023-11~2026-10) 확인
python run_silver.py --only-missing                          # 실행 기록이 없는 월만
```

- 실행 기록: `s3://smokestack-tms-raw-952900391026/silver/_runs/tw_cems/YYYY-MM.json` (행 수, `status`별 건수, 패키지 MD5, 런타임 버전)
- 조회: Athena 워크그룹 `tms-eda`에서 `tms_silver.tw_cems`. Spark는 `s3://smokestack-tms-raw-952900391026/silver/tw_cems/`를 직접 읽는다.

## 첫 실행에서 확인할 것

- 실행 기록의 `versions.pandas`가 `missing`이 아니다. `tw_cems.py` import용으로만 필요하다. `missing`이면 Job 인자에 `--additional-python-modules pandas`를 추가한다.
- 로그에 `ListBucket` `AccessDenied`가 없다. 거부되면 로그에 찍힌 접두어만 역할 정책의 `ListRawScoped`에 추가한다. 쓰기 권한은 넓히지 않는다.

## ML-ready (005)

Silver(`silver/tw_cems/`) 36개월 전체를 읽어 학습용 35컬럼 ML-ready(`silver/tw_cems_ml_ready/`)를 만든다.
- 규칙의 기준은 C의 `src/smokestack_guard/silver/ml_ready.py`(pandas)다. Spark 구현은 `ml_ready_spark.py`이고, 상수는 그 모듈에서 가져온다.
- 빈 슬롯을 건너뛰지 않도록 `lag()` 대신 30분 슬롯 번호 위의 범위 윈도우(`rangeBetween`)로 계산한다.
- spec·plan: [`specs/a-platform/005-tw-cems-ml-ready-spark/`](../../specs/a-platform/005-tw-cems-ml-ready-spark/)

| 파일 | 하는 일 |
|---|---|
| `ml_ready_spark.py` | 규칙(정규화, 피처, 라벨), 정답지 읽기, 결과 비교 |
| `glue_tw_cems_ml_ready.py` | Glue 진입 스크립트. `--mode build`(생성) / `--mode compare`(정답지와 35컬럼 비교) |
| `run_ml_ready.py` | 사람이 실행하는 명령. 1회 실행 후 실행 기록·비용 출력. 자동 재시도 없음 |

테스트(`tests/test_ml_ready_spark.py`)는 같은 가짜 Silver에 pandas `to_ml_ready`를 돌린 결과와 35컬럼을 비교한다. C의 `ml_ready.py`가 바뀌면 CI에서 차이를 잡는다.

```bash
python run_ml_ready.py --mode build      # 생성 (기본 파일 6개)
python run_ml_ready.py --mode compare    # C의 pandas 결과와 비교, passed가 아니면 종료 코드 1
```

- **읽기 전에 확인:** `s3://smokestack-tms-raw-952900391026/silver/_runs/tw_cems_ml_ready/latest.json`이 있어야 한다. build는 시작할 때 이 파일을 지우고 성공한 뒤에만 쓴다. 없으면 마지막 build가 실패했거나 진행 중이다.
- 출력은 파티션이 없다. 파일마다 연속된 `measured_at` 구간이 들어 있어, 기간으로 걸러 읽으면 해당 파일만 읽는다.
- 로컬 테스트는 시간대를 UTC로 고정한다(`tests/conftest.py`). PySpark가 시간대 없는 `datetime`을 PC의 로컬 시간대(KST)로 해석하기 때문이다.

## 재수집 원본: silver2 (006) — TW CEMS 공식

**학습·분석은 `tms_silver2.tw_cems`, `tms_silver2.tw_cems_ml_ready`를 쓴다.** 위의 `silver/tw_cems*`(004·005)는 중복 결함이 있는 옛 원본 기준이라 쓰지 않는다(정리 전까지 보존).

C가 다시 받은 원본(`bronze2/tw_cems/YYYY-MM.jsonl`)을 **같은 규칙**으로 `silver2/`에 만들어 기존 `silver/`와 비교한다. 기존 `silver/`는 그대로 둔다.
- 기존 원본은 줄 수는 같지만 달마다 1.3~3.8%가 중복 줄이었고, 새 원본에서는 그 자리에 실제 측정값이 들어 있다(약 340만 줄).
- Job·역할·카탈로그는 `infra/stacks/tms-silver/silver2.tf`에 따로 있다. 스크립트와 패키지는 기존 Job과 같은 파일을 쓴다.
- spec·plan: [`specs/a-platform/006-tw-cems-silver2-compare/`](../../specs/a-platform/006-tw-cems-silver2-compare/)

```bash
# Silver2: bronze2/tw_cems → silver2/tw_cems (36개월)
python run_silver.py --job-name tms-silver2-tw-cems --raw-prefix bronze2/tw_cems --runs-prefix silver2/_runs/tw_cems --dry-run
python run_silver.py --job-name tms-silver2-tw-cems --raw-prefix bronze2/tw_cems --runs-prefix silver2/_runs/tw_cems

# ML-ready2: silver2/tw_cems → silver2/tw_cems_ml_ready
python run_ml_ready.py --mode build --job-name tms-silver2-tw-cems-ml-ready --runs-prefix silver2/_runs/tw_cems_ml_ready
python run_ml_ready.py --mode compare --job-name tms-silver2-tw-cems-ml-ready --runs-prefix silver2/_runs/tw_cems_ml_ready
```

- 조회: Athena `tms_silver2.tw_cems`, `tms_silver2.tw_cems_ml_ready` (워크그룹 `tms-eda`)
- compare 정답지: C가 같은 bronze2로 만든 pandas 결과 `s3://smokestack-cems-local-eda-952900391026/tw_cems_ml_ready_fixed/part.parquet` (변수 `silver2_ml_ready_reference`)

## K-TMS Silver·ML-ready (008) — Iceberg, 매일 갱신

K-TMS 수집 원본(`tms_cleansys/`, `_SUCCESS` 있는 폴더)을 매일 03:00 KST에 끝난 최근 2일만 다시 계산해 Iceberg 테이블 두 개를 갱신한다.

```
EventBridge Scheduler(03:00 KST) → Step Functions tms-silver2-ktms
   ├─ Glue tms-silver2-ktms           tms_cleansys/ → tms_silver2.ktms           (9컬럼, KST 측정일 파티션)
   └─ Glue tms-silver2-ktms-ml-ready  tms_silver2.ktms → tms_silver2.ktms_ml_ready (35컬럼 = tw_cems_ml_ready)
   실패: 단계마다 재시도 1회 → SNS tms-collector-alerts
```

- 계산은 C의 `src/smokestack_guard/silver/ktms.py`, `ml_ready.py`를 수정 없이 driver의 pandas로 부른다. Spark는 Iceberg 읽기·쓰기에만 쓴다.
- spec·plan: [`specs/a-platform/008-ktms-silver-pipeline/`](../../specs/a-platform/008-ktms-silver-pipeline/), 인프라: `infra/stacks/tms-silver/ktms.tf`

| 파일 | 하는 일 |
|---|---|
| `ktms_pipeline.py` | 공통: 처리 범위(`auto` = 끝난 최근 2일), 원본·ML-ready 입력 범위, 테이블 DDL, 범위 교체 쓰기, 실행 기록 |
| `glue_ktms_silver.py` | Silver 잡. 원본 0행·결과 0행이면 쓰기 전에 실패. 한 번에 최대 7일 |
| `glue_ktms_ml_ready.py` | ML-ready 잡. Silver를 대상 날짜 앞 150분 ~ 뒤 60분까지 읽어 계산하고 대상 날짜만 쓴다 |
| `run_ktms.py` | 사람이 실행: `backfill`(처음 전체 생성), `rerun`(범위 지정), `runs`(실행 기록 표) |

테스트: Iceberg 테스트는 jar를 붙인 Spark 세션이 따로 필요해서 두 번 나눠 돌린다.

```bash
pytest -q -m "not iceberg"   # 단위 (범위 계산, ML-ready 앞뒤 범위 = 전체 계산, 상태 머신 정의, run_ktms)
pytest -q -m iceberg         # Iceberg 통합 (처음 한 번 Maven에서 iceberg-spark-runtime 1.7.1을 받는다)
```

실행 (사람, WSL):

```bash
python run_ktms.py backfill --from 2026-10-30 --to 2026-11-12 --dry-run   # Silver 5일 묶음 → ML-ready 전체
python run_ktms.py backfill --from 2026-10-30 --to 2026-11-12
python run_ktms.py rerun --from 2026-11-05 --to 2026-11-07 [--stage all|silver|ml_ready]
python run_ktms.py runs --table ktms --last 5
```

- 매일 스케줄은 전체 생성(10-30 ~ 11-12)과 PR #45 수치 비교를 마친 뒤 켰다(2026-11-13, `ktms_schedule_enabled` 기본값 true). 잠시 멈추려면 `TF_VAR_ktms_schedule_enabled=false`로 apply한다.
- 실행 기록: `silver2/_runs/ktms/`, `silver2/_runs/ktms_ml_ready/` (`<시작 UTC>_<job_run_id>.json`, 실패한 시도도 남는다)

**읽기 (E·D):** S3의 Parquet 파일을 직접 읽지 않는다. 지난 버전 파일이 함께 있어 행이 중복된다. 카탈로그로 읽고, 학습에 쓴 버전은 `snapshot_id`로 기록한다.

```sql
SELECT * FROM tms_silver2.ktms_ml_ready WHERE classification_eligible;            -- 최신본 (워크그룹 tms-eda)
SELECT snapshot_id, committed_at FROM "tms_silver2"."ktms_ml_ready$snapshots";   -- 버전 목록
SELECT * FROM tms_silver2.ktms_ml_ready FOR VERSION AS OF <snapshot_id>;          -- 그 버전 그대로
```

자세한 읽는 법: [`contracts/ktms-tables.md`](../../specs/a-platform/008-ktms-silver-pipeline/contracts/ktms-tables.md)
