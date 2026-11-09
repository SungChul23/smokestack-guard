# 계약: 실행 인터페이스 (Glue Job 인자, 일괄 실행 명령)

## 1. Glue Job `tms-silver-tw-cems`

스크립트: `services/tms-silver/glue_tw_cems_silver.py` → `s3://smokestack-tms-raw-952900391026/ops/glue-scripts/glue_tw_cems_silver.py`

패키지: `--extra-py-files s3://smokestack-tms-raw-952900391026/ops/glue-packages/smokestack_guard.zip`. 이 zip에는 `smokestack_guard/__init__.py`와 `smokestack_guard/silver/`만 들어 있다.

| 인자 | 필수 | 기본값 (Job `default_arguments`) | 뜻 |
|---|---|---|---|
| `--year` | 실행 시 | (없음) | `YYYY` |
| `--month` | 실행 시 | (없음) | `MM` (두 자리) |
| `--raw_bucket` | | `smokestack-tms-raw-952900391026` | 원본 버킷 |
| `--raw_prefix` | | `bronze/tw_cems/historical` | 원본 경로 |
| `--silver_bucket` | | `smokestack-tms-raw-952900391026` | 출력 버킷 (원본 버킷의 `silver/` 경로, R10) |
| `--table_prefix` | | `silver/tw_cems` | Silver 테이블 경로 |
| `--runs_prefix` | | `silver/_runs/tw_cems` | 실행 기록 경로 |
| `--package_md5` | | Terraform이 넣는 zip MD5 | 실행 기록용 |

**처리 순서** (근거: [research.md](../research.md) R2~R4)
1. `tw_cems_spark.read_raw`로 `{raw_prefix}/{year}-{month}.jsonl`을 읽는다.
2. 원본 10개 키만 남겨 `persist`하고, 입력 행 수를 센다.
3. `tw_cems_spark.to_silver`로 변환한다. `year`·`month`는 `ts_local`에서 만들며, `build()`와 같은 식이다. 결과를 `persist`한다.
4. (`year`, `month`, `status`)별 건수를 모은다.
5. 검사:
   - 다른 달 행이 있으면 **쓰기 전에 실패**한다.
   - 0행이면 실패한다.
6. `s3://{silver_bucket}/{table_prefix}/`에 `partitionBy("year","month")`로 동적 덮어쓰기한다.
7. 쓰기가 성공한 뒤 실행 기록 `{runs_prefix}/{year}-{month}.json`을 쓴다. 형식은 [data-model.md §3](../data-model.md)에 있다.

**실패** (Job 상태 `FAILED`, 실행 기록 없음, 기존 파티션 변경 없음)

| 경우 | 오류 메시지 |
|---|---|
| 입력 파일 없음 | Spark 읽기 오류 |
| 다른 달 행 있음 | `month mismatch: expected 2025-10, found {"2025-09": 12, ...}` |
| 결과 0행 | `empty silver for 2025-10` |

**로그**는 요약만 남긴다:
- 입력·출력 경로
- 입력 행 수, Silver 행 수, `status`별 행 수
- `package_md5`, 런타임 버전
- 소요 시간

데이터 값은 찍지 않는다.

## 2. 일괄 실행 명령 `services/tms-silver/run_silver.py`

사용자(A)가 자기 자격증명(환경 변수 또는 `--profile`)으로 실행한다. 코드에 자격증명을 쓰지 않는다.

```
python run_silver.py [--from YYYY-MM] [--to YYYY-MM] [--concurrency N]
                     [--only-missing] [--dry-run]
                     [--profile NAME] [--region ap-northeast-2]
```

| 옵션 | 기본값 | 뜻 |
|---|---|---|
| `--from` / `--to` | `2023-11` / `2026-10` | 대상 범위(포함). 원본 목록과 교집합 |
| `--concurrency` | `6` | 동시 실행 수. 1~6이 아니면 오류 |
| `--only-missing` | 끔 | 실행 기록이 있는 월은 `SKIPPED` |
| `--dry-run` | 끔 | 시작하지 않는다. 출력: 대상 월, 파일 크기, 범위 안에서 원본에 없는 월, 실행 기록 유무 |
| `--job-name` | `tms-silver-tw-cems` | |
| `--raw-bucket`, `--silver-bucket` | 위 버킷 | |

**동작**: `services/tms-eda/run_backfill.py`와 같다([003 계약 §2](../../003-tw-cems-eda/contracts/run-interface.md)).
- 30초마다 상태를 확인한다.
- 실패한 월은 1회 재시도한다.
- 동시 실행 상한으로 시작이 거절되면 시도로 세지 않고 다시 시작한다. 월마다 20번을 넘으면 실패로 처리한다.

**결과 표**: 월, 상태, 시도 수, run_id, 실행 초, DPU초, 추정 USD, `input_rows`, `silver_rows`, `ok_rows`.
- 행 수 세 개는 실행 기록에서 읽는다.
- 표 아래에 합계 행과 실패 목록을 출력한다.

**종료 코드**: 모두 성공(또는 SKIPPED)이면 0, 실패한 월이 있으면 1, 인자 오류는 2.
