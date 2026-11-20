-- 시멘틱 레이어: 에이전트·화면이 원본 표 대신 보는 뷰 (spec 012, 2026-11-19).
-- 지표 정의를 한 곳에 고정해, 조회 함수가 status 조건이나 사업장 연결을 빠뜨려도 틀린 값이 나오지 않게 한다.
-- 정의를 바꾸면 semantic_version을 올린다.

-- 지표 정의는 C의 scripts/silver_metric_queries.sql(사전 5.1절)과 같다: 진입 ≥ 90%, 초과 ≥ 100%, 극단값 > 200%.

-- 유효한 측정값: 정상 칸만.
CREATE OR REPLACE VIEW obs.v_valid_measurement AS
SELECT
  m.stack_key,
  m.item,
  m.measured_at,
  m.measured_at::date AS obs_date,
  m.value,
  m.limit_value,
  m.ratio_pct,
  m.ratio_pct >= 90  AS is_entry,
  m.ratio_pct >= 100 AS is_exceed,
  m.ratio_pct > 200  AS is_extreme,
  'v1'::text         AS semantic_version
FROM obs.measurement_30m m
WHERE m.status_code = 0;

-- 측정값(모든 상태) + 사업장 연결 + 상태 설명. 화면 시계열과 "그래프가 왜 비었나" 질문용.
CREATE OR REPLACE VIEW obs.v_measurement_site AS
SELECT
  m.stack_key,
  s.area_nm,
  s.fact_manage_nm,
  s.stack_code,
  s.site_id,
  s.frontend_stack_id,
  m.item,
  m.measured_at,
  m.measured_at::date AS obs_date,
  m.value,
  m.limit_value,
  m.ratio_pct,
  m.status_code,
  st.status,
  st.display_ko     AS status_display,
  st.explanation_ko AS status_explanation,
  st.counts_in_stats,
  m.loaded_at,
  'v1'::text        AS semantic_version
FROM obs.measurement_30m m
LEFT JOIN ref.v_stack s USING (stack_key)
JOIN ref.status_code st ON st.code = m.status_code;

GRANT SELECT ON obs.v_valid_measurement, obs.v_measurement_site TO tms_app, tms_loader;
