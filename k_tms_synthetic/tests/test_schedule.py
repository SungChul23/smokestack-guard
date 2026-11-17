'''
- schedule test: 시각표가 맞는지 확인
'''
from datetime import datetime, timedelta, timezone
from synth import schedule

KST = timezone(timedelta(hours = 9))

# 문자열 시간대를 한국 시간으로 바꿈
def test_parse_kst_is_timezone_aware():
    t = schedule.parse_kst("2026-11-20 09:00")
    assert t == datetime(2026, 11, 20, 9, 0, tzinfo = KST)

# 측정 시각은 실측처럼 "YYYY-MM-DD HH:MM"
def test_mesure_dt_format():
    t = schedule.parse_kst("2026-11-20 09:00")
    assert schedule.format_mesure_dt(t) == "2026-11-20 09:00"

# 측정 시각은 시작부터 30분씩, 요청한 개수 만큼
def test_mesure_times_are_30min_grid():
    times = schedule.mesure_times("2026-11-20 09:00", steps = 4)
    texts = [schedule.format_mesure_dt(t) for t in times]
    assert texts == ["2026-11-20 09:00", "2026-11-20 09:30", "2026-11-20 10:00", "2026-11-20 10:30"]

# snapshot은 10분 간격이고 값 하나가 3번씩 보임
def test_snapshot_times_every_10min_and_count():
    times = schedule.snapshot_times("2026-11-20 09:00", steps = 4)
    assert len(times) == 12
    gaps = {(b - a) for a, b in zip(times, times[1:])}
    assert gaps == {timedelta(minutes = 10)}
    assert times[0] == schedule.parse_kst("2026-11-20 09:00")

# 지연 0: 09:00~09:20 snapshot은 0번 값, 09:30~09:50은 1번 값을 담음
def test_latest_slot_index_zero_delay():
    start = "2026-11-20 09:00"
    def idx(hhmm):
        return schedule.latest_slot_index(start, schedule.parse_kst(f"2026-11-20 {hhmm}"))
    assert [idx("09:00"), idx("09:10"), idx("09:20")] == [0, 0, 0]
    assert [idx("09:30"), idx("09:40"), idx("09:50")] == [1, 1, 1]

# snapshot 실행 시각은 UTC 
def test_run_ts_is_utc_minus_9h():
    run_ts = schedule.to_run_ts(schedule.parse_kst("2026-11-20 09:00"))
    assert run_ts == datetime(2026, 11, 20, 0, 0, tzinfo = timezone.utc)
    assert run_ts.utcoffset() == timedelta(0)