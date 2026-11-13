# 계약: 실행 인터페이스

## 1. Step Functions 입력 (`tms-silver2-ktms`)

매일 예약 실행은 `{}`를 넘긴다. 사람이 실행할 때는 필요한 필드만 넣는다.

| 필드 | 기본값 | 값 |
|---|---|---|
| `start_date` | `auto` | KST 측정일 `YYYY-MM-DD` 또는 `auto` |
| `end_date` | `auto` | KST 측정일 `YYYY-MM-DD` 또는 `auto` |
| `stage` | `all` | `all`(Silver → ML-ready), `silver`, `ml_ready` |

- `auto`이면 끝난 최근 2일이다(data-model §5).
- 한쪽만 날짜를 주면 잡이 거부한다. 둘 다 주거나 둘 다 `auto`여야 한다.

```bash
# 예: 11-05 ~ 11-07 다시 실행
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:ap-northeast-2:952900391026:stateMachine:tms-silver2-ktms \
  --name rerun-20261105-20261107 \
  --input '{"start_date":"2026-11-05","end_date":"2026-11-07"}'
```

실행 결과:
- 성공: `Succeeded`
- 실패: 재시도 후 SNS `tms-collector-alerts`로 메일이 오고 `Failed`로 끝난다.

## 2. Glue 잡 인자

두 잡이 같은 인자 이름을 쓴다. Terraform이 기본값을 넣고, Step Functions는 `--start_date`, `--end_date`, `--sfn_execution`만 넘긴다.

| 인자 | Silver 기본값 | ML-ready 기본값 | 설명 |
|---|---|---|---|
| `--start_date`, `--end_date` | `auto` | `auto` | §1과 같다 |
| `--bucket` | `smokestack-tms-raw-952900391026` | 같음 | 원본·테이블 버킷 |
| `--source_prefix` | `tms_cleansys/` | (없음) | 원본 경로. 기본값이 아니면 C의 `read_bronze`에 경로 인자가 있어야 한다(research R9) |
| `--silver_table` | `tms_silver2.ktms` | 같음 | Silver 테이블(ML-ready에서는 입력) |
| `--ml_ready_table` | (없음) | `tms_silver2.ktms_ml_ready` | ML-ready 테이블 |
| `--runs_prefix` | `silver2/_runs/ktms` | `silver2/_runs/ktms_ml_ready` | 실행 기록 경로 |
| `--max_days` | `7` | (없음) | Silver 한 번에 처리할 최대 일수 |
| `--package_md5` | Terraform | Terraform | C 코드 zip MD5 |
| `--sfn_execution` | `manual` | `manual` | Step Functions 실행 이름 |
| `--local` | | | 로컬 Spark + Hadoop 카탈로그로 실행(테스트용) |

종료:
- 성공: 요약 JSON 한 줄을 출력하고 정상 종료한다.
- 실패: 실패 기록을 남기고 예외를 그대로 던진다(Glue `FAILED`).

실패 이유:

| 이유 | 단계 |
|---|---|
| 날짜 형식·순서 오류, `max_days` 초과 | 인자 검사 |
| 합성 경로인데 `read_bronze`에 경로 인자 없음 | 인자 검사 |
| 원본 스냅샷 0개 | 읽기 |
| 결과 0행 | 쓰기 전 |
| Iceberg 커밋 충돌·S3 오류 | 쓰기 |

## 3. 실행 기록 JSON

경로: `s3://smokestack-tms-raw-952900391026/<runs_prefix>/<시작 UTC>_<job_run_id>.json`

```json
{
  "table": "tms_silver2.ktms",
  "result": "succeeded",
  "error": null,
  "job_run_id": "jr_…",
  "sfn_execution": "…",
  "range": {"start": "2026-11-11", "end": "2026-11-12"},
  "source": {"prefix": "tms_cleansys/", "ingest_dates": ["2026-11-10", "2026-11-13"], "snapshots": 412},
  "rows": 612345,
  "rows_per_day": {"2026-11-11": 306100, "2026-11-12": 306245},
  "empty_days": [],
  "status_rows": {"ok": 0, "stopped": 0, "checking": 0},
  "duplicate_keys": 0,
  "snapshot_id": 1234567890123456789,
  "package_md5": "…",
  "versions": {"spark": "3.5.4", "python": "3.11.x", "pandas": "…", "numpy": "…"},
  "started_at": "2026-11-12T18:00:41+00:00",
  "finished_at": "2026-11-12T18:04:10+00:00"
}
```

- 숫자는 예시다.
- Silver의 `rows_per_day`, `status_rows`, `duplicate_keys`, `snapshots`는 C의 `quality()` 결과를 그대로 옮긴다.
- ML-ready에서는 `status_rows`, `duplicate_keys`, `source.ingest_dates` 대신 다음 필드를 넣는다.
  - `input_rows`: 읽은 Silver 행
  - `classification_eligible`, `regression_eligible`: 학습 가능 행 수
  - `positives`: `label_entry_60m = 1` 이고 `classification_eligible`인 행 수
- `result = "failed"`이면 `error`에 예외 종류와 메시지 첫 줄을 넣고, 아직 모르는 필드는 null이다. 데이터 값은 넣지 않는다.

## 4. 사람이 실행하는 명령 `run_ktms.py`

```bash
python run_ktms.py backfill --from 2026-10-30 --to 2026-11-12 --dry-run   # 묶음 계획만 출력
python run_ktms.py backfill --from 2026-10-30 --to 2026-11-12             # Silver 5일씩 → ML-ready 전체
python run_ktms.py rerun --from 2026-11-05 --to 2026-11-07 [--stage all|silver|ml_ready]
python run_ktms.py runs --table ktms --last 5                              # 최근 실행 기록 표
```

- Step Functions 실행을 시작하고 끝날 때까지 30초마다 상태를 본다. 하나가 실패하면 멈춘다.
- 자격증명은 실행자의 환경 변수나 `--profile`에서 읽는다.
