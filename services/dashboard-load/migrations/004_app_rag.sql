-- D 앱이 채우는 공간: 사용자·대화(app), 법령 문서 벡터(rag). 구조만 만든다 (data-model §6).
-- 컬럼은 D의 제안(2026-11-18) 기준이며, D가 바꾸면 다음 번호 파일로 고친다.

CREATE TABLE IF NOT EXISTS app.user_favorite (
  user_sub   text NOT NULL,                     -- Cognito sub
  target     text NOT NULL,                     -- stack_key 또는 site_id
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_sub, target)
);

CREATE TABLE IF NOT EXISTS app.conversation (
  conversation_id text PRIMARY KEY,
  user_sub        text NOT NULL,
  started_at      timestamptz NOT NULL DEFAULT now(),
  last_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.message (
  conversation_id text NOT NULL REFERENCES app.conversation (conversation_id),
  seq             integer NOT NULL,
  role            text NOT NULL,
  body_masked     text NOT NULL,                -- 개인정보를 가린 본문
  evidence        jsonb,
  status          text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (conversation_id, seq)
);

CREATE TABLE IF NOT EXISTS app.query_log (
  request_id     text PRIMARY KEY,
  user_sub_hash  text,
  question_masked text,
  interpretation jsonb,
  route          text,
  latency_ms     jsonb,
  tokens         jsonb,
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag.doc_chunk (
  chunk_id       text PRIMARY KEY,
  collection     text NOT NULL,
  doc_id         text NOT NULL,
  law_name       text,
  article        text,
  effective_date date,
  text           text NOT NULL,
  text_tsv       tsvector,
  embedding      vector(1024),                  -- 임베딩 모델을 바꾸면 차원도 바꾼다
  source_ref     text,
  index_version  text NOT NULL                  -- 모델 ID와 차원을 포함
);
CREATE INDEX IF NOT EXISTS doc_chunk_tsv ON rag.doc_chunk USING gin (text_tsv);
CREATE INDEX IF NOT EXISTS doc_chunk_embedding ON rag.doc_chunk USING hnsw (embedding vector_cosine_ops);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO tms_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA rag TO tms_app;  -- 문서 색인은 D가 채운다
