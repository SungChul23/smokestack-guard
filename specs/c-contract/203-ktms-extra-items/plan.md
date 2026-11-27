# Plan: K-TMS ML-ready에 CO·HCl·TSP 추가

- `ml_ready.py`: `KTMS_EXTRA_ITEMS`, `items_for(data_source)`. 입력 거름이 `data_source`가 정해진 뒤 `items_for`를 쓴다(합성·대만은 `ML_ITEMS`).
- `ml_ready_spark.py`: `normalize(silver, data_source=None)`가 같은 함수를 쓴다. 대만 Glue 잡은 `normalize(silver)`를 그대로 불러도 출처가 `tw_cems`로 정해져 바뀌지 않는다.
- 컬럼 변경이 없어 Iceberg·Terraform 변경은 없다.
- 문서: 008 `data-model.md`, `contracts/ktms-tables.md`.

## 배포·재계산

1. 머지, 재배포(A와 확인).
2. 다음 매일 갱신이 최근 2일에 새 물질 행을 채운다.
3. 과거 구간은 `rerun --dry-run`으로 범위를 확인한 뒤 11/11 이후부터 `rerun`. 분석에는 Silver를 직접 읽어도 된다.
4. 도은 님께 `item_code` 필터와 새 물질 추가를 알린다.

## 위험

- ML-ready 표 크기가 늘어난다(실측 `ok` 행 기준 CO 41만, HCl 96만, TSP 103만행 = 현재 NOx·SOx 353만행의 약 70%). 일일 갱신 시간과 비용을 한 번 확인한다.
