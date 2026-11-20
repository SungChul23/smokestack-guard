-- 기준 정보: 사업장, 이름 이력, 굴뚝, 상태 코드 (data-model §4).
-- 관측에는 사업장 코드를 저장하지 않는다. 굴뚝 → 사업장 코드는 이름 이력으로 읽을 때 찾는다.

CREATE TABLE IF NOT EXISTS ref.site (
  site_id           text PRIMARY KEY,          -- CleanSYS 사업체 코드
  display_name      text NOT NULL,
  region_sido       text,
  region_sigungu    text,
  address           text,
  lat               double precision,
  lon               double precision,
  coordinate_source text,
  source_version    text NOT NULL,             -- 사업장 목록 파일 버전
  loaded_at         timestamptz NOT NULL DEFAULT now()
);

-- (지역, 사업장 이름) → 사업장 코드. 이름이 바뀌면 새 이름 행을 추가한다. 옛 이름 행은 지우지 않는다.
CREATE TABLE IF NOT EXISTS ref.site_name_map (
  area_nm        text NOT NULL,
  fact_manage_nm text NOT NULL,
  valid_from     date NOT NULL,
  site_id        text NOT NULL REFERENCES ref.site (site_id),
  valid_to       date,
  confirmed_by   text NOT NULL,                -- auto | 사람 이름(역할)
  note           text,
  PRIMARY KEY (area_nm, fact_manage_nm, valid_from)
);

-- 굴뚝 키(ML-ready stack_code와 같은 규칙: 지역|사업장|굴뚝번호). 적재가 처음 본 키도 여기에 들어온다.
CREATE TABLE IF NOT EXISTS ref.stack (
  stack_key         text PRIMARY KEY,
  area_nm           text NOT NULL,
  fact_manage_nm    text NOT NULL,
  stack_code        text NOT NULL,
  frontend_stack_id text,                      -- 화면 id (KS-…)
  collision_flag    boolean NOT NULL DEFAULT false,
  source            text NOT NULL CHECK (source IN ('site_list', 'observed')),
  first_seen        date NOT NULL DEFAULT CURRENT_DATE
);

-- 굴뚝 키 → 사업장 코드. 같은 이름에 행이 여럿이면 가장 늦게 시작한 것을 쓴다.
CREATE OR REPLACE VIEW ref.v_stack AS
SELECT s.*, n.site_id
FROM ref.stack s
LEFT JOIN LATERAL (
  SELECT m.site_id
  FROM ref.site_name_map m
  WHERE m.area_nm = s.area_nm AND m.fact_manage_nm = s.fact_manage_nm
  ORDER BY m.valid_from DESC
  LIMIT 1
) n ON true;

CREATE TABLE IF NOT EXISTS ref.status_code (
  code            smallint PRIMARY KEY,
  status          text NOT NULL UNIQUE,         -- C의 Silver status 값
  source_text     text,
  display_ko      text NOT NULL,
  counts_in_stats boolean NOT NULL,
  explanation_ko  text                          -- 에이전트 설명 문구. C·B 확인 뒤 채운다
);

INSERT INTO ref.status_code (code, status, source_text, display_ko, counts_in_stats) VALUES
  (0,  'ok',            NULL,                     '값',       true),
  (1,  'stopped',       '측정자료확인중(가동중지)', '가동중지', false),
  (2,  'checking',      '측정자료확인중',          '확인중',   false),
  (3,  'no_signal',     '미수신',                  '미수신',   false),
  (4,  'maintenance',   '보수중',                  '보수중',   false),
  (5,  'inspection',    '기기점검',                '점검중',   false),
  (8,  'not_monitored', NULL,                      '미측정',   false),
  (9,  'ambiguous',     NULL,                      '확인 불가', false),
  (99, 'other',         NULL,                      '기타',     false)
ON CONFLICT (code) DO NOTHING;

GRANT SELECT ON ALL TABLES IN SCHEMA ref TO tms_loader, tms_app;
GRANT INSERT ON ref.stack TO tms_loader;
