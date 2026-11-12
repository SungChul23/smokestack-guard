'''
- 명령줄 입구: python -m synth generate...
'''
import argparse
import sys
from synth import generate, plan, validate

# 명령을 읽어 실행
def main(argv = None) -> int:
    parser = argparse.ArgumentParser(prog = "synth")
    sub = parser.add_subparsers(dest = "command", required = True)

    g = sub.add_parser("generate", help = "합성 snapshot 생성")
    g.add_argument("--config", default = "config/config.yaml")
    g.add_argument("--stats", default = "data/ref_stats.csv")
    g.add_argument("--out", default = "out")

    v = sub.add_parser("validate", help="생성 결과 점검")
    v.add_argument("--out", default="out")       

    args = parser.parse_args(argv)                  

    if args.command == "generate":
        generate.generate(plan.load_config(args.config), args.stats, args.out)
        return 0
    issues = validate.validate_out(args.out)                       # validate: 문제 목록
    validate.print_report(issues, args.out)
    return 1 if issues else 0                                            # 문제가 있으면 종료 코드 1

if __name__ == "__main__":
    sys.exit(main())