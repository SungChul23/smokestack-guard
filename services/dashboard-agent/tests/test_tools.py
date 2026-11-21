import pytest
from conftest import DAY, make_data

from app.agent.contract import Number, Part
from app.agent.data import parse_cell
from app.agent.slots import Period
from app.agent.tools import aggregate_values
from app.agent.verify import verify_part

PERIOD = Period(DAY, DAY.replace(day=11), "2026-11-10 하루")


def test_mean_excludes_status_rows_and_counts_zero():
    result = aggregate_values(make_data(), "100:1", "nox", "mean", "value", PERIOD)
    # 0..47 중 상태 3건(2,3,4)과 행 없음(10)을 뺀 44건. 값 0(0번 구간)은 정상 측정값이라 포함한다.
    assert result.n_used == 44 and result.n_excluded == 3 and result.n_missing == 1
    assert result.value == pytest.approx((sum(range(48)) - (2 + 3 + 4 + 10)) / 44)
    assert result.status_counts == {3: 2, 4: 1}


def test_max_min_sum():
    data = make_data()
    assert aggregate_values(data, "100:1", "nox", "max", "value", PERIOD).value == 47
    assert aggregate_values(data, "100:1", "nox", "min", "value", PERIOD).value == 0
    assert aggregate_values(data, "100:1", "nox", "sum", "value", PERIOD).value == 1109


def test_ratio_uses_limit():
    result = aggregate_values(make_data(), "100:1", "nox", "max", "ratio", PERIOD)
    assert result.value == pytest.approx(47 / 200 * 100) and result.unit == "%"


def test_not_monitored_item_has_no_value():
    result = aggregate_values(make_data(), "100:1", "sox", "mean", "value", PERIOD)
    assert result.value is None and result.n_used == 0 and result.status_counts == {8: 48}


def test_parse_cell_status_codes():
    assert parse_cell("미수신", "115").status_code == 3
    assert parse_cell("측정자료확인중(가동중지)", "115").status_code == 1
    assert parse_cell(None, None).status_code == 8
    assert parse_cell("알 수 없는 말", "1").status_code == 99
    ok = parse_cell("1,234.5", "2,000")
    assert ok.status_code == 0 and ok.value == 1234.5 and ok.limit == 2000
    zero = parse_cell("0.00", "100")
    assert zero.status_code == 0 and zero.value == 0
    # 상태 행의 value는 0이지만 status_code로 구분한다.
    status_row = parse_cell("보수중", "100")
    assert status_row.value == 0 and status_row.status_code == 4


def test_verify_detects_a_wrong_number():
    number = Number(
        name="mean",
        pollutant="NOx",
        value=12.34,
        unit="ppm",
        n_used=1,
        n_excluded=0,
        n_missing=0,
        period="p",
        as_of=None,
    )
    good = Part(
        part_id="p1",
        agent="data",
        status="DONE",
        label="현황",
        answer="NOx 평균 12.34 ppm",
        numbers=[number],
    )
    bad = good.model_copy(update={"answer": "NOx 평균 99.99 ppm"})
    assert verify_part(good) == [] and verify_part(bad) != []
