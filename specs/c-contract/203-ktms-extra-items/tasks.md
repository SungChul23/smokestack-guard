# Tasks: K-TMS ML-ready에 CO·HCl·TSP 추가

- [x] T001 `KTMS_EXTRA_ITEMS`, `items_for` 추가, pandas 거름 변경 `src/smokestack_guard/silver/ml_ready.py`
- [x] T002 Spark `normalize`에 출처 반영 `services/tms-silver/ml_ready_spark.py`
- [x] T003 테스트: 실측은 5개 물질, 합성은 nox·sox, 기존 K-TMS 테스트의 비대상 물질을 nh3로 바꿈
- [x] T004 계약 문서 반영(008 `data-model.md`, `ktms-tables.md`)
- [ ] T005 CI에서 `test_glue_ktms_ml_ready.py` 등 통과 확인
- [ ] T006 머지 후 재배포, 일일 갱신 시간·크기 확인
- [ ] T007 `rerun --dry-run` 후 11/11 이후 재계산
- [ ] T008 도은 님께 `item_code` 필터와 새 물질 전달
