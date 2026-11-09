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
