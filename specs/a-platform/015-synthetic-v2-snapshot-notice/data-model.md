# Data Model: 합성 v2 전환과 학습 스냅샷 알림

## S3 경로 (원본 버킷 `smokestack-tms-raw-952900391026`)

| 경로 | 쓰는 주체 | 상태 |
|---|---|---|
| `tms_synthetic_train/…` | (없음) | v1. 보존만, 더 쓰지 않음 |
| `tms_synthetic_train_v2/ingest_date=…/hour=…/run_ts=…/` | 합성 적재 Lambda | v2 스냅샷(실측과 같은 폴더 모양) |
| `tms_synthetic_train_v2/_manifest/YYYY-MM-DD.jsonl` | 합성 적재 Lambda | 에피소드 태그(v2 모양 이름) |
| `tms_synthetic_train_v2/_ref_stats/ref-1030-1110.csv` | 사람 | 참조 통계(v1과 같은 파일 복사, 덮어쓰지 않음) |

## Silver 표 (이름 그대로, 새 버전)

| 표 | 원본 | 변화 |
|---|---|---|
| `tms_silver2.ktms_synth` | `tms_synthetic_train_v2/` | 10/30~D−2 다시 계산 → 새 스냅샷 |
| `tms_silver2.ktms_synth_ml_ready` | `ktms_synth` | 같음 |

모양 이름(굴뚝 코드 `SYN-T-<날짜>-<성분>-<모양>-<번호>`): v2 = `GRADUAL`, `SPIKE`, `EXCEED`, `PLATEAU`, `OVER`, `FALLING`, `NEAR_HOLD`, `IRREGULAR_RISE`, `OSCILLATION`, `NEAR_MISS`. v1의 `OTHER`는 없다.

## 실행 기록 (알림이 읽는 것, 이미 있음)

| 경로 | 필드 |
|---|---|
| `silver2/_runs/ktms/`, `silver2/_runs/ktms_synth/` | `result`, `range`, `snapshot_id`, `started_at`, `finished_at`, `sfn_execution` |
| `silver2/_runs/ktms_ml_ready/`, `…/ktms_synth_ml_ready/` | 같음 + `source.table` |
| `silver2/_runs/ktms_ml_ready_check/` | `table`, `result`(passed·violation·empty·failed), `range`, `snapshot_id`, `ml_ready_run_record`, `started_at` |

## 알림 항목 (Lambda 안에서 만듦, 저장하지 않음)

| 필드 | 출처 |
|---|---|
| `source` | `ktms` · `ktms_synth` |
| `run_date` | 검사 기록 `started_at`(KST 날짜) |
| `result` | 검사 기록 `result` |
| `ml_ready_snapshot` | 검사 기록 `snapshot_id` |
| `silver_snapshot` | ML-ready 실행 시작 전 마지막 성공 Silver 기록의 `snapshot_id` (R5) |
| `confirmed` | 첫날 ~ `run_date − 2일` |

## 새 AWS 자원 (`tms-silver` 스택)

| 자원 | 이름 |
|---|---|
| SNS 토픽 | `tms-training-snapshots` |
| 이메일 구독 | SSM `/tms/notice/training-snapshot-emails`(사람이 등록) 목록대로 |
| Lambda | `tms-training-snapshot-notice` (+ 로그 그룹 14일) |
| Scheduler | `tms-training-snapshot-notice`, `cron(0 5 * * ? *)` Asia/Seoul |
