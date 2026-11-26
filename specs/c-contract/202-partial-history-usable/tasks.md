# Tasks: 부분 이력 사용 가능 열

- [x] T001 `COLUMNS`에 `partial_history_usable` 추가, 값 계산 `src/smokestack_guard/silver/ml_ready.py`
- [x] T002 Spark 구현 `services/tms-silver/ml_ready_spark.py`, Iceberg boolean 타입 `ktms_pipeline._ML_BOOL`
- [x] T003 계약 검사 규칙 `src/smokestack_guard/silver/ml_ready_check.py`
- [x] T004 테스트: 부분 이력 행 표시, 직전 30분·라벨 없는 행 제외, Spark 열 순서·타입, 열 개수 37
- [x] T005 문서: 005·008 `data-model.md`, 008 `contracts/ktms-tables.md`, Terraform 카탈로그 열
- [ ] T006 CI에서 `test_ktms_pipeline.py`, `test_lambda_ktms_ml_ready_check.py`, `test_glue_ktms_ml_ready.py` 통과 확인(로컬은 Python 3.11·pyspark 환경이 없어 못 돌림)
- [ ] T007 머지 후 A와 재배포, Terraform plan 확인·apply(사람)
- [ ] T008 `rerun --dry-run`으로 범위 확인 후 11/11 이후 재계산, 계약 검사 통과 확인
- [ ] T009 도은 님께 열 이름과 SOx 사용 규칙 전달
