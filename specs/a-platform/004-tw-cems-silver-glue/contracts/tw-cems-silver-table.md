# 계약: Silver 테이블 `tms_silver.tw_cems` (저장·조회)

행의 **의미**(슬롯, `status`, `ratio` 규칙)는 C의 계약 `specs/c-contract/201-tw-cems-silver/spec.md`가 정한다. 이 문서는 저장 위치·타입·조회 방법만 정한다. 컬럼을 추가·삭제·변경하려면 C의 계약을 먼저 고친다.

## 위치

- 데이터: `s3://smokestack-tms-raw-952900391026/silver/tw_cems/year=YYYY/month=MM/part-*.snappy.parquet`
- 파티션 `year`·`month`: `ts_local`(대만 현지 시각)의 연·월. 원본 파일 월과 같다.

## 스키마

[data-model.md §2](../data-model.md)의 표 13개 컬럼 + 파티션 2개. Parquet 타입과 카탈로그 타입이 같다.

## 읽는 방법

| 누가 | 어떻게 | 비고 |
|---|---|---|
| Athena (C·D·E) | 워크그룹 `tms-eda`에서 `tms_silver.tw_cems` 조회 | 파티션 프로젝션이라 새 월도 바로 보인다. 쿼리당 스캔 한도는 10GB |
| Spark·Glue (005 ML-ready, E) | `spark.read.parquet("s3://smokestack-tms-raw-952900391026/silver/tw_cems/")` | **카탈로그 테이블로 읽지 않는다.** 프로젝션 파티션은 Spark에서 보이지 않는다 |
| pandas (로컬) | `pd.read_parquet("s3://.../silver/tw_cems/year=2025/month=10/")` | 자격증명은 각자 프로필 |

예시:
```sql
SELECT status, count(*) AS n
FROM tms_silver.tw_cems
WHERE year = '2025' AND month = '10'
GROUP BY status;
```

- `limit` 컬럼은 예약어라 `"limit"`으로 감싼다.
- 시각은 시간대 없는 벽시계 값이다. `ts_kst` = `ts_local` + 1시간.

## 바뀌는 시점

- 같은 월을 다시 실행하면 그 파티션만 통째로 교체된다.
- 원본 버킷은 버전 관리가 켜져 있고 수명 주기 규칙이 없다. 그래서 교체된 이전 파일은 이전 버전으로 계속 남는다(R11). 지울 때는 사람이 직접 지운다.
