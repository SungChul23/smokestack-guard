-- 스키마 5개, 벡터 검색 확장, 적재·앱 계정 (data-model §7).
-- 계정은 IAM 인증(rds_iam)으로만 로그인한다. 비밀번호를 만들지 않는다 (research R4).

CREATE SCHEMA IF NOT EXISTS ref;
CREATE SCHEMA IF NOT EXISTS obs;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS rag;

CREATE EXTENSION IF NOT EXISTS vector;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tms_loader') THEN
    CREATE ROLE tms_loader LOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tms_app') THEN
    CREATE ROLE tms_app LOGIN;
  END IF;
  -- rds_iam은 RDS에만 있다. 로컬 테스트 DB에서는 건너뛴다.
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rds_iam') THEN
    GRANT rds_iam TO tms_loader;
    GRANT rds_iam TO tms_app;
  END IF;
END
$$;

GRANT USAGE ON SCHEMA ref, obs, ops TO tms_loader;
GRANT USAGE ON SCHEMA ref, obs, rag TO tms_app;
GRANT USAGE, CREATE ON SCHEMA app TO tms_app;
