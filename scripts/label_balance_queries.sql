-- 실측 + 합성 K-TMS ML-ready 양성·음성 비율 (specs/a-platform/011-synthetic-train-s3-ingest T031)
-- Athena(워크그룹 tms-eda, DB tms_silver2). Terraform이 "-- name:" 단위로 저장된 쿼리로 등록한다(실행은 사람이).
-- 자리표시자: {start}, {end} = KST 측정일(양 끝 포함, YYYY-MM-DD).
-- 학습에 쓴 버전으로 보려면 두 테이블 이름 뒤에 FOR VERSION AS OF <snapshot_id>를 붙인다.
-- 양성 = label_entry_60m = 1 (지금 90% 미만, 60분 안에 90% 이상), 분류 적격 행(classification_eligible)만 센다.

-- name: balance_by_source
-- 출처 × 성분별 적격 행, 양성, 음성, 양성 비율(%)
SELECT data_source, item_code,
       COUNT(*)                                             AS eligible_rows,
       SUM(CASE WHEN label_entry_60m = 1 THEN 1 ELSE 0 END) AS positives,
       SUM(CASE WHEN label_entry_60m = 0 THEN 1 ELSE 0 END) AS negatives,
       ROUND(100.0 * SUM(CASE WHEN label_entry_60m = 1 THEN 1 ELSE 0 END) / COUNT(*), 3) AS positive_pct
FROM (SELECT data_source, item_code, measured_at, label_entry_60m FROM tms_silver2.ktms_ml_ready WHERE classification_eligible
      UNION ALL
      SELECT data_source, item_code, measured_at, label_entry_60m FROM tms_silver2.ktms_synth_ml_ready WHERE classification_eligible) t
WHERE measured_at >= TIMESTAMP '{start} 00:00:00' AND measured_at < TIMESTAMP '{end} 00:00:00' + INTERVAL '1' DAY
GROUP BY data_source, item_code
ORDER BY item_code, data_source;

-- name: balance_combined
-- 성분별 실측 단독 vs 실측+합성 양성 비율과 양성 증가 배수(설계 기준 약 2배, SC-007)
WITH t AS (
  SELECT data_source, item_code, label_entry_60m FROM tms_silver2.ktms_ml_ready
  WHERE classification_eligible AND measured_at >= TIMESTAMP '{start} 00:00:00' AND measured_at < TIMESTAMP '{end} 00:00:00' + INTERVAL '1' DAY
  UNION ALL
  SELECT data_source, item_code, label_entry_60m FROM tms_silver2.ktms_synth_ml_ready
  WHERE classification_eligible AND measured_at >= TIMESTAMP '{start} 00:00:00' AND measured_at < TIMESTAMP '{end} 00:00:00' + INTERVAL '1' DAY
), s AS (
  SELECT item_code,
         SUM(CASE WHEN data_source = 'ktms' THEN 1 ELSE 0 END)                             AS real_rows,
         SUM(CASE WHEN data_source = 'ktms' AND label_entry_60m = 1 THEN 1 ELSE 0 END)     AS real_pos,
         SUM(CASE WHEN data_source = 'ktms_synth' THEN 1 ELSE 0 END)                       AS synth_rows,
         SUM(CASE WHEN data_source = 'ktms_synth' AND label_entry_60m = 1 THEN 1 ELSE 0 END) AS synth_pos
  FROM t GROUP BY item_code
)
SELECT item_code, real_rows, real_pos, synth_rows, synth_pos,
       ROUND(100.0 * real_pos / NULLIF(real_rows, 0), 3)                                   AS real_positive_pct,
       ROUND(100.0 * (real_pos + synth_pos) / NULLIF(real_rows + synth_rows, 0), 3)        AS combined_positive_pct,
       ROUND(CAST(real_pos + synth_pos AS DOUBLE) / NULLIF(real_pos, 0), 2)                AS positive_multiplier,
       ROUND(CAST(synth_pos AS DOUBLE) / NULLIF(real_pos, 0), 2)                           AS synth_to_real_ratio
FROM s ORDER BY item_code;

-- name: synth_by_shape
-- 합성 모양별 양성 수. 굴뚝 키(시도|사업장|굴뚝)의 굴뚝 코드 SYN-T-<날짜>-<성분>-<모양>-<번호>에서 모양을 꺼낸다
SELECT item_code,
       regexp_extract(stack_code, 'SYN-T-[0-9]{8}-[A-Z]+-([A-Z]+)-[0-9]+', 1) AS shape,
       COUNT(DISTINCT stack_code)                            AS episodes,
       COUNT(*)                                              AS eligible_rows,
       SUM(CASE WHEN label_entry_60m = 1 THEN 1 ELSE 0 END)  AS positives
FROM tms_silver2.ktms_synth_ml_ready
WHERE classification_eligible
  AND measured_at >= TIMESTAMP '{start} 00:00:00' AND measured_at < TIMESTAMP '{end} 00:00:00' + INTERVAL '1' DAY
GROUP BY 1, 2
ORDER BY item_code, positives;

-- name: balance_by_day
-- 측정일 × 출처 × 성분별 양성 수 추이(합성이 매일 실측과 비슷하게 들어오는지)
SELECT date(measured_at) AS day, data_source, item_code,
       COUNT(*)                                              AS eligible_rows,
       SUM(CASE WHEN label_entry_60m = 1 THEN 1 ELSE 0 END)  AS positives
FROM (SELECT data_source, item_code, measured_at, label_entry_60m FROM tms_silver2.ktms_ml_ready WHERE classification_eligible
      UNION ALL
      SELECT data_source, item_code, measured_at, label_entry_60m FROM tms_silver2.ktms_synth_ml_ready WHERE classification_eligible) t
WHERE measured_at >= TIMESTAMP '{start} 00:00:00' AND measured_at < TIMESTAMP '{end} 00:00:00' + INTERVAL '1' DAY
GROUP BY 1, 2, 3
ORDER BY day, item_code, data_source;
