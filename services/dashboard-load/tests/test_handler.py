"""입력 검증·mode 흐름 (T019·T020·T036). recent·day는 가짜 S3 + DB 컨테이너로 끝까지 돈다."""
from __future__ import annotations

from datetime import date

import pytest
from conftest import BUCKET, utc
from ktms_cases import put_snapshot, stack_item

import lambda_handler as h

A = ("서울특별시", "가나다발전", "001")


def test_parse_event_validates():
    with pytest.raises(ValueError, match="mode"):
        h.parse_event({"mode": "x", "db_host": "h"})
    with pytest.raises(ValueError, match="db_host"):
        h.parse_event({"mode": "recent"})
    with pytest.raises(ValueError, match="date"):
        h.parse_event({"mode": "day", "db_host": "h"})
    req = h.parse_event({"mode": "recent", "db_host": "h", "db_port": "5432", "hours": 6})
    assert req == {"mode": "recent", "db_host": "h", "db_port": 5432, "hours": 6.0}
    assert h.parse_event({"mode": "day", "db_host": "h", "date": "2026-11-12"})["date"] == date(2026, 11, 12)


def test_kst_today_crosses_midnight():
    assert h.kst_today(utc(2026, 11, 18, 15, 30)) == date(2026, 11, 19)


def test_recent_then_daily_then_day(pg, fake_s3, monkeypatch):
    monkeypatch.setattr(h, "BUCKET", BUCKET)
    put_snapshot(fake_s3, BUCKET, utc(2026, 11, 18, 0, 40), [stack_item(*A, "2026-11-18 09:00", nox="30", sox="미수신")])
    put_snapshot(fake_s3, BUCKET, utc(2026, 11, 19, 0, 40), [stack_item(*A, "2026-11-19 09:00", nox="45", sox="2")])
    now = utc(2026, 11, 19, 0, 45)

    out = h.run({"mode": "recent", "hours": 4}, pg, fake_s3, now)
    assert out["rows"] == {"read": 2, "upserted": 2, "unchanged": 0}
    assert out["new_stack_keys"] == 1 and out["measured_range"]["max"] == "2026-11-19 09:00:00"
    assert h.run({"mode": "recent", "hours": 4}, pg, fake_s3, now)["rows"]["upserted"] == 0

    daily = h.run({"mode": "daily"}, pg, fake_s3, utc(2026, 11, 19, 18, 20))  # KST 11-20 03:20
    assert daily["rows"]["read"] == 0 and daily["summary_days"] == ["2026-11-18", "2026-11-19"]
    assert daily["new_names"] == [{"area_nm": "서울특별시", "fact_manage_nm": "가나다발전"}]  # ref 비어 있음

    day = h.run({"mode": "day", "date": date(2026, 11, 18)}, pg, fake_s3, now)
    assert day["rows"]["read"] == 2 and day["rows"]["upserted"] == 2  # 11-18 칸 NOx·SOx 새로
    assert pg.run("SELECT count(*) FROM obs.daily_stack_summary WHERE obs_date = '2026-11-18'")[0][0] == 2
