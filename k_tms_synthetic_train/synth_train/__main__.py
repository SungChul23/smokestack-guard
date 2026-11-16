import argparse
from datetime import date, datetime, timezone

from synth_train import generate, plan, publish, release, stats, summary, validate

def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default="config/daily.yaml")
    common.add_argument("--out", default=None)

    parser = argparse.ArgumentParser(prog="synth_train")
    sub = parser.add_subparsers(dest="cmd", required=True)
    one = sub.add_parser("generate-day", parents=[common])
    one.add_argument("--date", required=True, type=date.fromisoformat)
    many = sub.add_parser("backfill", parents=[common])
    many.add_argument("--from", dest="start", required=True, type=date.fromisoformat)
    many.add_argument("--to", dest="end", required=True, type=date.fromisoformat)
    check = sub.add_parser("validate")
    check.add_argument("--out", required=True)
    show = sub.add_parser("summary")
    show.add_argument("--manifest-dir", default="out/manifest")
    pub = sub.add_parser("publish", parents=[common])
    pub.add_argument("--src", default=None)
    pub.add_argument("--topic", default=publish.TOPIC)
    pub.add_argument("--bootstrap", default="localhost:9092")
    rel = sub.add_parser("release", parents=[common])
    rel.add_argument("--topic", default=publish.TOPIC)
    rel.add_argument("--bootstrap", default="localhost:9092")
    rel.add_argument("--now", default=None, help="ISO 시각(시간대 포함). 없으면 현재 시각")
    rel.add_argument("--lookback-min", type=int, default=None)
    args = parser.parse_args()

    if args.cmd == "validate":
        issues = validate.validate_out(args.out)
        validate.print_report(issues)
        raise SystemExit(1 if issues else 0)
    if args.cmd == "summary":
        summary.print_summary(summary.summarize(args.manifest_dir))
        raise SystemExit(0)

    config = plan.load_config(args.config)
    out = args.out or config["paths"]["out"]

    if args.cmd == "publish":
        from confluent_kafka import Producer               # 발행할 때만 필요
        producer = Producer({"bootstrap.servers": args.bootstrap})
        n = publish.publish(producer, args.topic, publish.messages_from_dir(args.src or out))
        print(f"발행 {n}개")
        raise SystemExit(0)

    ref_df = stats.load_ref_stats(config["paths"]["stats"])
    if args.cmd == "release":
        from confluent_kafka import Producer
        producer = Producer({"bootstrap.servers": args.bootstrap})
        now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
        r = release.run(config, ref_df, now, out, producer, args.topic, args.lookback_min)
        print(f"{r['now']}: 생성 {r['generated_days']}, 발행 {r['published']}개, 마지막 run_ts {r['last_run_ts']}")
        raise SystemExit(0)

    if args.cmd == "generate-day":
        results = [generate.generate_day(config, ref_df, args.date, out)]
    else:
        results = generate.backfill(config, ref_df, args.start, args.end, out)
    for r in results:
        print(f"{r['day']}: 스냅샷 {r['snapshots']}개, 행 {r['rows']}, 에피소드 {r['episodes']}")

if __name__ == "__main__":
    main()