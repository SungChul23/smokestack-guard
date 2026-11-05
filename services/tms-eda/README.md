# tms-eda

TW CEMS 원본 월 파일(JSONL)을 한 번 Parquet으로 바꿔 Athena에서 조회할 수 있게 하는 Glue Job 스크립트와 백필 명령입니다.

- **Athena EDA 전용입니다. Silver·ML 파이프라인의 입력이 아닙니다.** Silver는 원본 JSONL을 직접 읽습니다.
- 포맷만 바꿉니다. 고정 스키마가 없고, 값은 원문 문자열 그대로 두며, 행을 거르지 않습니다.
- spec: `specs/a-platform/003-tw-cems-eda/` · 테이블 계약: `contracts/tw-cems-raw-parquet.md` · 실행 계약: `contracts/run-interface.md`

## 구성

```
사람: run_backfill.py ──start_job_run(--year, --month)──▶ Glue Job: tms-eda-tw-cems-parquet (6.0, G.1X × 10)
                                                               │ 읽기: s3://smokestack-tms-raw-952900391026/bronze/tw_cems/historical/YYYY-MM.jsonl
                                                               │ 쓰기: s3://smokestack-tms-eda-952900391026/tw_cems_raw/year=YYYY/month=MM/
                                                               ▼
사람: 크롤러 Run ──▶ Glue 크롤러: tms-eda-tw-cems-crawler ──▶ 테이블 tms_eda.tw_cems_raw
                                                               ▼
                                              Athena 워크그룹 tms-eda (쿼리당 10GB 한도)
```

| 항목 | 값 |
|---|---|
| 런타임 | Glue 6.0 (Spark 4.1.1, Python 3.13), 추가 패키지 없음 |
| Job 스크립트 | `tw_cems_parquet.py` → `s3://…-eda-…/glue-scripts/` (Terraform이 업로드) |
| 백필 명령 | `run_backfill.py` (사람이 자기 자격증명으로 실행) |
| 로그 | `/aws-glue/tms-eda` (연속 로그, 14일) |
| 인프라 코드 | `infra/stacks/tms-eda` |

| 파일 | 내용 |
|---|---|
| `tw_cems_parquet.py` | 월 파일 1개 → Parquet 2개 + `_SUCCESS`. Glue와 로컬(`--local`) 겸용 |
| `run_backfill.py` | 대상 월 찾기, 동시 실행, 재시도 1회, 결과 표·비용 추정, 크롤러 시작 |
| `tests/fixtures/*.jsonl` | **가짜 데이터.** 실제 원본 값이 아니며 키 이름과 형식만 흉내 냈습니다 |

## 로컬 준비 (WSL, 최초 1회)

PySpark 4는 Java 17 이상이 필요합니다.

```bash
sudo apt install -y openjdk-17-jdk-headless
java -version                    # 17.x
cd services/tms-eda
uv venv --python 3.13
uv pip install -e ".[dev]"       # 또는 uv sync --extra dev
source .venv/bin/activate
```

## 테스트와 로컬 실행

```bash
ruff check .
pytest -q
```

- `test_tw_cems_parquet.py`: 로컬 Spark로 가짜 샘플을 변환해 행 수, 키·값 보존, 손상 줄, 재실행, 대소문자 충돌을 확인합니다.
- `test_run_backfill.py`: boto3를 가짜 객체로 바꿔 월 파싱, `--dry-run`, 재시도, 동시 실행 수, 비용 계산을 확인합니다. AWS를 호출하지 않습니다.

```bash
python tw_cems_parquet.py --local --year 2025 --month 03 \
  --input_path tests/fixtures/synthetic_edge_cases.jsonl --output_path /tmp/tw_cems_raw
ls /tmp/tw_cems_raw/year=2025/month=03/    # part-*.parquet 2개 + _SUCCESS
```

## 백필 흐름

원본 업로드가 모두 끝난 뒤 실행합니다. 자격증명은 환경 변수나 `--profile`로 넘깁니다.

