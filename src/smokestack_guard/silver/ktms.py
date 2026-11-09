"""K-TMS bronze (10-minute API snapshots in MinIO) -> silver (long: one row per stack x time x item).

Silver rules:
- the API repeats the latest measurement every 10 minutes (measurements are on :00/:30), so rows are
  deduplicated on stack + mesure_dt + item, keeping the latest snapshot (a "checking" value can be filled in later).
- text values become a `status` code and a NaN value; null value + null limit means the item is not monitored there.
- ratio = value / permit limit, the exceedance signal to predict.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
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
PREFIX = "tms_cleansys/"


def _s3():
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("MINIO_ENDPOINT", "http://localhost:9000"),
        aws_access_key_id=os.environ["MINIO_ROOT_USER"],
        aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
        region_name="us-east-1",
    )


def read_bronze(bucket: str = "bronze") -> pd.DataFrame:
    s3 = _s3()
    keys = sorted(
        o["Key"]
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=PREFIX)
        for o in page.get("Contents", [])
        if o["Key"].endswith("snapshot.json.gz")
    )
    frames = []
    for i, key in enumerate(keys):
        body = json.loads(gzip.decompress(s3.get_object(Bucket=bucket, Key=key)["Body"].read()))
        df = pd.DataFrame(body["response"]["body"]["items"])
        df["snapshot"] = i  # keys sort by ingest time
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def to_silver(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for item in ITEMS:
        for suffix in ("_mesure_value", "_exhst_perm_stdr_value"):
            if f"{item}{suffix}" not in df.columns:
                df[f"{item}{suffix}"] = pd.NA

    df = df.dropna(subset=STACK + ["mesure_dt"])
    parts = []
    for item in ITEMS:
        raw = df[f"{item}_mesure_value"]
        limit = pd.to_numeric(df[f"{item}_exhst_perm_stdr_value"], errors="coerce")
        part = df[STACK + ["mesure_dt", "snapshot"]].assign(item=item, value=pd.to_numeric(raw, errors="coerce"), limit=limit)
        text = raw.where(raw.notna() & part["value"].isna())
        part["status"] = text.map(STATUS).fillna("other").where(text.notna(), "ok")
        part.loc[part["status"].eq("ok") & (part["value"].isna() | part["limit"].isna()), "status"] = "not_monitored"
        parts.append(part[raw.notna() | limit.notna()])
    out = pd.concat(parts, ignore_index=True)
    out["ts_kst"] = pd.to_datetime(out["mesure_dt"], format="%Y-%m-%d %H:%M", errors="coerce")
    out = out.dropna(subset=["ts_kst"]).sort_values("snapshot")
    out = out.drop_duplicates(STACK + ["ts_kst", "item"], keep="last")
    out["ratio"] = out["value"] / out["limit"].where(out["limit"] > 0)
    return out.drop(columns=["mesure_dt", "snapshot"]).sort_values(STACK + ["item", "ts_kst"]).reset_index(drop=True)


def build(silver_dir: Path, bucket: str = "bronze") -> Path:
    # ponytail: full rebuild from every snapshot, partition by month once reads get slow (~144 snapshots/day)
    silver = to_silver(read_bronze(bucket))
    out = silver_dir / "ktms" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    silver.to_parquet(out, index=False)
    print(f"ktms: {len(silver):,} rows, {silver[STACK].drop_duplicates().shape[0]} stacks, status={silver['status'].value_counts().to_dict()}")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="K-TMS bronze snapshots -> silver parquet")
    p.add_argument("--silver-dir", type=Path, default=Path("data/silver"))
    build(p.parse_args().silver_dir)


if __name__ == "__main__":
    main()
