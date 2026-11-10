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

## 재수집 원본 비교: silver2 (006)

C가 다시 받은 원본(`bronze2/tw_cems/YYYY-MM.jsonl`)을 **같은 규칙**으로 `silver2/`에 만들어 기존 `silver/`와 비교한다. 기존 `silver/`는 그대로 둔다.
- 기존 원본은 줄 수는 같지만 달마다 1.3~3.8%가 중복 줄이었고, 새 원본에서는 그 자리에 실제 측정값이 들어 있다(약 340만 줄).
- Job·역할·카탈로그는 `infra/stacks/tms-silver/silver2.tf`에 따로 있다. 스크립트와 패키지는 기존 Job과 같은 파일을 쓴다.
- spec·plan: [`specs/a-platform/006-tw-cems-silver2-compare/`](../../specs/a-platform/006-tw-cems-silver2-compare/)

```bash
# Silver2: bronze2/tw_cems → silver2/tw_cems (36개월)
python run_silver.py --job-name tms-silver2-tw-cems --raw-prefix bronze2/tw_cems --runs-prefix silver2/_runs/tw_cems --dry-run
python run_silver.py --job-name tms-silver2-tw-cems --raw-prefix bronze2/tw_cems --runs-prefix silver2/_runs/tw_cems

# ML-ready2: silver2/tw_cems → silver2/tw_cems_ml_ready (build 전용)
python run_ml_ready.py --mode build --job-name tms-silver2-tw-cems-ml-ready --runs-prefix silver2/_runs/tw_cems_ml_ready
```

- 조회: Athena `tms_silver2.tw_cems`, `tms_silver2.tw_cems_ml_ready` (워크그룹 `tms-eda`)
- ML-ready2의 compare는 아직 없다. 새 원본 기준 정답지(C의 pandas 결과)가 생기면 정답지 읽기 권한과 `--reference`를 추가한다.
