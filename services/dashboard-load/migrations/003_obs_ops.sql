-- 관측(30분), 일일 요약 2개, 적재 운영 기록 (data-model §1~3, §5).
-- 시각은 KST 벽시계 timestamp(시간대 없음). Silver ts_kst와 같다.
-- 지표 정의는 C의 scripts/silver_metric_queries.sql(용어·산식 사전 5.1절)을 따른다:
--   진입(entry) = 정상 칸 중 비율 ≥ 90%, 초과(exceed) = 비율 ≥ 100%, 극단값(extreme) = 비율 > 200%.

CREATE TABLE IF NOT EXISTS obs.measurement_30m (
  stack_key   text NOT NULL,
  item        text NOT NULL CHECK (item IN ('nox', 'sox')),
  measured_at timestamp NOT NULL,
  value       double precision,                -- 상태 행은 null (0으로 채우지 않음)
  limit_value double precision,
  ratio_pct   double precision,                -- 100 = 허용기준
  status_code smallint NOT NULL REFERENCES ref.status_code (code),
  load_path   text NOT NULL CHECK (load_path IN ('recent', 'backfill')),
  loaded_at   timestamptz NOT NULL,
  PRIMARY KEY (stack_key, item, measured_at)
);
CREATE INDEX IF NOT EXISTS measurement_30m_measured_at ON obs.measurement_30m (measured_at);
CREATE INDEX IF NOT EXISTS measurement_30m_loaded_at ON obs.measurement_30m (loaded_at);

CREATE TABLE IF NOT EXISTS obs.daily_stack_summary (
  stack_key       text NOT NULL,
  item            text NOT NULL,
  obs_date        date NOT NULL,
  slots_expected  smallint NOT NULL,
  n_ok            integer NOT NULL,
  n_zero          integer NOT NULL,
  n_stopped       integer NOT NULL,
  n_checking      integer NOT NULL,
  n_no_signal     integer NOT NULL,
  n_maintenance   integer NOT NULL,
  n_inspection    integer NOT NULL,
  n_not_monitored integer NOT NULL,
  n_ambiguous     integer NOT NULL,
  n_other         integer NOT NULL,
  n_missing       integer NOT NULL,              -- 행 자체가 없는 칸
  mean_value      double precision,
  max_value       double precision,
  max_at          timestamp,
  min_value       double precision,
  mean_ratio_pct  double precision,
  max_ratio_pct   double precision,
  n_entry         integer NOT NULL,              -- 비율 ≥ 90%
  n_exceed        integer NOT NULL,              -- 비율 ≥ 100%
  n_extreme       integer NOT NULL,              -- 비율 > 200%
  mean_ratio_pct_ex_extreme double precision,    -- 극단값 뺀 평균 (사전 보고 규칙)
  max_ratio_pct_ex_extreme  double precision,
  limit_min       double precision,
  limit_max       double precision,
  computed_at     timestamptz NOT NULL,
  PRIMARY KEY (stack_key, item, obs_date)
);

CREATE TABLE IF NOT EXISTS obs.daily_national_summary (
  obs_date           date NOT NULL,
  item               text NOT NULL,
  max_ratio_pct      double precision,
  max_stack_key      text,
  max_at             timestamp,
  max_value          double precision,
  mean_ratio_pct     double precision,
  n_stacks_reporting integer NOT NULL,
  n_stacks_entry     integer NOT NULL,           -- 그날 진입(≥ 90%)이 한 번이라도 있었던 굴뚝 수
  n_stacks_exceed    integer NOT NULL,           -- 그날 초과(≥ 100%)가 한 번이라도 있었던 굴뚝 수
  computed_at        timestamptz NOT NULL,
  PRIMARY KEY (obs_date, item)
);

CREATE TABLE IF NOT EXISTS ops.load_run (
  run_id         text PRIMARY KEY,
  mode           text NOT NULL,
  started_at     timestamptz NOT NULL,
  finished_at    timestamptz NOT NULL,
  source_range   jsonb,
  rows_read      integer NOT NULL DEFAULT 0,
  rows_upserted  integer NOT NULL DEFAULT 0,
  rows_unchanged integer NOT NULL DEFAULT 0,
  new_stack_keys integer NOT NULL DEFAULT 0,
  summary_days   date[],
  result         text NOT NULL
);

CREATE TABLE IF NOT EXISTS ops.mapping_report (
  report_date date NOT NULL,
  check_type  text NOT NULL CHECK (check_type IN ('A', 'B', 'C')),  -- A 미연결 이름 · B 관측 없는 굴뚝 · C 새 굴뚝
  n_items     integer NOT NULL,
  detail      jsonb NOT NULL,
  computed_at timestamptz NOT NULL,
  PRIMARY KEY (report_date, check_type)
);

CREATE TABLE IF NOT EXISTS ops.unmapped_name (
  area_nm        text NOT NULL,
  fact_manage_nm text NOT NULL,
  first_seen     date NOT NULL,
  alerted_at     timestamptz,
  resolved_at    timestamptz,
  PRIMARY KEY (area_nm, fact_manage_nm)
);

GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA obs TO tms_loader;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA ops TO tms_loader;
GRANT SELECT ON ALL TABLES IN SCHEMA obs TO tms_app;
