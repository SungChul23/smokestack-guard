"""원본 범위·C의 규칙 호출·적재용 정리 (T014·T015·T035). DB 없이 돈다."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest
from conftest import BUCKET, utc
from ktms_cases import build_silver, put_snapshot, stack_item
from smokestack_guard.silver import ml_ready

import load

A = ("서울특별시", "가나다발전", "001")
B = ("부산광역시", "라마바소각", "002")


# --- 적재용 정리 ---------------------------------------------------------------


def test_prepare_rows_keeps_nox_sox_and_maps_status():
    silver = build_silver()
    rows = load.prepare_rows(silver)
    assert set(rows["item"]) == {"nox", "sox"}  # co 제외
    assert len(rows) == (silver["item"] != "co").sum()
    checking = rows[(rows["stack_code"] == "001") & (rows["item"] == "sox")
                    & (rows["measured_at"] == datetime(2026, 11, 2, 5, 0))]
    assert checking["status_code"].tolist() == [2]
    assert checking["value"].isna().all()  # 상태 행은 null, 0이 아님 (SC-005)
    ok = rows[rows["status_code"] == 0]
    assert (ok["ratio_pct"] - ok["value"] / ok["limit_value"] * 100).abs().max() < 1e-9


def test_stack_key_matches_ml_ready_rule():
    silver = build_silver()
    keys = set(load.prepare_rows(silver)["stack_key"])
    ml = ml_ready.to_ml_ready(silver.assign(status="ok"), data_source="ktms")
    assert keys == set(ml["stack_code"])  # ML-ready stack_code와 같은 규칙


def test_prepare_rows_rejects_unknown_status():
    silver = build_silver()
    silver.loc[0, "status"] = "new_status"
    with pytest.raises(ValueError, match="ref.status_code에 없는 상태"):
        load.prepare_rows(silver)


def test_prepare_rows_empty():
    assert load.prepare_rows(build_silver().iloc[0:0]).empty


# --- 범위 ---------------------------------------------------------------------


def test_recent_window_and_ingest_span_cross_utc_midnight():
    lo, hi = load.recent_window(utc(2026, 11, 19, 1, 15), 4)
    assert (lo, hi) == (utc(2026, 11, 18, 21, 15), utc(2026, 11, 19, 1, 15))
    assert load.ingest_span(lo, hi) == (date(2026, 11, 18), date(2026, 11, 19))
    with pytest.raises(ValueError):
        load.recent_window(utc(2026, 11, 19), 0)


def test_day_range_rejects_future():
    now = utc(2026, 11, 19, 1, 0)  # KST 11-19 10:00
    assert load.day_range(date(2026, 11, 19), now).start == date(2026, 11, 19)
    with pytest.raises(ValueError, match="미래"):
        load.day_range(date(2026, 11, 20), now)


# --- 원본 읽기 (가짜 S3) ---------------------------------------------------------


def _bronze(s3):
    put_snapshot(s3, BUCKET, utc(2026, 11, 18, 20, 40), [stack_item(*A, "2026-11-19 05:00", nox="40")])  # 창 밖
    put_snapshot(s3, BUCKET, utc(2026, 11, 18, 22, 10), [stack_item(*A, "2026-11-19 06:30", nox="41", sox="미수신"),
                                                         stack_item(*B, "2026-11-16 10:00", nox="미수신")])
    put_snapshot(s3, BUCKET, utc(2026, 11, 19, 0, 40), [stack_item(*A, "2026-11-19 09:00", nox="1,910.17", sox="5"),
                                                        stack_item(*B, "2026-11-16 10:00", nox="기기점검")])  # 사흘 전 칸 정정
    put_snapshot(s3, BUCKET, utc(2026, 11, 19, 0, 50), [stack_item(*A, "2026-11-19 09:30", nox="99")], success=False)


def test_read_recent_reads_only_window_and_success(fake_s3):
    _bronze(fake_s3)
    silver, info = load.read_recent(BUCKET, utc(2026, 11, 19, 1, 15), 4, fake_s3)
    rows = load.prepare_rows(silver)
    assert info["snapshots"] == 2  # 20:40(창 밖)·00:50(_SUCCESS 없음) 제외
    assert sorted(rows["measured_at"].astype(str).unique()) == [
        "2026-11-16 10:00:00", "2026-11-19 06:30:00", "2026-11-19 09:00:00"]
    late = rows[(rows["stack_code"] == "002") & (rows["item"] == "nox")]
    assert late["status_code"].tolist() == [5]  # 최근 스냅샷의 기기점검 (측정 시각으로 거르지 않음)
    big = rows[(rows["measured_at"] == pd.Timestamp("2026-11-19 09:00")) & (rows["item"] == "nox")]
    assert big["value"].tolist() == [1910.17]  # 천 단위 쉼표는 C의 규칙이 처리


def test_read_recent_empty_window(fake_s3):
    silver, info = load.read_recent(BUCKET, utc(2026, 11, 19, 1, 15), 4, fake_s3)
    assert silver.empty and info["snapshots"] == 0
    assert load.prepare_rows(silver).empty


def test_read_day_keeps_only_that_kst_day(fake_s3):
    _bronze(fake_s3)
    silver, info = load.read_day(BUCKET, date(2026, 11, 19), utc(2026, 11, 19, 3, 0), fake_s3)
    assert info["ingest_dates"] == ["2026-11-18", "2026-11-19"]
    assert set(pd.to_datetime(silver["ts_kst"]).dt.date) == {date(2026, 11, 19)}
