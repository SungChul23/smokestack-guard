"""K-TMS bronze (10-minute API snapshots in S3) -> silver (long: one row per stack x time x item).

Silver rules:
- the API repeats the latest measurement every 10 minutes (measurements are on :00/:30), so rows are
  deduplicated on stack + mesure_dt + item, keeping the latest snapshot (a "checking" value can be filled in later).
- only runs with a `_SUCCESS` marker are read (the collector writes it last, so a failed or half-written run is skipped).
- big values come with a thousands separator ("1,910.17"); it is removed so the value is kept instead of becoming `other`.
- text values become a `status` code and a NaN value; null value + null limit means the item is not monitored there.
- the API has no id to tell apart two rows with the same area + facility + stack_code in one snapshot; when such
  rows disagree on an item, that item is `ambiguous` (NaN value) instead of an arbitrary winner.
- ratio = value / permit limit, the exceedance signal to predict.
"""
from __future__ import annotations

import argparse
import gzip
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import boto3
import pandas as pd

ITEMS = ["nox", "sox", "tsp", "hcl", "co", "nh3", "hf"]
STACK = ["area_nm", "fact_manage_nm", "stack_code"]
STATUS = {
    "측정자료확인중(가동중지)": "stopped",
    "측정자료확인중": "checking",
    "미수신": "no_signal",
    "보수중": "maintenance",
    "기기점검": "inspection",
}
BUCKET = "smokestack-tms-raw-952900391026"
REGION = "ap-northeast-2"
PREFIX = "tms_cleansys/"


def _s3():
    return boto3.client("s3", region_name=REGION)


def _keys(s3, bucket: str, start: date | None, end: date | None) -> list[str]:
    if start is None and end is None:
        prefixes = [PREFIX]
    else:
        start, end = start or end, end or start
        prefixes = [f"{PREFIX}ingest_date={start + timedelta(days=n)}/" for n in range((end - start).days + 1)]
    keys = [
        o["Key"]
        for prefix in prefixes
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
        for o in page.get("Contents", [])
    ]
    done = {k.rsplit("/", 1)[0] for k in keys if k.endswith("/_SUCCESS")}  # the collector writes _SUCCESS last
    return sorted(  # keys sort by ingest time
        k for k in keys if k.endswith("snapshot.json.gz") and k.rsplit("/", 1)[0] in done
    )


