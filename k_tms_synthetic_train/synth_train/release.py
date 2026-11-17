'''
- release: 지금 시각을 기준으로 도착할 때가 된 스냅샷만 Kafka로 발행
'''
from datetime import timedelta, timezone
from pathlib import Path
from synth_train import generate, publish, schedule

DEFAULT_LOOKBACK_MIN = 180

# 하루치가 이미 만들어 졌는지
def _day_done(out_dir, day) -> bool:
    return (Path(out_dir) / "manifest" / f"{day:%Y-%m-%d}.jsonl").exists()

# now 기준으로 한 번 실행
def run(config: dict, ref_df, now, out_dir, producer, topic: str = publish.TOPIC, lookback_min = None) -> dict:
    now = now.astimezone(timezone.utc)
    if lookback_min is None:
        lookback_min = config.get("release", {}).get("lookback_min", DEFAULT_LOOKBACK_MIN)

    today = now.astimezone(schedule.KST).date()
    generated = []
    for day in (today - timedelta(days = 1), today, today + timedelta(days = 1)):
        if not _day_done(out_dir, day):
            generate.generate_day(config, ref_df, day, out_dir)
            generated.append(f"{day:%Y-%m-%d}")

    due = publish.messages_from_dir(
        out_dir, max_bytes = config["snapshot"]["max_message_bytes"],
        since = now - timedelta(minutes = lookback_min), until = now)
    sent = publish.publish(producer, topic, due)
    return {
        "now": now.isoformat(timespec="seconds"),
        "generated_days": generated,
        "published": sent,
        "last_run_ts": due[-1]["key"].decode() if due else None,
    }