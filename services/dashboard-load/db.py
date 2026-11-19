"""RDS 접속과 쓰기 (spec 012, research R4·R5·R10).

- 적재 계정(tms_loader)은 IAM 인증 토큰으로 접속한다. 토큰 생성은 로컬 서명이라 네트워크 호출이 없다.
- 쓰기는 임시 표에 넣은 뒤 키 기준 UPSERT. 값이 같으면 갱신하지 않는다(loaded_at 유지).
"""
from __future__ import annotations

import json
import math
import ssl
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pg8000.native

CA_BUNDLE = Path(__file__).resolve().parent / "certs" / "global-bundle.pem"
DB_NAME = "tms"
CHUNK = 10_000
SLOTS_PER_DAY = 48


# ---------------------------------------------------------------------------
# 접속
# ---------------------------------------------------------------------------


def ssl_context(verify_hostname: bool = True) -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=str(CA_BUNDLE))
    ctx.check_hostname = verify_hostname  # 베스천 터널(localhost)은 이름이 달라 CA만 검증한다
    return ctx


def iam_token(host: str, port: int, user: str, region: str) -> str:
    import boto3

    return boto3.client("rds", region_name=region).generate_db_auth_token(
        DBHostname=host, Port=port, DBUsername=user, Region=region
    )


def connect(
    host: str,
    port: int,
    user: str,
    *,
    password: str | None = None,
    region: str = "ap-northeast-2",
    database: str = DB_NAME,
    tls: ssl.SSLContext | bool | None = True,
    timeout: int = 60,
) -> pg8000.native.Connection:
    """password가 없으면 IAM 토큰을 만든다. tls=False는 로컬 테스트 DB에서만 쓴다."""
    if password is None:
        password = iam_token(host, port, user, region)
    if tls is True:
        tls = ssl_context()
    return pg8000.native.Connection(
        user, host=host, port=port, database=database, password=password,
        ssl_context=tls or None, timeout=timeout,
    )


# ---------------------------------------------------------------------------
# 마이그레이션
# ---------------------------------------------------------------------------


def split_sql(text: str) -> list[str]:
    """`;`로 문장을 나눈다. `$$ … $$` 안과 `--` 주석 안의 `;`는 무시한다."""
    stmts, buf, i, in_dollar = [], [], 0, False
    while i < len(text):
        if not in_dollar and text.startswith("--", i):
            j = text.find("\n", i)
            i = len(text) if j == -1 else j
            continue
        if text.startswith("$$", i):
            in_dollar = not in_dollar
            buf.append("$$")
            i += 2
            continue
        ch = text[i]
        if ch == ";" and not in_dollar:
            stmt = "".join(buf).strip()
            if stmt:
                stmts.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


def applied_migrations(conn) -> set[str]:
    conn.run("CREATE SCHEMA IF NOT EXISTS ops")
    conn.run(
        "CREATE TABLE IF NOT EXISTS ops.schema_migrations "
        "(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
    )
    return {r[0] for r in conn.run("SELECT version FROM ops.schema_migrations")}


def migrate(conn, folder: Path, dry_run: bool = False) -> list[str]:
    """번호순으로 적용 안 된 파일만, 파일마다 한 트랜잭션."""
    done = applied_migrations(conn)
    todo = [p for p in sorted(folder.glob("*.sql")) if p.stem not in done]
    if dry_run:
        return [p.name for p in todo]
    for p in todo:
        conn.run("BEGIN")
        try:
            for stmt in split_sql(p.read_text(encoding="utf-8")):
                conn.run(stmt)
            conn.run("INSERT INTO ops.schema_migrations (version) VALUES (:v)", v=p.stem)
            conn.run("COMMIT")
        except Exception:
            conn.run("ROLLBACK")
            raise
    return [p.name for p in todo]


# ---------------------------------------------------------------------------
# 관측 UPSERT
# ---------------------------------------------------------------------------


def _clean(values: Iterable) -> list:
    """NaN·NaT → None (pg8000이 null로 보낸다)."""
    out = []
    for v in values:
        if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NaT:
            out.append(None)
        elif isinstance(v, pd.Timestamp):
            out.append(v.to_pydatetime())
        else:
            out.append(v)
    return out


