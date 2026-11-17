-- Silver 지표 검증 쿼리 (용어·산식 사전 5.1절 지표를 Silver에서 직접 계산)
-- 입력: Silver 테이블 한 개. 대만은 area_nm·fact_manage_nm·stack_code·item·unit·value·limit·status·ts_kst·ratio·ts_local,
--       K-TMS(tms_silver2.ktms)는 unit·ts_local이 없다. 아래 쿼리는 두 테이블에 공통인 컬럼만 쓴다.
-- 자리표시자: {silver} = 테이블 이름, {start} = 시작 시각(포함), {end} = 끝 시각(제외), 시각은 한국 시각(ts_kst)이다.
-- 굴뚝은 (area_nm, fact_manage_nm, stack_code)로 식별한다. K-TMS의 stack_code는 같은 사업장 안의 호기 번호라서 단독으로 쓰면 안 된다.
-- 표준 SQL만 쓰고 limit 컬럼은 큰따옴표로 감싼다(Athena 방식). Spark SQL에서는 spark.sql.ansi.enabled=true, spark.sql.ansi.doubleQuotedIdentifiers=true로 같은 문장을 돌린다.

-- name: example_entry_stacks
-- "최근 일주일 NOx 기준대비율이 90%를 넘은 배출구" (사전 5.2절). 극단값(ratio > 2)은 포함한 값과 제외한 값을 함께 낸다.
SELECT area_nm, fact_manage_nm, stack_code,
       COUNT(*)                                          AS entry_slots,
       MAX(ratio)                                        AS max_ratio,
       MAX(CASE WHEN ratio <= 2 THEN ratio END)          AS max_ratio_ex_extreme,
       SUM(CASE WHEN ratio > 2 THEN 1 ELSE 0 END)        AS extreme_slots,
       MAX(ts_kst)                                       AS last_entry_ts
FROM {silver}
WHERE status = 'ok' AND item = 'nox' AND ratio >= 0.9
  AND ts_kst >= TIMESTAMP '{start}' AND ts_kst < TIMESTAMP '{end}'
GROUP BY area_nm, fact_manage_nm, stack_code
ORDER BY entry_slots DESC, area_nm, fact_manage_nm, stack_code;

-- name: entry_slots_by_item
-- 진입 슬롯 수 = COUNT(슬롯 WHERE ratio >= 0.9)
SELECT item, COUNT(*) AS entry_slots
FROM {silver}
WHERE status = 'ok' AND ratio >= 0.9 AND ts_kst >= TIMESTAMP '{start}' AND ts_kst < TIMESTAMP '{end}'
GROUP BY item ORDER BY item;

-- name: entry_stacks_by_item
-- 진입 굴뚝 = 90% 이상이 한 번이라도 있었던 굴뚝 수
SELECT item, COUNT(*) AS entry_stacks
FROM (SELECT DISTINCT item, area_nm, fact_manage_nm, stack_code
      FROM {silver}
      WHERE status = 'ok' AND ratio >= 0.9 AND ts_kst >= TIMESTAMP '{start}' AND ts_kst < TIMESTAMP '{end}') t
GROUP BY item ORDER BY item;

-- name: exceed_slots_by_item
-- 기준 초과 슬롯 수 = COUNT(슬롯 WHERE ratio >= 1.0)
SELECT item, COUNT(*) AS exceed_slots
FROM {silver}
WHERE status = 'ok' AND ratio >= 1.0 AND ts_kst >= TIMESTAMP '{start}' AND ts_kst < TIMESTAMP '{end}'
GROUP BY item ORDER BY item;

-- name: missing_ratio_by_item
-- 결측 슬롯 비율 = COUNT(status <> 'ok') / COUNT(*)  (분모는 상태와 관계없이 모든 슬롯)
SELECT item,
       COUNT(*)                                              AS slots,
       SUM(CASE WHEN status <> 'ok' THEN 1 ELSE 0 END)       AS not_ok_slots,
       CAST(SUM(CASE WHEN status <> 'ok' THEN 1 ELSE 0 END) AS DOUBLE) / COUNT(*) AS not_ok_ratio
FROM {silver}
WHERE ts_kst >= TIMESTAMP '{start}' AND ts_kst < TIMESTAMP '{end}'
GROUP BY item ORDER BY item;

-- name: extreme_report_by_item
-- 평균·최대는 극단값(ratio > 2, 200% 초과)을 포함한 값과 제외한 값을 함께 낸다 (사전 5.1절 보고 규칙)
SELECT item,
       COUNT(*)                                              AS ok_slots,
       SUM(CASE WHEN ratio > 2 THEN 1 ELSE 0 END)            AS extreme_slots,
       AVG(ratio)                                            AS mean_ratio,
       AVG(CASE WHEN ratio <= 2 THEN ratio END)              AS mean_ratio_ex_extreme,
       MAX(ratio)                                            AS max_ratio,
       MAX(CASE WHEN ratio <= 2 THEN ratio END)              AS max_ratio_ex_extreme
FROM {silver}
WHERE status = 'ok' AND ts_kst >= TIMESTAMP '{start}' AND ts_kst < TIMESTAMP '{end}'
GROUP BY item ORDER BY item;

-- name: invariants
-- 항상 0이어야 하는 값. 하나라도 0이 아니면 Silver 계약이 깨진 것이다.
SELECT
  SUM(CASE WHEN status = 'ok' AND ratio IS NULL THEN 1 ELSE 0 END)                       AS ok_without_ratio,
  SUM(CASE WHEN ratio IS NOT NULL AND ("limit" IS NULL OR "limit" <= 0) THEN 1 ELSE 0 END)   AS ratio_without_limit,
  SUM(CASE WHEN ratio IS NOT NULL AND "limit" > 0 AND ABS(ratio - value / "limit") > 1e-6 THEN 1 ELSE 0 END) AS ratio_mismatch
FROM {silver}
WHERE ts_kst >= TIMESTAMP '{start}' AND ts_kst < TIMESTAMP '{end}';

-- name: duplicate_keys
-- 같은 (사업장, 굴뚝, 항목, 시각) 행이 둘 이상이면 그 초과분. 0이어야 한다.
SELECT COALESCE(SUM(c - 1), 0) AS duplicate_keys
FROM (SELECT COUNT(*) AS c FROM {silver}
      WHERE ts_kst >= TIMESTAMP '{start}' AND ts_kst < TIMESTAMP '{end}'
      GROUP BY area_nm, fact_manage_nm, stack_code, item, ts_kst HAVING COUNT(*) > 1) t;

-- name: ratio_on_not_ok_by_status
-- 참고(0이 아니어도 정상): 대만은 status가 ok가 아니어도 ratio가 채워진 행이 있다(예: other_code). K-TMS는 0이다.
-- 그래서 ratio가 있다는 이유로 사용 가능한 값이라고 판단하면 안 되고, 지표는 반드시 status = 'ok'로 거른다.
SELECT status, item, COUNT(*) AS slots_with_ratio
FROM {silver}
WHERE status <> 'ok' AND ratio IS NOT NULL AND ts_kst >= TIMESTAMP '{start}' AND ts_kst < TIMESTAMP '{end}'
GROUP BY status, item ORDER BY status, item;
