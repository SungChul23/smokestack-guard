'''
- 실행: python -m synth_train generate-day --date 2026-11-16
        python -m synth_train backfill --from 2026-10-30 --to 2026-11-15
'''
import argparse
from datetime import date

from synth_train import generate, plan, stats

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
    args = parser.parse_args()

    config = plan.load_config(args.config)
    out = args.out or config["paths"]["out"]
    ref_df = stats.load_ref_stats(config["paths"]["stats"])

    if args.cmd == "generate-day":
        results = [generate.generate_day(config, ref_df, args.date, out)]
    else:
        results = generate.backfill(config, ref_df, args.start, args.end, out)
    for r in results:
        print(f"{r['day']}: 스냅샷 {r['snapshots']}개, 행 {r['rows']}, 에피소드 {r['episodes']}")

if __name__ == "__main__":
    main()