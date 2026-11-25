-- 007: 사업장 이름 비교에서 법인 표기와 공백을 무시한다 (2026-11-24 매핑 메일)
-- K-TMS 원본 이름은 법인 표기 위치가 바뀌어 오기도 한다(예: "(주)티와이코퍼레이션" ↔ "티와이코퍼레이션(주)").
-- 원본 이름과 stack_key는 그대로 두고, 연결할 때만 비교용 키(ref.name_key)로 한 번 더 찾는다.
--   1) 지금처럼 정확히 같은 이름(앞뒤 공백 무시, 006)이 있으면 그것을 쓴다.
--   2) 없으면 같은 시·도에서 name_key가 같은 이름 이력을 찾는다. 사업장이 딱 1곳일 때만 연결한다
--      (둘 이상이면 연결하지 않고 지금처럼 미연결 이름으로 알린다. 동명 사업장 원칙과 같다).
-- 열을 끝에 하나(site_match) 더할 뿐이라 이 뷰를 쓰는 뷰(005)는 그대로 동작하고, 과거 관측까지 바로 연결된다.

CREATE OR REPLACE FUNCTION ref.name_key(t text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT regexp_replace(
           regexp_replace(coalesce(t, ''), '\s+', '', 'g'),
           '[(（]\s*[주유재사]\s*[)）]|㈜|주식회사|유한회사|재단법인|사단법인', '', 'g')
$$;

CREATE OR REPLACE VIEW ref.v_stack AS
SELECT s.*,
       coalesce(e.site_id, k.site_id) AS site_id,
       CASE WHEN e.site_id IS NOT NULL THEN 'exact'
            WHEN k.site_id IS NOT NULL THEN 'name_key' END AS site_match
FROM ref.stack s
LEFT JOIN LATERAL (
  SELECT m.site_id
  FROM ref.site_name_map m
  WHERE btrim(m.area_nm) = btrim(s.area_nm) AND btrim(m.fact_manage_nm) = btrim(s.fact_manage_nm)
  ORDER BY m.valid_from DESC
  LIMIT 1
) e ON true
LEFT JOIN LATERAL (
  SELECT min(m.site_id) AS site_id
  FROM ref.site_name_map m
  WHERE btrim(m.area_nm) = btrim(s.area_nm) AND ref.name_key(m.fact_manage_nm) = ref.name_key(s.fact_manage_nm)
  HAVING count(DISTINCT m.site_id) = 1
) k ON e.site_id IS NULL;

-- 점검 D: 법인 표기 차이로 자동 연결한 이름(메일은 보내지 않고 기록만)
ALTER TABLE ops.mapping_report DROP CONSTRAINT IF EXISTS mapping_report_check_type_check;
ALTER TABLE ops.mapping_report ADD CONSTRAINT mapping_report_check_type_check
  CHECK (check_type IN ('A', 'B', 'C', 'D'));

-- 이미 알린 이름 중 이제 연결되는 것은 해결로 표시한다.
UPDATE ops.unmapped_name u SET resolved_at = now()
WHERE resolved_at IS NULL
  AND EXISTS (SELECT 1 FROM ref.v_stack s
              WHERE s.area_nm = u.area_nm AND s.fact_manage_nm = u.fact_manage_nm AND s.site_id IS NOT NULL);
