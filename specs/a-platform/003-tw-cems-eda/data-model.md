# Data Model: TW CEMS Athena EDA 환경

**Spec**: [spec.md](spec.md) · **계약**: [contracts/](contracts/)

## 1. 원본 월 파일 (입력, 읽기 전용)

| 항목 | 값 |
|---|---|
| 위치 | `s3://smokestack-tms-raw-952900391026/bronze/tw_cems/historical/YYYY-MM.jsonl` |
| 형식 | 압축 없는 JSONL. 한 줄이 객체 하나 |
| 크기 | 파일당 약 2.2~2.8GB |
| 대상 | 2023-11~2026-10 중 존재하는 월 (2026-11-06 변경, 이전 2024-11~) |
| 키 | 2024-03 기준 15개(spec Assumptions). 다른 달은 미확인 |

- 파일명이 `^\d{4}-\d{2}\.jsonl$`이 아니면 대상에서 제외한다.
- 이 기능은 원본을 바꾸지 않는다.

## 2. EDA 테이블 `tms_eda.tw_cems_raw` (출력)

자세한 내용은 [contracts/tw-cems-raw-parquet.md](contracts/tw-cems-raw-parquet.md)에 있다.

| 컬럼 | 출처 | 비고 |
|---|---|---|
| 원본 키 전체 | 입력 | 값은 원문 문자열. Athena에서는 이름이 소문자로 보인다(`ImportDate` → `importdate`) |
| `_corrupt_record` | Spark | 손상된 줄의 원문. 그 달에 손상 줄이 있을 때만 생긴다 |
| `source_file` | `_metadata.file_path` | 원본 파일 전체 경로 |
| `year`, `month` | 경로 파티션 | 문자열 `'2025'`, `'03'`. 데이터 파일 안에는 없다 |

**규칙**
- 소문자로 바꾼 컬럼 이름에 중복이 있으면 Job을 실패시킨다 (R6).
- 행 수 일치(행 수 = 비어 있지 않은 입력 줄 수)는 PERMISSIVE 읽기로 보장하고, 표본 월만 사람이 확인한다 (R5).

## 3. 월 완료 표지 `_SUCCESS`

- 위치: `tw_cems_raw/year=YYYY/month=MM/_SUCCESS`
- Spark가 쓰기를 끝까지 마쳤을 때 남기는 빈 파일이다.
- `--only-missing`의 기준이 된다. 행 수 검증 결과는 아니다.

## 4. 월 변환 실행의 상태 흐름 (백필 스크립트 기준)

```
PENDING ─start─▶ RUNNING ─▶ SUCCEEDED
                    │
                    └─▶ FAILED/ERROR/TIMEOUT/STOPPED ─(1회)─▶ RUNNING(재시도) ─▶ SUCCEEDED
                                                                  └─▶ FAILED(최종, 실패 목록)
SKIPPED: --only-missing에서 _SUCCESS가 이미 있는 월
```

- 동시에 `RUNNING`인 월은 `--concurrency` 이하(기본·최대 6)로 유지한다.
- Job 자체의 동시 실행 상한은 6이다.

## 5. 백필 결과 행 (화면 출력)

| 필드 | 뜻 |
|---|---|
| `month` | `YYYY-MM` |
| `state` | 최종 상태 |
| `attempts` | 1 또는 2 |
| `run_id` | 마지막 JobRunId |
| `execution_s` | `ExecutionTime` (초) |
| `dpu_s` | `DPUSeconds`. 비어 있으면 `ExecutionTime × NumberOfWorkers` |
| `est_usd` | `dpu_s / 3600 × 0.308` |

마지막 줄에는 합계와 실패 목록을 출력한다.
