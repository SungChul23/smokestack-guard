# Plan: 부분 이력 사용 가능 열

## 설계

- 값 계산은 `to_ml_ready`의 `classification_eligible` 바로 옆에서 한다(pandas `ml_ready.py`, Spark `ml_ready_spark.py`). 열 정의는 `COLUMNS`가 기준이다.
- Iceberg 형식은 `ktms_pipeline._ML_BOOL`에 추가해 boolean으로 잡는다. 없으면 double로 잘못 잡힌다.
- Terraform 카탈로그(`infra/stacks/tms-silver/main.tf`의 `ml_ready_columns`)에 boolean 열을 끝에 추가한다. 파일만 고치고 apply는 사람이 plan을 보고 한다.
- 계약 검사(`ml_ready_check._rule_checks`)에 규칙 하나를 더한다. 재계산 비교는 `COLUMNS` 전체를 돌므로 이 열도 자동으로 비교된다.
- 문서: 005 `data-model.md`, 008 `data-model.md`, 008 `contracts/ktms-tables.md`.

## 배포·재계산

1. PR 머지, Glue 스크립트·패키지 재배포(A와 확인).
2. 다음 매일 갱신에서 `ADD COLUMNS`가 열을 추가하고 최근 2일을 채운다.
3. 과거 구간은 `python run_ktms.py rerun --from <시작> --to <끝>`(quickstart 참고)으로 다시 계산한다. 11/11 이후를 우선 채운다. `--dry-run`으로 범위를 먼저 확인한다.
4. 계약 검사는 다시 계산한 범위에서 통과해야 한다. 재계산 전 범위를 지정해 검사하면 null 행이 불일치로 나올 수 있다.

## 위험

- 대만 표(`tms_silver2.tw_cems_ml_ready`)는 같은 코드로 만들지만 다시 계산하지 않으면 새 열이 없다. 대만 학습은 이 열을 쓰지 않으므로 급하지 않다. 합칠 때는 열이 없는 쪽을 null로 본다.
