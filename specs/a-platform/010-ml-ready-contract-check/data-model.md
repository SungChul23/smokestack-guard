# Data Model: K-TMS ML-ready 계약 검사 단계

## 1. 실행 입력 (상태 머신)

| 필드 | 기본값 | 값 | 설명 |
|---|---|---|---|
| `start_date`, `end_date` | `auto` | `YYYY-MM-DD` \| `auto` | 008과 같음. 둘 다 날짜이거나 둘 다 auto |
| `stage` | `all` | `all` \| `silver` \| `ml_ready` \| `check` | `check`는 Glue 잡 없이 검사만 |
| `notify` | `true` | bool | false면 알림을 보내지 않음(기록은 남음) |
| `check_table` | `tms_silver2.ktms_ml_ready` | 카탈로그 이름 | 합성 테이블 검사용 |
| `expect_source` | 없음 | 예: `ktms_synth` | `data_source` 기대값 |
| `real_table` | 없음 | 카탈로그 이름 | 굴뚝 키 겹침 비교 대상(합성용) |

모드(`observe` | `block`)는 입력이 아니라 Terraform 변수 `ktms_check_mode`다. 실행 입력으로 차단을 끌 수 없게 한다.

## 2. 검사 결과 (Lambda 출력)

| 필드 | 설명 |
|---|---|
| `result` | `passed` \| `violation` \| `empty` |
| `table`, `range`, `snapshot_id` | 검사 대상 |
| `rows` | 대상 범위 행 수 |
| `violations` | 위반 항목 수 |
| `run_record` | 실행 기록 S3 경로 |
| `subject`, `message` | 알림 제목·본문 (`passed`면 빈 값) |

검사 자체 실패는 출력이 아니라 Lambda 오류로 끝나고, 상태 머신 Catch가 처리한다.

상태 전이:

```
ML-ready 성공 ─▶ Check ─┬ passed ─────────────────────────▶ Done
                        ├ violation/empty ─ notify? ─▶ SNS ─┬ observe 또는 empty ─▶ Done
                        │                                    └ block + violation ─▶ Failed
                        └ 오류(재시도 1회 뒤) ─ notify? ─▶ SNS ─┬ observe ─▶ Done
                                                                 └ block ─▶ Failed
```

## 3. 위반 항목

C의 규칙이 돌려주는 문자열 한 줄을 그대로 쓰고, 앞에 검사 종류를 붙인다.

| 필드 | 값 |
|---|---|
| `kind` | `format` \| `rule` \| `recompute` \| `overlap` |
| `text` | C 규칙 문구 (예: `재계산 불일치 label_entry_60m: 1행 (첫 행 [...])`) |

## 4. 실행 기록 `silver2/_runs/ktms_ml_ready_check/<시작 UTC>_<요청 ID>.json`

008 실행 기록과 같은 이름 규칙(`ktms_pipeline.run_record_key`). 실패한 실행도 남긴다.

| 필드 | 설명 |
|---|---|
| `table`, `range`, `snapshot_id` | 검사 대상 |
| `range_source` | `ml_ready_run`(ML-ready 기록에서) \| `input`(stage=check) |
| `ml_ready_run_record` | 범위를 가져온 기록 경로(있으면) |
| `window` | 읽은 구간 `[lo, hi]` |
| `rows`, `window_rows` | 대상 행 수, 읽은 행 수 |
| `result` | `passed` \| `violation` \| `empty` \| `failed` |
| `violations` | 위반 항목 전체 목록 |
| `error` | 실패 시 오류 |
| `mode`, `notify`, `expect_source`, `real_table` | 실행 조건 |
| `sfn_execution`, `request_id` | 추적용 |
| `versions` | python, pandas, numpy |
| `started_at`, `finished_at` | UTC |

## 5. 통과 스냅샷 (E가 읽는 법)

마지막으로 `result = passed`인 기록의 `snapshot_id`가 "검사를 통과한 ML-ready"다. 같은 범위를 다시 갱신했다면 더 최근 통과 기록을 쓴다.