_UPSERT = """
INSERT INTO obs.measurement_30m AS m
  (stack_key, item, measured_at, value, limit_value, ratio_pct, status_code, load_path, loaded_at)
SELECT k, it, ts, v, l, r, s, :path, :now
FROM unnest(CAST(:k AS text[]), CAST(:it AS text[]), CAST(:ts AS timestamp[]),
            CAST(:v AS float8[]), CAST(:l AS float8[]), CAST(:r AS float8[]), CAST(:s AS int2[]))
     AS t(k, it, ts, v, l, r, s)
ON CONFLICT (stack_key, item, measured_at) DO UPDATE SET
  value = EXCLUDED.value, limit_value = EXCLUDED.limit_value, ratio_pct = EXCLUDED.ratio_pct,
  status_code = EXCLUDED.status_code, load_path = EXCLUDED.load_path, loaded_at = EXCLUDED.loaded_at
WHERE (m.value, m.limit_value, m.ratio_pct, m.status_code)
      IS DISTINCT FROM (EXCLUDED.value, EXCLUDED.limit_value, EXCLUDED.ratio_pct, EXCLUDED.status_code)
RETURNING 1
"""

_ADD_STACKS = """
INSERT INTO ref.stack (stack_key, area_nm, fact_manage_nm, stack_code, source, first_seen)
SELECT DISTINCT k, a, f, c, 'observed', CAST(:day AS date)
FROM unnest(CAST(:k AS text[]), CAST(:a AS text[]), CAST(:f AS text[]), CAST(:c AS text[])) AS t(k, a, f, c)
ON CONFLICT (stack_key) DO NOTHING
RETURNING 1
"""


def upsert_measurements(conn, rows: pd.DataFrame, load_path: str, now: datetime) -> tuple[int, int]:
    """(바뀌거나 새로 들어간 행 수, 그대로인 행 수). 한 트랜잭션."""
    if rows.empty:
        return 0, 0
    changed = 0
    conn.run("BEGIN")
    try:
        for i in range(0, len(rows), CHUNK):
            part = rows.iloc[i : i + CHUNK]
            res = conn.run(
                _UPSERT,
                k=list(part["stack_key"]), it=list(part["item"]),
                ts=_clean(part["measured_at"]), v=_clean(part["value"]),
                l=_clean(part["limit_value"]), r=_clean(part["ratio_pct"]),
                s=[int(x) for x in part["status_code"]], path=load_path, now=now,
            )
            changed += len(res)
        conn.run("COMMIT")
    except Exception:
        conn.run("ROLLBACK")
        raise
    return changed, len(rows) - changed


def add_stack_keys(conn, rows: pd.DataFrame, day: date) -> int:
    """처음 본 굴뚝 키를 ref.stack에 source=observed로 추가한다(사업장 코드는 이름 이력으로 연결)."""
    if rows.empty:
        return 0
    keys = rows.drop_duplicates("stack_key")
    res = conn.run(
        _ADD_STACKS, k=list(keys["stack_key"]), a=list(keys["area_nm"]),
        f=list(keys["fact_manage_nm"]), c=list(keys["stack_code"]), day=day,
    )
    return len(res)


# ---------------------------------------------------------------------------
# 일일 요약
# ---------------------------------------------------------------------------

