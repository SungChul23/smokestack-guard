# 계약: 실행 인터페이스 (Glue Job 인자, 백필 명령)

## 1. Glue Job `tms-eda-tw-cems-parquet`

스크립트: `services/tms-eda/tw_cems_parquet.py` → `s3://smokestack-tms-eda-952900391026/glue-scripts/tw_cems_parquet.py`

| 인자 | 필수 | 기본값 (Job `default_arguments`) | 뜻 |
|---|---|---|---|
| `--year` | 실행 시 | (없음) | `YYYY` |
| `--month` | 실행 시 | (없음) | `MM` (두 자리) |
| `--raw_bucket` | | `smokestack-tms-raw-952900391026` | 원본 버킷 |
| `--raw_prefix` | | `bronze/tw_cems/historical` | 원본 경로 |
| `--eda_bucket` | | `smokestack-tms-eda-952900391026` | 출력 버킷 |
| `--output_prefix` | | `tw_cems_raw` | 출력 경로 |
| `--local` | 로컬 | (없음) | 로컬 Spark로 실행. `--input_path`, `--output_path` 필수 |
| `--input_path` | 로컬 | | 로컬 입력 파일 |
| `--output_path` | 로컬 | | 로컬 출력 폴더 (`year=/month=` 아래가 만들어짐) |

- 그 밖에 Glue가 넘기는 인자(`--JOB_NAME`, `--TempDir` 등)는 무시한다.
- **성공**: Parquet과 Spark 기본 `_SUCCESS`를 쓰고 정상 종료한다.
- **실패**: 아래 경우 예외로 종료한다(Job 상태 `FAILED`). 쓰기 전에 실패하면 `_SUCCESS`가 없다.
  - 입력 파일이 없을 때
  - 소문자로 바꾼 컬럼 이름이 충돌할 때
- 로그에는 요약만 남긴다: 입력 경로, 출력 경로, 컬럼 수, 컬럼 이름, Spark 버전, 소요 시간. 데이터 값은 찍지 않는다.

## 2. 백필 명령 `services/tms-eda/run_backfill.py`

사용자(A)가 자기 자격증명(환경 변수 또는 `--profile`)으로 실행한다. 코드에 자격증명을 쓰지 않는다.

```
python run_backfill.py [--from YYYY-MM] [--to YYYY-MM] [--concurrency N]
                       [--only-missing] [--dry-run] [--start-crawler]
                       [--profile NAME] [--region ap-northeast-2]
```

| 옵션 | 기본값 | 뜻 |
|---|---|---|
| `--from` / `--to` | `2024-01` / `2026-10` | 대상 범위(포함). raw 목록과 교집합 |
| `--concurrency` | `6` | 동시 실행 수. 1~6이 아니면 오류 |
| `--only-missing` | 끔 | `_SUCCESS`가 있는 월은 `SKIPPED` |
| `--dry-run` | 끔 | 시작하지 않는다. 대상 월, 파일 크기, 마지막 수정 시각, 범위 안에서 빠진 월을 출력 |
| `--start-crawler` | 끔 | 모든 월이 끝난 뒤 크롤러 `tms-eda-tw-cems-crawler`를 시작. 실패한 월이 있으면 경고를 출력하고 시작하지 않는다 |
| `--job-name` | `tms-eda-tw-cems-parquet` | |
| `--raw-bucket`, `--eda-bucket` | 위 버킷 | |

**동작**
- 30초마다 실행 상태를 확인한다.
- 실패한 월은 1회만 다시 시작한다.
- 동시 실행 상한 때문에 시작이 거절되면(`ConcurrentRunsExceededException`) 시도로 세지 않고 다음 확인 때 다시 시작한다. 실행이 만들어지지 않으므로 과금되지 않는다. Glue는 끝난 실행을 잠시 진행 중으로 세므로 이런 거절이 생긴다(2026-11-05 백필에서 확인). 월마다 20번 넘게 거절되면 실패로 처리한다.
- 끝나면 [data-model.md §5](../data-model.md) 형식의 표와 합계 추정 비용, 실패 목록을 출력한다.

**종료 코드**: 모두 성공(또는 SKIPPED)이면 0, 실패한 월이 있으면 1, 인자 오류는 2.
