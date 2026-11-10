# Implementation Plan: TW CEMS 재수집 원본 비교 (bronze2 → silver2)

**Branch**: `32-a-tw-cems-ml-ready-spark-이식-silvertw_cems-silvertw_cems_ml_ready` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md) | **Issue**: #32

## Summary

기존 004·005 Job과 **같은 스크립트·패키지**를 쓰는 Glue Job 2개를 경로만 바꿔 추가한다. 입력은 `bronze2/tw_cems/`, 출력은 `silver2/`, 카탈로그는 `tms_silver2`다. 기존 리소스와 데이터는 그대로 둔다. Python 코드는 바꾸지 않는다(실행 명령이 이미 `--job-name`, `--raw-prefix`, `--runs-prefix`를 받는다).

## Technical Context

- **Terraform**: `infra/stacks/tms-silver/silver2.tf` (새 파일). 컬럼 정의는 `main.tf`의 `locals`(`silver_columns`, `ml_ready_columns`)를 함께 쓴다. 이 이동은 기존 리소스 변경이 없다(plan 확인).
- **Glue**: 5.0, G.1X. Silver2는 기존과 같이 10 워커·동시 6, ML-ready2는 10 워커·동시 1.
- **정답지**: 변수 `silver2_ml_ready_reference` (기본값 C의 `tw_cems_ml_ready_fixed/part.parquet`).
- **실행**: 사람이 WSL에서 `run_silver.py`, `run_ml_ready.py`. Terraform은 사람이 PowerShell에서 plan·apply.

## Constitution Check

| 원칙 | 판단 |
|---|---|
| I. 원본 보존 | ✅ `bronze/`·`bronze2/`는 읽기만. 새 역할은 `silver2/` 아래에만 쓰기·삭제. 기존 `silver/`를 덮어쓰지 않는다 |
| 비밀값 | ✅ 해당 없음 |
| 최소 권한 | ✅ 역할을 Job마다 따로 두고, 기존 역할 권한을 넓히지 않는다 |
| 비용 | ✅ 일회성 약 $5. 보관 `bronze2/` 약 $2.3/월 |

## 리소스 (`silver2.tf`)

| 리소스 | 이름 | 비고 |
|---|---|---|
| IAM 역할 | `tms-glue-silver2` | 읽기 `bronze2/tw_cems/*`, 쓰기·삭제 `silver2/tw_cems/*`, `silver2/_runs/tw_cems/*`, 폴더 표시 파일 `silver2_$folder$`, `silver2/tw_cems_$folder$` |
| Glue Job | `tms-silver2-tw-cems` | 스크립트 `ops/glue-scripts/glue_tw_cems_silver.py` (004와 같음) |
| IAM 역할 | `tms-glue-silver2-ml-ready` | 읽기 `silver2/tw_cems/*`·정답지 경로, 쓰기·삭제 `silver2/tw_cems_ml_ready/*`, `silver2/_runs/tw_cems_ml_ready/*` |
| Glue Job | `tms-silver2-tw-cems-ml-ready` | 스크립트 `ops/glue-scripts/glue_tw_cems_ml_ready.py` + `ml_ready_spark.py` (005와 같음), `--reference` = 정답지 |
| Glue DB | `tms_silver2` | |
| Glue 테이블 | `tms_silver2.tw_cems` | 파티션 프로젝션 `year`/`month`, 크롤러 없음 |
| Glue 테이블 | `tms_silver2.tw_cems_ml_ready` | 파티션 없음 |

## 실행 순서

1. `terraform plan` → `11 to add, 0 to change, 0 to destroy` 확인 → apply
2. Silver2: `run_silver.py --job-name tms-silver2-tw-cems --raw-prefix bronze2/tw_cems --runs-prefix silver2/_runs/tw_cems` (한 달 시험 2024-03 → 나머지 `--only-missing`)
3. Athena로 `tms_silver.tw_cems` vs `tms_silver2.tw_cems` 비교
4. main 머지(PR #34 v2) → Spark v2 반영(005 코드) → plan·apply(패키지·Job 인자 6개 변경)
5. ML-ready2: `run_ml_ready.py --mode build --job-name tms-silver2-tw-cems-ml-ready --runs-prefix silver2/_runs/tw_cems_ml_ready`
6. 정답지 권한·`--reference` 추가 → plan·apply(2개 변경) → `--mode compare`

## 실행 결과 (2026-11-10)

| 단계 | 결과 |
|---|---|
| Silver2 | 36/36 성공, 실패 0. 13:38 ~ 약 13:56(약 18분), 월 실행 86 ~ 201초. 패키지 MD5 `1b4585d5…` |
| ML-ready2 build | 18,436,379행, 파일 6개. 패키지 MD5 `5bbd7394…` (v2) |
| ML-ready2 compare | `passed=True`. 최대 차이 `ratio_rolling_std_3h` 5.96e-06 |

수치와 해석은 [spec.md](spec.md) "결과"에 있다.

## 비교에 쓴 쿼리

- 원본 줄 단위 비교: `tms_eda`에 임시 테이블(한 줄 = 문자열 하나, 파티션 `src=old/new`)을 만들어 `xxhash64`로 월별 비교하고 지웠다. 원본 두 벌 약 182GB를 읽어 `tms-eda` 워크그룹 10GB 제한을 넘으므로 `primary` 워크그룹에서 1회 실행했다(약 $0.9).
- Silver 비교: `stack_code`·`item`·`ts_local`로 두 테이블을 FULL JOIN해 상태 변화와 값 변경을 셌다.
- ML-ready 비교: 월별 학습 가능 행·양성 비율, 새로 생긴 행 vs 기존 행의 분포, 굴뚝·항목별 증가율.
