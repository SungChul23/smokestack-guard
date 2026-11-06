# Quickstart: TW CEMS Athena EDA 환경 검증

**Spec**: [spec.md](spec.md) · **계약**: [tw-cems-raw-parquet](contracts/tw-cems-raw-parquet.md), [run-interface](contracts/run-interface.md)

## 0. 준비 (WSL, 최초 1회)

```bash
sudo apt install -y openjdk-17-jdk-headless   # PySpark 4는 Java 17 이상 필요
java -version                                  # 17.x 확인
cd services/tms-eda
uv venv --python 3.13 && source .venv/bin/activate
uv pip install -e ".[dev]"
```

## 1. 로컬 검증 (클라우드 없이)

```bash
ruff check .
pytest -q
```

pytest가 확인하는 것:

| 테스트 | 확인 내용 |
|---|---|
| 행 수 | 손상 줄을 포함한 가짜 샘플(비어 있지 않은 줄 N개) → 출력 N행, `_SUCCESS` 생성 |
| 키 보존 | 입력의 모든 키 + `source_file`이 출력 컬럼에 있음 |
| 값 보존 | `"nan"`, 빈 값, 숫자 문자열이 그대로 |
| 두 월 | 키가 다른 두 샘플(예: `flareno` 포함)이 각각 변환됨 |
| 재실행 | 같은 월 두 번 → 결과 하나 |
| 대소문자 충돌 | Job이 실패하고 `_SUCCESS`가 없음 |
| 백필 | 월 파싱, 범위 필터, `--dry-run`이 Job을 시작하지 않음, 재시도 1회, 비용 계산 (boto3 mock) |

수동 로컬 실행:

```bash
python tw_cems_parquet.py --local --year 2025 --month 03 \
  --input_path tests/fixtures/synthetic_edge_cases.jsonl --output_path /tmp/tw_cems_raw
ls /tmp/tw_cems_raw/year=2025/month=03/    # part-*.parquet 2개 + _SUCCESS
```

## 2. 인프라 검토 (사용자, PowerShell)

```powershell
cd infra/stacks/tms-eda
terraform init
terraform fmt -check -recursive ..\..\
terraform validate
terraform plan
```

**기대 결과:** 새로 생성만 있고 변경·삭제는 0건이다.
- 생성 대상: 버킷 + 하위 설정 5개, 스크립트 객체, 역할 + 부착 + 인라인 정책, 로그 그룹, Glue DB, Job, 크롤러, 워크그룹
- `glue_version = "6.0"`이 오류 없이 받아들여져야 한다.

확인 후 사용자가 `terraform apply`를 실행한다.

## 3. 백필 (사용자, raw 업로드가 끝난 뒤)

```bash
python run_backfill.py --dry-run
```
- 대상 월이 36개(2023-11~2026-10)인지 확인한다. 이미 변환한 월을 건너뛰려면 `--only-missing`을 붙인다. 빠진 월이 있으면 업로드를 다시 확인한다.
- 파일 크기와 마지막 수정 시각이 업로드 완료 상태인지 본다.

```bash
python run_backfill.py                    # 기본 동시 6개, 약 15분
```
- 결과 표의 실패 목록이 비어 있는지 확인한다.

```bash
python run_backfill.py --only-missing     # 실패한 월이 있었을 때만
```

크롤러는 콘솔 Glue → Crawlers → `tms-eda-tw-cems-crawler` → Run으로 시작한다. 또는 `--only-missing --start-crawler`로 시작한다.

## 4. Athena 확인 (워크그룹 `tms-eda`)

```sql
SHOW TABLES IN tms_eda;   -- tw_cems_raw 하나만 있어야 한다
SELECT year, month, count(*) AS n
FROM tms_eda.tw_cems_raw
GROUP BY 1, 2 ORDER BY 1, 2;   -- 36행
```
- 이 쿼리는 Parquet 메타데이터로 계산되어 스캔이 거의 없다(추정).
- 한 달 조건을 붙인 집계가 1분 안에 끝나는지 확인한다 (SC-005).

**표본 행 수 확인 (SC-002, 1~2개월)**: 원본을 스트리밍해 비어 있지 않은 줄을 센다(월 약 2.5GB를 받는다).
```bash
aws s3 cp s3://smokestack-tms-raw-952900391026/bronze/tw_cems/historical/2025-03.jsonl - | grep -c .
```
- 이 숫자가 위 쿼리의 같은 월 `n`과 같아야 한다.
- 손상 줄 수는 Athena에서 확인한다: `SELECT count(*) FROM tms_eda.tw_cems_raw WHERE year='2025' AND month='03' AND "_corrupt_record" IS NOT NULL`. 그 달에 컬럼이 없으면 손상 줄이 0개라는 뜻이다.

## 5. 원본 불변 확인 (SC-006)

```bash
aws s3 ls s3://smokestack-tms-raw-952900391026/bronze/tw_cems/historical/ --summarize | tail -2
```
- 백필 전후 객체 수와 총 크기가 같아야 한다.

## 되돌리기

- **특정 월이 잘못됐을 때:** 그 월만 다시 실행한다. `--from YYYY-MM --to YYYY-MM`
- **스택 전체를 지울 때:** 버킷의 `prevent_destroy`를 사람이 먼저 풀어야 한다. 원본에는 영향이 없다.
