# 계약: ML-ready 테이블 `tms_silver.tw_cems_ml_ready` (저장·조회)

컬럼의 **의미**(피처·라벨 정의)는 C의 `ml_ready.py`와 `specs/c-contract/201-tw-cems-silver/spec.md`가 정한다. 이 문서는 저장 위치·타입·읽는 방법만 정한다. 컬럼을 추가·변경하려면(예: `observed_risk_level`, 기준치 변경 플래그) C의 `ml_ready.py`를 먼저 고친다.

## 위치와 형태

- `s3://smokestack-tms-raw-952900391026/silver/tw_cems_ml_ready/part-*.parquet`
- 파티션 없음. 파일 4~8개, 파일마다 연속된 `measured_at` 구간
- 스키마: [data-model.md §2](../data-model.md) 35컬럼

## 읽기 전에 확인

`s3://smokestack-tms-raw-952900391026/silver/_runs/tw_cems_ml_ready/latest.json`이 있어야 한다. 없으면 마지막 생성이 실패했거나 진행 중이므로 읽지 않는다.

## 읽는 방법

| 누가 | 어떻게 |
|---|---|
| Athena | 워크그룹 `tms-eda`, `tms_silver.tw_cems_ml_ready` |
| SageMaker / pandas (E) | `pd.read_parquet("s3://…/silver/tw_cems_ml_ready/", filters=[("measured_at", ">=", …), ("measured_at", "<", …)])` |
| Spark | `spark.read.parquet("s3://…/silver/tw_cems_ml_ready/")` |

예시 (분할은 E가 정한다):
```sql
-- 학습 가능 행과 양성 수 (item별)
SELECT item_code,
       count_if(classification_eligible) AS eligible,
       count_if(classification_eligible AND label_entry_60m = 1) AS positives
FROM tms_silver.tw_cems_ml_ready
GROUP BY item_code;
```

## 알아둘 점

- **분할 경계 누수**: 라벨이 60분 뒤 값을 본다. 그래서 구간 경계 앞 1시간 행은 다음 구간 값을 참조한다. 경계에 1시간 이상 간격을 두는 처리는 E가 한다.
- 시간 피처(`hour_*`, `month_*`, `day_of_week`)는 대만 현지 시각 기준이다. K-TMS(`ktms_ml_ready`, 후속)는 한국 시각 기준이다.
- `month_sin/cos`를 국내 적용 모델에 쓸지는 E가 정한다. 국내 데이터가 짧아서다(범위 밖).
- 다시 생성하면 전체가 바뀐다. 이전 버전 파일은 원본 버킷의 버전 관리로 남는다(수명 주기 규칙 없음).