def read_bronze(bucket: str = BUCKET, start: date | None = None, end: date | None = None, s3=None) -> pd.DataFrame:
    s3 = s3 or _s3()
    frames = []
    for i, key in enumerate(_keys(s3, bucket, start, end)):
        body = json.loads(gzip.decompress(s3.get_object(Bucket=bucket, Key=key)["Body"].read()))
        df = pd.DataFrame(body["response"]["body"]["items"])
        df["snapshot"] = i
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _plain_number(raw: pd.Series) -> pd.Series:
    """Drop the thousands separator the API puts in big values ("1,910.17"); other strings stay as they are."""
    s = raw.astype("string")
    return s.where(~s.str.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", na=False), s.str.replace(",", "", regex=False))


def to_silver(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for item in ITEMS:
        for suffix in ("_mesure_value", "_exhst_perm_stdr_value"):
            if f"{item}{suffix}" not in df.columns:
                df[f"{item}{suffix}"] = pd.NA

    df = df.dropna(subset=STACK + ["mesure_dt"])
    parts = []
    for item in ITEMS:
        raw = _plain_number(df[f"{item}_mesure_value"])
        limit = pd.to_numeric(df[f"{item}_exhst_perm_stdr_value"], errors="coerce")
        part = df[STACK + ["mesure_dt", "snapshot"]].assign(item=item, value=pd.to_numeric(raw, errors="coerce").astype("float64"), limit=limit, raw=raw.astype("string") + "|" + limit.astype("string"))  # value and limit must both agree
        text = raw.where(raw.notna() & part["value"].isna())
        part["status"] = text.map(STATUS).fillna("other").where(text.notna(), "ok")
        part.loc[part["status"].eq("ok") & (part["value"].isna() | part["limit"].isna()), "status"] = "not_monitored"
        part = part[raw.notna() | limit.notna()]
        disagree = part.groupby(STACK + ["mesure_dt", "snapshot"], dropna=False)["raw"].transform("nunique").gt(1)
        part.loc[disagree, "status"] = "ambiguous"
        part.loc[disagree, "value"] = float("nan")
        parts.append(part.drop(columns="raw"))
    out = pd.concat(parts, ignore_index=True)
    out["ts_kst"] = pd.to_datetime(out["mesure_dt"], format="%Y-%m-%d %H:%M", errors="coerce")
    out = out.dropna(subset=["ts_kst"]).sort_values("snapshot", kind="stable")  # same-snapshot ties keep input order
    out = out.drop_duplicates(STACK + ["ts_kst", "item"], keep="last")
    out["ratio"] = out["value"] / out["limit"].where(out["limit"] > 0)
    return out.drop(columns=["mesure_dt", "snapshot"]).sort_values(STACK + ["item", "ts_kst"]).reset_index(drop=True)


def quality(silver: pd.DataFrame, snapshots: int, same_snapshot_dupes: int = 0) -> dict:
    return {
        "snapshots": snapshots,
        "same_snapshot_dupes": same_snapshot_dupes,
        "rows": len(silver),
        "stacks": silver[STACK].drop_duplicates().shape[0],
        "status": silver["status"].value_counts().to_dict(),
        "duplicate_keys": int(silver.duplicated(STACK + ["ts_kst", "item"]).sum()),
        "rows_per_day": {str(d): n for d, n in silver.groupby(silver["ts_kst"].dt.date).size().items()},
    }


def write_partitions(silver: pd.DataFrame, silver_dir: Path, first: date | None = None, last: date | None = None) -> list[date]:
    written = []
    for day, part in silver.groupby(silver["ts_kst"].dt.date):
        if (first is None or day >= first) and (last is None or day <= last):
            out = silver_dir / "ktms" / f"ts_date={day}" / "part.parquet"
            out.parent.mkdir(parents=True, exist_ok=True)
            part.to_parquet(out, index=False)  # same date -> same file, so reruns overwrite
            written.append(day)
    return written


KST = timezone(timedelta(hours=9))


def last_complete_day(now: datetime | None = None) -> date:
    """Latest Korean calendar day that has fully ended, so a half-collected day is never written."""
    return (now or datetime.now(timezone.utc)).astimezone(KST).date() - timedelta(days=1)


def build(silver_dir: Path, bucket: str = BUCKET, start: date | None = None, end: date | None = None, s3=None) -> list[date]:
    bronze = read_bronze(bucket, start, end, s3=s3)
    if bronze.empty:  # collection outage or wrong dates: fail loudly and leave existing partitions alone
        raise ValueError(f"no K-TMS snapshots in s3://{bucket}/{PREFIX} for ingest_date {start}..{end}")
    silver = to_silver(bronze)
    # ingest_date is the UTC date: KST day D lives in ingest dates D-1 (from 15:00Z) and D, so only D in [start+1, end] is complete
    first = start + timedelta(days=1) if start else None
    done = last_complete_day()
    written = write_partitions(silver, silver_dir, first, min(end, done) if end else done)
    dupes = int(bronze.duplicated(STACK + ["mesure_dt", "snapshot"]).sum()) if len(bronze) else 0
    print("ktms quality:", json.dumps(quality(silver, bronze["snapshot"].nunique() if len(bronze) else 0, dupes), ensure_ascii=False))
    print(f"ktms partitions written: {[str(d) for d in written]}")
    return written


def main() -> None:
    p = argparse.ArgumentParser(description="K-TMS bronze snapshots -> silver parquet partitions (ts_date=YYYY-MM-DD)")
    p.add_argument("--silver-dir", type=Path, default=Path("data/silver"))
    p.add_argument("--bucket", default=BUCKET)
    p.add_argument("--start-date", type=date.fromisoformat, help="first ingest_date (UTC, YYYY-MM-DD); omit both dates to read everything")
    p.add_argument("--end-date", type=date.fromisoformat, help="last ingest_date (inclusive)")
    p.add_argument("--days", type=int, help="rebuild the last N ingest days up to today (UTC), e.g. 2; the still-running Korean day is not written")
    args = p.parse_args()
    start, end = args.start_date, args.end_date
    if args.days:
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=args.days)
    build(args.silver_dir, args.bucket, start, end)


if __name__ == "__main__":
    main()
