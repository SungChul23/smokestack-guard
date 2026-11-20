from datetime import datetime, timedelta

import pytest

from app.agent.slots import (
    KST,
    UnsupportedPeriod,
    merge_command,
    missing_slots,
    norm_name,
    resolve_period,
)

NOW = datetime(2026, 11, 11, 9, 20, tzinfo=KST)


def test_norm_name_ignores_corporate_markers_and_spaces():
    names = [
        "㈜가나에너지",
        "(주)가나에너지",
        "가나에너지",
        "주식회사 가나에너지",
        "가나 에너지(주)",
    ]
    assert len({norm_name(n) for n in names}) == 1


def test_yesterday_is_a_full_day_of_48_slots():
    period = resolve_period({"kind": "yesterday"}, NOW)
    assert period.start == datetime(2026, 11, 10, tzinfo=KST)
    assert period.end == datetime(2026, 11, 11, tzinfo=KST)
    assert len(period.slots()) == 48


def test_today_runs_to_the_current_slot():
    period = resolve_period({"kind": "today"}, NOW)
    assert period.slots()[-1] == datetime(2026, 11, 11, 9, 0, tzinfo=KST)


def test_date_and_hours():
    assert resolve_period({"kind": "date", "value": "2026-11-10"}, NOW).label == "2026-11-10 하루"
    period = resolve_period({"kind": "hours", "value": 3}, NOW)
    assert period.end - period.start == timedelta(hours=3)


@pytest.mark.parametrize(
    "spec",
    [
        None,
        {"kind": "other"},
        {"kind": "now"},
        {"kind": "date", "value": "11월"},
        {"kind": "hours", "value": 100},
        {"kind": "hours", "value": "abc"},
    ],
)
def test_unsupported_periods(spec):
    with pytest.raises(UnsupportedPeriod):
        resolve_period(spec, NOW)


def test_missing_slots_are_asked_in_order():
    assert missing_slots({}) == ["stack", "pollutants", "time", "operation"]
    full = {
        "stack": {"business": "a"},
        "pollutants": ["nox"],
        "time": {"kind": "today"},
        "operation": "mean",
    }
    assert missing_slots(full) == []


def test_followup_patch_keeps_other_slots():
    base = {
        "stack": {"stack_key": "100:1"},
        "pollutants": ["nox"],
        "time": {"kind": "yesterday"},
        "operation": "mean",
        "metric": "value",
    }
    merged = merge_command(base, {"pollutants": ["sox"]}, ["pollutants"])
    assert merged["pollutants"] == ["sox"]
    assert merged["stack"] == {"stack_key": "100:1"} and merged["operation"] == "mean"


def test_without_patch_only_the_new_question_counts():
    base = {"stack": {"stack_key": "100:1"}, "pollutants": ["nox"], "operation": "mean"}
    merged = merge_command(base, {"pollutants": ["sox"]}, None)
    assert "stack" not in merged and merged["pollutants"] == ["sox"]