_STATUS_COUNTS = [
    ("n_stopped", 1), ("n_checking", 2), ("n_no_signal", 3), ("n_maintenance", 4),
    ("n_inspection", 5), ("n_not_monitored", 8), ("n_ambiguous", 9), ("n_other", 99),
]
_STACK_COLS = [
    "slots_expected", "n_ok", "n_zero", *[c for c, _ in _STATUS_COUNTS], "n_missing",
    "mean_value", "max_value", "max_at", "min_value", "mean_ratio_pct", "max_ratio_pct",
    "n_entry", "n_exceed", "n_extreme", "mean_ratio_pct_ex_extreme", "max_ratio_pct_ex_extreme",
    "limit_min", "limit_max", "computed_at",
]
_OK = "status_code = 0"
_STACK_SUMMARY = f"""
WITH d AS (SELECT unnest(CAST(:days AS date[])) AS obs_date),
m AS (
  SELECT m.*, d.obs_date FROM obs.measurement_30m m
  JOIN d ON m.measured_at >= d.obs_date AND m.measured_at < d.obs_date + 1
)
INSERT INTO obs.daily_stack_summary (stack_key, item, obs_date, {", ".join(_STACK_COLS)})
SELECT stack_key, item, obs_date, {SLOTS_PER_DAY},
  count(*) FILTER (WHERE {_OK}),
  count(*) FILTER (WHERE {_OK} AND value = 0),
  {", ".join(f"count(*) FILTER (WHERE status_code = {code})" for _, code in _STATUS_COUNTS)},
  GREATEST({SLOTS_PER_DAY} - count(*), 0),
  avg(value) FILTER (WHERE {_OK}),
  max(value) FILTER (WHERE {_OK}),
  (array_agg(measured_at ORDER BY value DESC, measured_at) FILTER (WHERE {_OK} AND value IS NOT NULL))[1],
  min(value) FILTER (WHERE {_OK}),
  avg(ratio_pct) FILTER (WHERE {_OK}),
  max(ratio_pct) FILTER (WHERE {_OK}),
  count(*) FILTER (WHERE {_OK} AND ratio_pct >= 90),
  count(*) FILTER (WHERE {_OK} AND ratio_pct >= 100),
  count(*) FILTER (WHERE {_OK} AND ratio_pct > 200),
  avg(ratio_pct) FILTER (WHERE {_OK} AND ratio_pct <= 200),
  max(ratio_pct) FILTER (WHERE {_OK} AND ratio_pct <= 200),
  min(limit_value), max(limit_value), :now
FROM m GROUP BY stack_key, item, obs_date
ON CONFLICT (stack_key, item, obs_date) DO UPDATE SET
  {", ".join(f"{c} = EXCLUDED.{c}" for c in _STACK_COLS)}
"""
_NATIONAL_COLS = [
    "max_ratio_pct", "max_stack_key", "max_at", "max_value", "mean_ratio_pct",
    "n_stacks_reporting", "n_stacks_entry", "n_stacks_exceed", "computed_at",
]
_ORDER = "ratio_pct DESC NULLS LAST, measured_at, stack_key"
_NATIONAL_SUMMARY = f"""
WITH d AS (SELECT unnest(CAST(:days AS date[])) AS obs_date),
s AS (
  SELECT m.*, d.obs_date FROM obs.measurement_30m m
  JOIN d ON m.measured_at >= d.obs_date AND m.measured_at < d.obs_date + 1
  WHERE m.{_OK}
)
INSERT INTO obs.daily_national_summary (obs_date, item, {", ".join(_NATIONAL_COLS)})
SELECT obs_date, item,
  (array_agg(ratio_pct ORDER BY {_ORDER}))[1],
  (array_agg(stack_key ORDER BY {_ORDER}))[1],
  (array_agg(measured_at ORDER BY {_ORDER}))[1],
  (array_agg(value ORDER BY {_ORDER}))[1],
  avg(ratio_pct),
  count(DISTINCT stack_key),
  count(DISTINCT stack_key) FILTER (WHERE ratio_pct >= 90),
  count(DISTINCT stack_key) FILTER (WHERE ratio_pct >= 100),
  :now
FROM s GROUP BY obs_date, item
ON CONFLICT (obs_date, item) DO UPDATE SET
  {", ".join(f"{c} = EXCLUDED.{c}" for c in _NATIONAL_COLS)}
"""


def refresh_daily_summaries(conn, days: list[date], now: datetime) -> None:
    """관측 행은 읽기만 한다. 요약 두 표만 쓴다(FR-008·009)."""
    if not days:
        return
    conn.run("BEGIN")
    try:
        conn.run(_STACK_SUMMARY, days=days, now=now)
        conn.run(_NATIONAL_SUMMARY, days=days, now=now)
        conn.run("COMMIT")
    except Exception:
        conn.run("ROLLBACK")
        raise


def summary_days(conn, today: date) -> list[date]:
    """최근 2일(어제·그제, KST) + 직전 daily 이후 관측이 바뀐 날짜(오늘 제외) (FR-009)."""
    days = {date.fromordinal(today.toordinal() - 1), date.fromordinal(today.toordinal() - 2)}
    last = conn.run(
        "SELECT max(started_at) FROM ops.load_run WHERE mode = 'daily' AND result = 'succeeded'"
    )[0][0]
    if last is not None:
        rows = conn.run(
            "SELECT DISTINCT measured_at::date FROM obs.measurement_30m "
            "WHERE loaded_at >= :since AND measured_at < :today",
            since=last, today=today,
        )
        days |= {r[0] for r in rows}
    return sorted(days)


# ---------------------------------------------------------------------------
# 매핑 점검
# ---------------------------------------------------------------------------

