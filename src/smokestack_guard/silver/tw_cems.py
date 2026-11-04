"""Taiwan CEMS 15-minute records (AQX_P_186 monthly JSON) -> silver on the K-TMS 30-minute grid.

Rules follow the "대만 CEMS 데이터 활용" plan (v0.1, 6.3 / 6.4):
- keep NOX(923) / SOX(922) / CO(924) only, and only rows whose unit is ppm (anything else is dropped, never converted).
- Code2 is 4 chars: operating state (N, A usable) + equipment class + data state (10, 11 usable; 11 = over the limit, keep it).
- M_Time is the interval start in Taiwan time (UTC+8); stored as UTC.
- two valid 15-minute rows are averaged into one :00/:30 row; a single missing/invalid one leaves the slot empty (no fill).
- measured values are already oxygen-corrected record values, so no correction is applied here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ITEMS = {"923": "NOX", "922": "SOX", "924": "CO"}
OPERATING = set("NA")
OPERATING_KNOWN = OPERATING | set("BCDEFGHIJP")
DATA_OK = {"10", "11"}
DATA_KNOWN = DATA_OK | {"01", "02", "03", "20", "21", "22", "30", "31", "32", "40", "93"}
ORIGIN = "tw_observed"


def record_state(code2: pd.Series) -> pd.Series:
    known = (code2.str.len() == 4) & code2.str[0].isin(OPERATING_KNOWN) & code2.str[2:].isin(DATA_KNOWN)
    operating = code2.str[0].isin(OPERATING)
    valid = code2.str[2:].isin(DATA_OK)
    return pd.Series(
        np.select([~known, ~operating, ~valid], ["UNKNOWN_STATUS", "NOT_OPERATING", "INVALID_DATA"], "NORMAL"),
        index=code2.index,
    )


def to_silver(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=str.lower)
    df = df[df["item"].isin(ITEMS) & (df["unit"] == "ppm")].copy()
    df["record_state"] = record_state(df["code2"].fillna(""))
    df = df[df["record_state"] == "NORMAL"]
    df["measure_value"] = pd.to_numeric(df["m_value"], errors="coerce")
    df["standard_value"] = pd.to_numeric(df["std"], errors="coerce").where(lambda s: s > 0)
    df["measured_at"] = pd.to_datetime(df["m_time"]) - pd.Timedelta(hours=8)  # UTC+8 -> UTC
    df["slot"] = df["measured_at"].dt.floor("30min")
    df["stack_code"] = "TW-" + df["cno"] + "-" + df["polno"]
    df["item_code"] = df["item"].map(ITEMS)

    keys = ["stack_code", "item_code", "slot"]
    g = df.dropna(subset=["measure_value"]).groupby(keys)
    out = g.agg(
        measure_value=("measure_value", "mean"),
        standard_value=("standard_value", "first"),
        std_basis=("std_s", "first"),
        n_values=("measure_value", "size"),
        n_standards=("standard_value", "nunique"),
    ).reset_index()
    out = out[(out["n_values"] == 2) & (out["n_standards"] <= 1)].rename(columns={"slot": "measured_at"})
    out["ratio_pct"] = out["measure_value"] / out["standard_value"] * 100
    out.insert(0, "data_origin", ORIGIN)
    return out.drop(columns=["n_values", "n_standards"]).sort_values(["stack_code", "item_code", "measured_at"]).reset_index(drop=True)


def build(source: Path, silver_dir: Path) -> Path:
    # ponytail: whole month in memory (~230MB JSON for 3 days of 15-min rows), chunk by stack if monthly files get too big
    raw = pd.DataFrame(json.loads(source.read_text(encoding="utf-8-sig")))
    silver = to_silver(raw)
    out = silver_dir / "tw_cems" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    silver.to_parquet(out, index=False)
    print(f"tw_cems: {len(raw):,} raw rows -> {len(silver):,} 30-min rows, {silver['stack_code'].nunique()} stacks")
    print(silver.groupby("item_code")["ratio_pct"].agg(rows="size", has_std="count", ge90=lambda s: (s >= 90).sum()).to_string())
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Taiwan CEMS 15-minute JSON -> silver parquet")
    p.add_argument("source", type=Path)
    p.add_argument("--silver-dir", type=Path, default=Path("data/silver"))
    a = p.parse_args()
    build(a.source, a.silver_dir)


if __name__ == "__main__":
    main()
