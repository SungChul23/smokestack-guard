"""DB 쓰기·요약·매핑 점검·권한 (T012·T017·T028·T030~T032·T038). PostgreSQL 컨테이너가 필요하다."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest
from conftest import MIGRATIONS, utc

import db
import load

NOW = utc(2026, 11, 19, 1, 15)
LATER = utc(2026, 11, 19, 1, 45)


def _rows(spec):
    """spec: (stack_code, item, 'YYYY-MM-DD HH:MM', value, status)."""
    recs = []
    for code, item, ts, value, status in spec:
        recs.append({
            "area_nm": "서울특별시", "fact_manage_nm": "가나다발전", "stack_code": code, "item": item,
            "value": value, "limit": 100.0, "status": status, "ts_kst": pd.Timestamp(ts),
            "ratio": None if value is None else value / 100.0,
        })
    return load.prepare_rows(pd.DataFrame(recs))


def _count(conn, sql, **kw):
    return conn.run(sql, **kw)[0][0]


# --- 마이그레이션 ----------------------------------------------------------------


def test_migrations_apply_once_and_seed_status(pg):
    assert db.migrate(pg, MIGRATIONS) == []  # 두 번째는 건너뜀
    assert _count(pg, "SELECT count(*) FROM ref.status_code") == 9
    assert _count(pg, "SELECT count(*) FROM ops.schema_migrations") == 4


def test_split_sql_keeps_dollar_blocks():
    stmts = db.split_sql("CREATE A; -- x;y\nDO $$ BEGIN SELECT 1; END $$;\nSELECT 2")
    assert stmts == ["CREATE A", "DO $$ BEGIN SELECT 1; END $$", "SELECT 2"]


# --- UPSERT --------------------------------------------------------------------


def test_upsert_is_idempotent_and_updates_changes(pg):
    rows = _rows([("001", "nox", "2026-11-19 09:00", 45.2, "ok"),
                  ("001", "sox", "2026-11-19 09:00", None, "no_signal")])
    assert db.upsert_measurements(pg, rows, "recent", NOW) == (2, 0)
    assert db.upsert_measurements(pg, rows, "recent", LATER) == (0, 2)  # SC-002
    assert _count(pg, "SELECT count(*) FROM obs.measurement_30m WHERE loaded_at = :t", t=NOW) == 2  # 그대로 유지

    fixed = _rows([("001", "sox", "2026-11-19 09:00", 3.0, "ok")])  # 미수신 → 값 채워짐
    assert db.upsert_measurements(pg, fixed, "recent", LATER) == (1, 0)
    v = pg.run("SELECT value, status_code, loaded_at FROM obs.measurement_30m WHERE item = 'sox'")[0]
    assert v[0] == 3.0 and v[1] == 0


def test_status_rows_are_null_not_zero(pg):
    rows = _rows([("001", "nox", "2026-11-19 09:00", None, "maintenance"),
                  ("001", "nox", "2026-11-19 09:30", 0.0, "ok")])
    db.upsert_measurements(pg, rows, "recent", NOW)
    assert _count(pg, "SELECT count(*) FROM obs.measurement_30m WHERE status_code <> 0 AND value IS NOT NULL") == 0
    assert _count(pg, "SELECT count(*) FROM obs.measurement_30m WHERE status_code = 0 AND value = 0") == 1


def test_add_stack_keys_registers_new_keys_once(pg):
    rows = _rows([("001", "nox", "2026-11-19 09:00", 1.0, "ok"), ("002", "nox", "2026-11-19 09:00", 1.0, "ok")])
    assert db.add_stack_keys(pg, rows, date(2026, 11, 19)) == 2
    assert db.add_stack_keys(pg, rows, date(2026, 11, 19)) == 0
    assert _count(pg, "SELECT count(*) FROM ref.stack WHERE source = 'observed'") == 2


# --- 일일 요약 -------------------------------------------------------------------


def _day_rows(day: str, ok: int, no_signal: int, values=None):
    spec = []
    slots = pd.date_range(f"{day} 00:00", periods=48, freq="30min")
    for i, ts in enumerate(slots[: ok + no_signal]):
        if i < ok:
            v = (values or {}).get(i, 50.0)
            spec.append(("001", "nox", str(ts), v, "ok"))
        else:
            spec.append(("001", "nox", str(ts), None, "no_signal"))
    return _rows(spec)


def test_daily_stack_summary_counts_and_stats(pg):
    rows = _day_rows("2026-11-18", ok=40, no_signal=5, values={0: 0.0, 3: 95.0, 7: 101.0})
    db.upsert_measurements(pg, rows, "recent", NOW)
    before = _count(pg, "SELECT count(*) FROM obs.measurement_30m")
    db.refresh_daily_summaries(pg, [date(2026, 11, 18)], NOW)
    s = pg.run("""SELECT n_ok, n_zero, n_no_signal, n_missing, max_value, max_at, min_value,
                         n_ge_90, n_ge_100, n_gt_100, limit_min, limit_max
                  FROM obs.daily_stack_summary""")[0]
    assert s[:4] == [40, 1, 5, 3]  # US2-3: 정상 40, 미수신 5, 행 없음 3
    assert s[4] == 101.0 and s[5] == datetime(2026, 11, 18, 3, 30) and s[6] == 0.0
    assert s[7:10] == [2, 1, 1]
    assert s[10:] == [100.0, 100.0]
    assert _count(pg, "SELECT count(*) FROM obs.measurement_30m") == before  # 관측은 안 바뀜
    n = pg.run("SELECT max_ratio_pct, max_stack_key, n_stacks_reporting, n_stacks_gt_100 "
               "FROM obs.daily_national_summary")[0]
    assert n == [101.0, "서울특별시|가나다발전|001", 1, 1]


def test_summary_days_includes_dates_changed_since_last_daily(pg):
    today = date(2026, 11, 19)
    assert db.summary_days(pg, today) == [date(2026, 11, 17), date(2026, 11, 18)]
    db.record_run(pg, {"run_id": "d1", "mode": "daily", "started_at": NOW, "finished_at": NOW,
                       "rows": {"read": 0, "upserted": 0, "unchanged": 0}, "result": "succeeded"})
    late = _rows([("001", "nox", "2026-11-10 10:00", 7.0, "ok")])  # 늦게 온 과거 칸
    db.upsert_measurements(pg, late, "recent", LATER)
    assert db.summary_days(pg, today) == [date(2026, 11, 10), date(2026, 11, 17), date(2026, 11, 18)]


# --- 사업장 목록 · 매핑 점검 ---------------------------------------------------------


def _sites():
    return pd.DataFrame([
        {"site_id": "112003", "area_nm": "서울특별시", "fact_manage_nm": "가나다발전", "display_name": "가나다발전(주)",
         "region_sigungu": "중구", "address": "가상 주소 1", "lat": "37.5", "lon": "127.0",
         "coordinate_source": "test", "stack_code": "001", "frontend_stack_id": "KS-T1", "mapping_status": "auto"},
    ])


def test_load_ref_is_idempotent_and_view_resolves_site(pg):
    assert db.load_ref(pg, _sites(), "test-v1") == {"sites": 1, "names": 1, "stacks": 1}
    db.load_ref(pg, _sites(), "test-v1")
    assert _count(pg, "SELECT count(*) FROM ref.stack") == 1
    assert pg.run("SELECT site_id FROM ref.v_stack")[0][0] == "112003"


def test_load_ref_rejects_inconsistent_site():
    bad = pd.concat([_sites(), _sites().assign(stack_code="002", address="다른 주소")])
    with pytest.raises(ValueError, match="사업장 정보가 다름"):
        db.validate_sites(bad)


def test_mapping_check_alerts_new_name_once_and_name_change_links_history(pg):
    db.load_ref(pg, _sites(), "test-v1")
    renamed = load.prepare_rows(pd.DataFrame([{
        "area_nm": "서울특별시", "fact_manage_nm": "가나다에너지", "stack_code": "001", "item": "nox",
        "value": 1.0, "limit": 100.0, "status": "ok", "ts_kst": pd.Timestamp("2026-11-18 10:00"), "ratio": 0.01}]))
    db.upsert_measurements(pg, renamed, "recent", NOW)
    db.add_stack_keys(pg, renamed, date(2026, 11, 18))
    names = db.mapping_check(pg, date(2026, 11, 18), NOW)
    assert names == [{"area_nm": "서울특별시", "fact_manage_nm": "가나다에너지"}]
    assert db.mapping_check(pg, date(2026, 11, 18), LATER) == []  # 같은 이름은 다시 알리지 않음
    assert _count(pg, "SELECT n_items FROM ops.mapping_report WHERE check_type = 'C'") == 1  # 새 굴뚝은 기록만

    pg.run("INSERT INTO ref.site_name_map (area_nm, fact_manage_nm, valid_from, site_id, confirmed_by) "
           "VALUES ('서울특별시', '가나다에너지', '2026-11-18', '112003', 'A')")  # 사람이 한 줄 추가
    sites = {r[0] for r in pg.run("SELECT site_id FROM ref.v_stack")}
    assert sites == {"112003"}  # 옛 이름·새 이름 굴뚝 모두 같은 사업장 (US3-3)


# --- 권한 ----------------------------------------------------------------------


def test_app_role_cannot_write_obs_or_ref_but_can_write_app(pg):
    pg.run("SET ROLE tms_app")
    try:
        with pytest.raises(Exception, match="permission denied"):
            pg.run("INSERT INTO obs.daily_national_summary (obs_date, item, n_stacks_reporting, n_stacks_ge_90, "
                   "n_stacks_gt_100, computed_at) VALUES ('2026-11-18', 'nox', 0, 0, 0, now())")
    finally:
        pg.run("RESET ROLE")
    pg.run("SET ROLE tms_app")
    try:
        with pytest.raises(Exception, match="permission denied"):
            pg.run("INSERT INTO ref.site_name_map (area_nm, fact_manage_nm, valid_from, site_id, confirmed_by) VALUES ('a', 'b', '2026-01-01', 'x', 'y')")
    finally:
        pg.run("RESET ROLE")
    pg.run("SET ROLE tms_app")
    try:
        pg.run("INSERT INTO app.user_favorite (user_sub, target) VALUES ('u1', 's1')")
        pg.run("SELECT embedding <=> embedding FROM rag.doc_chunk")  # pgvector 사용 가능
    finally:
        pg.run("RESET ROLE")


def test_loader_role_cannot_write_site_map(pg):
    pg.run("SET ROLE tms_loader")
    try:
        with pytest.raises(Exception, match="permission denied"):
            pg.run("INSERT INTO ref.site_name_map (area_nm, fact_manage_nm, valid_from, site_id, confirmed_by) VALUES ('a', 'b', '2026-01-01', 'x', 'y')")
    finally:
        pg.run("RESET ROLE")