_UNMAPPED = """
SELECT DISTINCT s.area_nm, s.fact_manage_nm
FROM obs.measurement_30m m JOIN ref.v_stack s USING (stack_key)
WHERE m.measured_at >= :day AND m.measured_at < CAST(:day AS date) + 1 AND s.site_id IS NULL
ORDER BY 1, 2
"""
_SILENT = """
SELECT s.stack_key FROM ref.stack s
WHERE s.source = 'site_list' AND NOT EXISTS (
  SELECT 1 FROM obs.measurement_30m m
  WHERE m.stack_key = s.stack_key AND m.measured_at >= :day AND m.measured_at < CAST(:day AS date) + 1)
ORDER BY 1
"""
_NEW_STACKS = "SELECT stack_key FROM ref.stack WHERE source = 'observed' AND first_seen = :day ORDER BY 1"
_REPORT = """
INSERT INTO ops.mapping_report (report_date, check_type, n_items, detail, computed_at)
VALUES (:day, :t, :n, CAST(:detail AS jsonb), :now)
ON CONFLICT (report_date, check_type) DO UPDATE SET
  n_items = EXCLUDED.n_items, detail = EXCLUDED.detail, computed_at = EXCLUDED.computed_at
"""
DETAIL_LIMIT = 200


def mapping_check(conn, day: date, now: datetime) -> list[dict]:
    """그날 관측에 나왔는데 이름 이력에 없는 (지역, 사업장) 중 처음 본 것만 돌려준다(FR-010).

    점검 A(미연결 이름)·B(관측 없는 목록 굴뚝)·C(새 굴뚝)는 ops.mapping_report에 남긴다.
    """
    unmapped = [tuple(r) for r in conn.run(_UNMAPPED, day=day)]
    silent = [r[0] for r in conn.run(_SILENT, day=day)]
    new_stacks = [r[0] for r in conn.run(_NEW_STACKS, day=day)]
    conn.run("BEGIN")
    try:
        new_names = []
        for area, fact in unmapped:
            res = conn.run(
                "INSERT INTO ops.unmapped_name (area_nm, fact_manage_nm, first_seen, alerted_at) "
                "VALUES (:a, :f, :day, :now) ON CONFLICT DO NOTHING RETURNING 1",
                a=area, f=fact, day=day, now=now,
            )
            if res:
                new_names.append({"area_nm": area, "fact_manage_nm": fact})
        conn.run(
            "UPDATE ops.unmapped_name u SET resolved_at = :now WHERE resolved_at IS NULL "
            "AND EXISTS (SELECT 1 FROM ref.site_name_map n "
            "WHERE n.area_nm = u.area_nm AND n.fact_manage_nm = u.fact_manage_nm)",
            now=now,
        )
        for t, items in (("A", [list(x) for x in unmapped]), ("B", silent), ("C", new_stacks)):
            conn.run(_REPORT, day=day, t=t, n=len(items),
                     detail=json.dumps(items[:DETAIL_LIMIT], ensure_ascii=False), now=now)
        conn.run("COMMIT")
    except Exception:
        conn.run("ROLLBACK")
        raise
    return new_names


# ---------------------------------------------------------------------------
# 실행 기록
# ---------------------------------------------------------------------------


def record_run(conn, run: dict) -> None:
    conn.run(
        """INSERT INTO ops.load_run (run_id, mode, started_at, finished_at, source_range,
             rows_read, rows_upserted, rows_unchanged, new_stack_keys, summary_days, result)
           VALUES (:run_id, :mode, :started_at, :finished_at, CAST(:source AS jsonb),
             :read, :upserted, :unchanged, :new_keys, CAST(:days AS date[]), :result)
           ON CONFLICT (run_id) DO NOTHING""",
        run_id=run["run_id"], mode=run["mode"], started_at=run["started_at"],
        finished_at=run["finished_at"], source=json.dumps(run.get("source", {}), ensure_ascii=False),
        read=run["rows"]["read"], upserted=run["rows"]["upserted"],
        unchanged=run["rows"]["unchanged"], new_keys=run.get("new_stack_keys", 0),
        days=[date.fromisoformat(d) for d in run.get("summary_days", [])], result=run["result"],
    )


# ---------------------------------------------------------------------------
# 사업장 목록 → ref (사람, 베스천 터널)
# ---------------------------------------------------------------------------

