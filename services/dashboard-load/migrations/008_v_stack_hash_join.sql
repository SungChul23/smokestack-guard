-- 008: ref.v_stack을 같은 규칙으로 빠르게 계산한다 (2026-11-26 /api/sites·/api/day 지연)
--
-- 007의 뷰는 굴뚝마다 이름 이력 전체를 훑고(btrim 때문에 PK 인덱스 못 씀), 비교 키(ref.name_key)도
-- 정확한 이름을 이미 찾은 굴뚝까지 모두 계산한 뒤 버렸다. 운영 DB(굴뚝 2,929, 이름 이력 910)에서
-- 뷰 한 번에 약 2.9초(정규식 약 270만 번)였고, /api/sites는 이 뷰를 두 번, /api/day는 한 번 읽는다.
--
-- 이름 이력을 먼저 한 번만 정리(정확한 이름표, 비교 키표)한 뒤 해시 조인으로 붙인다.
-- 연결 규칙은 007과 같다:
--   1) 시·도와 이름이 같으면(앞뒤 공백 무시) 그 이름의 가장 늦게 시작한 행
--   2) 없으면 같은 시·도에서 비교 키가 같은 사업장이 1곳일 때만
-- 열 이름·순서가 같아 이 뷰를 쓰는 005 뷰와 API는 그대로 동작한다. 되돌리기: 007의 CREATE VIEW를 다시 실행.

CREATE OR REPLACE VIEW ref.v_stack AS
WITH exact_name AS (
  SELECT DISTINCT ON (btrim(area_nm), btrim(fact_manage_nm))
         btrim(area_nm) AS area_key, btrim(fact_manage_nm) AS name_key, site_id
  FROM ref.site_name_map
  ORDER BY btrim(area_nm), btrim(fact_manage_nm), valid_from DESC
), loose_name AS (
  SELECT btrim(area_nm) AS area_key, ref.name_key(fact_manage_nm) AS name_key, min(site_id) AS site_id
  FROM ref.site_name_map
  GROUP BY 1, 2
  HAVING count(DISTINCT site_id) = 1
)
SELECT s.*,
       coalesce(e.site_id, k.site_id) AS site_id,
       CASE WHEN e.site_id IS NOT NULL THEN 'exact'
            WHEN k.site_id IS NOT NULL THEN 'name_key' END AS site_match
FROM ref.stack s
LEFT JOIN exact_name e
  ON e.area_key = btrim(s.area_nm) AND e.name_key = btrim(s.fact_manage_nm)
LEFT JOIN loose_name k
  ON e.site_id IS NULL AND k.area_key = btrim(s.area_nm) AND k.name_key = ref.name_key(s.fact_manage_nm);