1. **업로드 완료 확인:** 원본 경로에 대상 월 파일이 모두 있는지 봅니다.
2. **대상 확인:** `python run_backfill.py --dry-run`
   - 대상 월이 24개(2024-11~2026-10)인지, "원본에 없는 월"이 비어 있는지 확인합니다.
   - 파일 크기와 마지막 수정 시각이 업로드 완료 상태인지 봅니다.
3. **실행:** `python run_backfill.py` (기본 동시 6개, 약 15분)
   - 30초마다 상태를 확인하고, 실패한 월은 1회만 다시 시작합니다.
   - 끝나면 `month | state | attempts | run_id | execution_s | dpu_s | est_usd` 표와 합계, 실패 목록을 출력합니다.
4. **빠진 월만 다시:** `python run_backfill.py --only-missing` (`_SUCCESS`가 있는 월은 `SKIPPED`)
5. **크롤러:** 콘솔 Glue → Crawlers → `tms-eda-tw-cems-crawler` → Run. 또는 `--only-missing --start-crawler`(실패한 월이 있으면 시작하지 않음)
6. **Athena**에서 조회합니다.

| 종료 코드 | 뜻 |
|---|---|
| 0 | 모두 성공 또는 SKIPPED (`--dry-run` 포함) |
| 1 | 실패한 월이 있음, 또는 크롤러 시작 실패 |
| 2 | 인자 오류 (`--concurrency`가 1~6이 아님, 월 형식 오류 등) |

## Athena 조회 요령

- 워크그룹은 **`tms-eda`** 를 고릅니다. 쿼리당 10GB를 넘으면 중단됩니다.
- **파티션 조건을 꼭 붙입니다.** 파티션은 문자열입니다: `WHERE year = '2025' AND month = '03'`
- 값은 모두 문자열입니다. 숫자 계산은 `try_cast(m_value AS double)`처럼 실패하면 NULL이 되는 변환을 씁니다.
- 컬럼 이름은 소문자로 보입니다(`ImportDate` → `importdate`).
- `_`로 시작하는 컬럼은 큰따옴표로 감쌉니다: `"_id"`, `"_corrupt_record"`.

```sql
SELECT item, code2, count(*) AS n
FROM tms_eda.tw_cems_raw
WHERE year = '2025' AND month = '03'
GROUP BY 1, 2 ORDER BY n DESC;
```

## 표본 행 수 확인

월별 행 수는 원본의 비어 있지 않은 줄 수와 같아야 합니다. 1~2개월만 직접 확인합니다(월 약 2.5GB를 받습니다).

```bash
aws s3 cp s3://smokestack-tms-raw-952900391026/bronze/tw_cems/historical/2025-03.jsonl - | grep -c .
```

```sql
SELECT count(*) FROM tms_eda.tw_cems_raw WHERE year = '2025' AND month = '03';
SELECT count(*) FROM tms_eda.tw_cems_raw
WHERE year = '2025' AND month = '03' AND "_corrupt_record" IS NOT NULL;   -- 손상 줄 수
```

## 비용 확인

- 백필이 끝나면 표의 `est_usd` 합계를 봅니다. `DPUSeconds × $0.308 / 3600`으로 계산한 추정치입니다.
- 실제 요금은 Billing → Cost Explorer에서 서비스 `Glue`, `Athena`로 확인합니다.
- 예상: 1회 백필 약 $3~5, 이후 Athena·S3 합쳐 월 $1 미만.

## 되돌리기

- **특정 월이 잘못됐을 때:** 그 월만 다시 실행합니다. `python run_backfill.py --from 2025-03 --to 2025-03`. 그 월 폴더만 교체되고 다른 월은 그대로입니다.
- 덮어쓴 이전 Parquet은 버전으로 남았다가 7일 뒤 정리됩니다.
- 원본 버킷에는 쓰기·삭제 권한이 없으므로 어떤 실행도 원본을 바꾸지 않습니다.

## 알려진 제약

- 대소문자만 다른 키(`ImportDate`와 `importdate`)가 한 달에 같이 있으면 Job이 실패합니다. Athena에서 같은 컬럼으로 충돌하기 때문입니다.
- 행 수 일치는 표본 월만 사람이 확인합니다. Job은 추가로 행을 세지 않습니다(원본을 두 번 읽지 않기 위해).