SITE_COLUMNS = [
    "site_id", "area_nm", "fact_manage_nm", "display_name", "region_sigungu", "address",
    "lat", "lon", "coordinate_source", "stack_code", "frontend_stack_id", "mapping_status",
]
SITE_FIELDS = ["display_name", "area_nm", "region_sigungu", "address", "lat", "lon", "coordinate_source"]
INITIAL_VALID_FROM = date(2000, 1, 1)


def validate_sites(df: pd.DataFrame) -> pd.DataFrame:
    """contracts §4. 한 줄 = 굴뚝 하나, 같은 site_id의 사업장 정보는 같아야 한다."""
    missing = [c for c in SITE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"사업장 목록에 없는 컬럼: {missing}")
    df = df[SITE_COLUMNS].copy()
    for c in ["site_id", "area_nm", "fact_manage_nm", "stack_code"]:
        df[c] = df[c].astype(str).str.strip()
    bad = df.groupby("site_id")[SITE_FIELDS].nunique(dropna=False).gt(1).any(axis=1)
    if bad.any():
        raise ValueError(f"같은 site_id인데 사업장 정보가 다름: {sorted(bad[bad].index)[:10]}")
    if not set(df["mapping_status"]).issubset({"auto", "confirmed", "unobserved"}):
        raise ValueError("mapping_status는 auto / confirmed / unobserved")
    df["stack_key"] = df["area_nm"] + "|" + df["fact_manage_nm"] + "|" + df["stack_code"]
    if df["stack_key"].duplicated().any():
        raise ValueError("같은 (지역, 사업장, 굴뚝 번호)가 여러 줄")
    return df


def load_ref(conn, df: pd.DataFrame, version: str) -> dict:
    """ref.site · ref.site_name_map · ref.stack(source=site_list). 같은 파일로 다시 돌려도 같다."""
    df = validate_sites(df)
    sites = df.drop_duplicates("site_id")
    names = df.drop_duplicates(["area_nm", "fact_manage_nm", "site_id"])
    conn.run("BEGIN")
    try:
        for r in sites.itertuples(index=False):
            conn.run(
                """INSERT INTO ref.site (site_id, display_name, region_sido, region_sigungu, address,
                     lat, lon, coordinate_source, source_version)
                   VALUES (:id, :name, :sido, :sgg, :addr, :lat, :lon, :src, :ver)
                   ON CONFLICT (site_id) DO UPDATE SET display_name = EXCLUDED.display_name,
                     region_sido = EXCLUDED.region_sido, region_sigungu = EXCLUDED.region_sigungu,
                     address = EXCLUDED.address, lat = EXCLUDED.lat, lon = EXCLUDED.lon,
                     coordinate_source = EXCLUDED.coordinate_source,
                     source_version = EXCLUDED.source_version, loaded_at = now()""",
                id=r.site_id, name=r.display_name, sido=r.area_nm, sgg=_clean([r.region_sigungu])[0],
                addr=_clean([r.address])[0], lat=_clean([float(r.lat)])[0], lon=_clean([float(r.lon)])[0],
                src=_clean([r.coordinate_source])[0], ver=version,
            )
        for r in names.itertuples(index=False):
            conn.run(
                """INSERT INTO ref.site_name_map (area_nm, fact_manage_nm, valid_from, site_id, confirmed_by, note)
                   VALUES (:a, :f, :vf, :id, :by, :note)
                   ON CONFLICT (area_nm, fact_manage_nm, valid_from) DO UPDATE SET
                     site_id = EXCLUDED.site_id, confirmed_by = EXCLUDED.confirmed_by""",
                a=r.area_nm, f=r.fact_manage_nm, vf=INITIAL_VALID_FROM, id=r.site_id,
                by="auto" if r.mapping_status == "auto" else "site_list_confirmed",
                note=f"사업장 목록 {version}",
            )
        for r in df.itertuples(index=False):
            conn.run(
                """INSERT INTO ref.stack (stack_key, area_nm, fact_manage_nm, stack_code,
                     frontend_stack_id, source)
                   VALUES (:k, :a, :f, :c, :fid, 'site_list')
                   ON CONFLICT (stack_key) DO UPDATE SET frontend_stack_id = EXCLUDED.frontend_stack_id,
                     source = 'site_list'""",
                k=r.stack_key, a=r.area_nm, f=r.fact_manage_nm, c=r.stack_code,
                fid=_clean([r.frontend_stack_id])[0],
            )
        conn.run("COMMIT")
    except Exception:
        conn.run("ROLLBACK")
        raise
    return {"sites": len(sites), "names": len(names), "stacks": len(df)}
