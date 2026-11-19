"""사람이 실행하는 명령 (spec 012, contracts §4). AWS·DB 명령은 사람이 실행한다(AGENTS.md).

    python run_dashboard_load.py migrate [--dry-run]
    python run_dashboard_load.py load-ref --sites s3://…/ref/sites/<버전>.csv [--dry-run]
    python run_dashboard_load.py backfill --from 2026-10-30 --to 2026-11-19 [--dry-run]
    python run_dashboard_load.py status

migrate · load-ref · status는 베스천 터널(기본 localhost:5433)로 tms_admin이 접속한다.
    ssh -i tms-bastion.pem -L 5433:<db_host>:5432 ec2-user@bastion.smokestack-guard.store
관리자 비밀번호는 실행할 때 Secrets Manager에서 읽고, 출력하거나 저장하지 않는다.
backfill은 상태 머신을 날짜마다 실행한다(본인 IAM 권한).
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import boto3
import pandas as pd

import db

REGION = "ap-northeast-2"
ACCOUNT = "952900391026"
STATE_MACHINE = f"arn:aws:states:{REGION}:{ACCOUNT}:stateMachine:tms-dashboard-load"
SECRET_ARN_PARAM = "/tms/app/config/db-secret-arn"
MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def admin_connection(host: str, port: int):
    ssm = boto3.client("ssm", region_name=REGION)
    arn = ssm.get_parameter(Name=SECRET_ARN_PARAM)["Parameter"]["Value"]
    secret = json.loads(boto3.client("secretsmanager", region_name=REGION).get_secret_value(SecretId=arn)["SecretString"])
    return db.connect(host, port, secret["username"], password=secret["password"],
                      tls=db.ssl_context(verify_hostname=False))


def read_sites(path: str) -> pd.DataFrame:
    if path.startswith("s3://"):
        bucket, key = path[5:].split("/", 1)
        body = boto3.client("s3", region_name=REGION).get_object(Bucket=bucket, Key=key)["Body"].read()
        return pd.read_csv(io.BytesIO(body), dtype=str)
    return pd.read_csv(path, dtype=str)


def cmd_migrate(args) -> None:
    conn = admin_connection(args.host, args.port)
    try:
        files = db.migrate(conn, MIGRATIONS, dry_run=args.dry_run)
    finally:
        conn.close()
    print(("적용할 파일: " if args.dry_run else "적용함: ") + (", ".join(files) or "없음"))


def cmd_load_ref(args) -> None:
    df = read_sites(args.sites)
    checked = db.validate_sites(df)
    version = Path(args.sites).stem
    print(f"사업장 {checked['site_id'].nunique()} · 이름 {checked[['area_nm', 'fact_manage_nm']].drop_duplicates().shape[0]}"
          f" · 굴뚝 {len(checked)} (버전 {version})")
    if args.dry_run:
        return
    conn = admin_connection(args.host, args.port)
    try:
        print(db.load_ref(conn, df, version))
    finally:
        conn.close()


def _dates(a: date, b: date) -> list[date]:
    return [a + timedelta(days=n) for n in range((b - a).days + 1)]


def cmd_backfill(args) -> None:
    days = _dates(date.fromisoformat(args.date_from), date.fromisoformat(args.date_to))
    if args.dry_run:
        print(f"{len(days)}일: {days[0]} ~ {days[-1]}")
        return
    sfn = boto3.client("stepfunctions", region_name=REGION)
    failed = []
    print("date        status     read   upserted  unchanged")
    for d in days:
        arn = sfn.start_execution(stateMachineArn=STATE_MACHINE,
                                  input=json.dumps({"mode": "day", "date": d.isoformat()}))["executionArn"]
        while (res := sfn.describe_execution(executionArn=arn))["status"] == "RUNNING":
            time.sleep(5)
        out = json.loads(res.get("output") or "{}")
        rows = out.get("load", {}).get("Payload", {}).get("rows", {})
        status = res["status"] if "skipped" not in out else f"skip:{out['skipped']}"
        print(f"{d}  {status:<9} {rows.get('read', '-'):>6} {rows.get('upserted', '-'):>9} {rows.get('unchanged', '-'):>10}")
        if res["status"] != "SUCCEEDED":
            failed.append(d)
    if failed:
        print("실패한 날짜: " + ", ".join(map(str, failed)))
        print(f"다시: python run_dashboard_load.py backfill --from {failed[0]} --to {failed[-1]}")
        sys.exit(1)


def cmd_status(args) -> None:
    conn = admin_connection(args.host, args.port)
    try:
        for r in conn.run("SELECT run_id, result, rows_read, rows_upserted, rows_unchanged, summary_days "
                          "FROM ops.load_run ORDER BY started_at DESC LIMIT 10"):
            print(*r)
        print("--- 날짜별 관측 행 수 (최근 14일)")
        for r in conn.run("SELECT measured_at::date, item, count(*) FROM obs.measurement_30m "
                          "WHERE measured_at >= now()::date - 14 GROUP BY 1, 2 ORDER BY 1, 2"):
            print(*r)
    finally:
        conn.close()


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="localhost", help="베스천 터널 주소")
    p.add_argument("--port", type=int, default=5433)
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("migrate"); m.add_argument("--dry-run", action="store_true")
    r = sub.add_parser("load-ref"); r.add_argument("--sites", required=True); r.add_argument("--dry-run", action="store_true")
    b = sub.add_parser("backfill")
    b.add_argument("--from", dest="date_from", required=True); b.add_argument("--to", dest="date_to", required=True)
    b.add_argument("--dry-run", action="store_true")
    sub.add_parser("status")
    args = p.parse_args(argv)
    {"migrate": cmd_migrate, "load-ref": cmd_load_ref, "backfill": cmd_backfill, "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    main()
