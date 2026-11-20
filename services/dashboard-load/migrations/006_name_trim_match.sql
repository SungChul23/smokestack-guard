-- 006: 사업장 이름 비교에서 앞뒤 공백을 무시한다 (2026-11-20 매핑 점검)
-- K-TMS 원본 이름 일부는 끝에 공백이 붙어 온다(예: "㈜지에스포천그린에너지 ").
-- 사업장 목록은 공백을 잘라 넣었으므로 글자가 달라 연결되지 않았다.
-- 원본 이름과 stack_key(Silver·ML-ready와 같은 규칙)는 그대로 두고, 연결할 때만 btrim으로 비교한다.
-- 열은 그대로라 뷰를 바꾸면 과거 관측까지 바로 사업장에 연결된다.

CREATE OR REPLACE VIEW ref.v_stack AS
SELECT s.*, n.site_id
FROM ref.stack s
LEFT JOIN LATERAL (
  SELECT m.site_id
  FROM ref.site_name_map m
  WHERE btrim(m.area_nm) = btrim(s.area_nm) AND btrim(m.fact_manage_nm) = btrim(s.fact_manage_nm)
  ORDER BY m.valid_from DESC
  LIMIT 1
) n ON true;

-- 이미 알린 이름 중 이제 연결되는 것은 해결로 표시한다.
UPDATE ops.unmapped_name u SET resolved_at = now()
WHERE resolved_at IS NULL
  AND EXISTS (SELECT 1 FROM ref.site_name_map n
              WHERE btrim(n.area_nm) = btrim(u.area_nm) AND btrim(n.fact_manage_nm) = btrim(u.fact_manage_nm));
