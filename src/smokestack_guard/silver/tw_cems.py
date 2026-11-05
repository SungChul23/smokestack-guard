"""Taiwan CEMS 15-minute records (AQX_P_186 monthly JSON) -> silver in the same long contract as K-TMS silver (ktms.py).

One row per stack x item x 30-minute slot:
    area_nm, fact_manage_nm, stack_code, item, value, limit, status, ts_kst, ratio   (the K-TMS columns)
    + ts_local (Taiwan wall clock, for hour-of-day features), code2 (tracing), flag_code_ratio_mismatch

Rules:
- keep NOX(923) / SOX(922) rows in ppm only; other units are dropped, never converted.
- a 15-minute row is usable when code2 is [N|A]?10 / [N|A]?11 (11 = over the limit, kept), the value is numeric and the limit > 0.
- M_Time is the interval start in Taiwan time (UTC+8) [assumed, unverified]; ts_local keeps it, ts_kst is +1h like K-TMS. A 30-minute slot is the :00 and :15 row.
- slot is ok only with both usable rows and one limit: value = their mean, ratio = value / limit. Nothing is filled or interpolated.
- code2 is kept ("NA10|NA11" when the pair differs); NA10 with ratio >= 1 or NA11 with ratio < 1 is flagged, never dropped.
- other slots keep their row with value NaN and a status: partial (one usable row), invalid (none, or conflicting), not_monitored (no limit).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ITEMS = {"923": "nox", "922": "sox"}  # the ML targets; add "924": "co" here if CO is needed
USABLE_CODE2 = r"[NA].(?:10|11)"
STACK = ["area_nm", "fact_manage_nm", "stack_code"]
COLUMNS = STACK + ["item", "value", "limit", "status", "ts_kst", "ratio", "ts_local", "code2", "flag_code_ratio_mismatch"]
RAW = ["cno", "polno", "item", "unit", "m_time", "m_value", "std", "code2", "abbr", "epb_county"]


def prep(df: pd.DataFrame) -> pd.DataFrame:
    """Drop what silver never uses (other items/units/columns) so a month can be held in memory."""
    df = df.rename(columns=str.lower)
    df = df[df["item"].isin(ITEMS) & (df["unit"] == "ppm")]
    return df.reindex(columns=RAW)


def to_silver(df: pd.DataFrame) -> pd.DataFrame:
    d = prep(df).copy()
    d["item"] = d["item"].map(ITEMS)
    d["area_nm"] = d["epb_county"].fillna("")
    d["fact_manage_nm"] = d["abbr"].fillna("")
    d["stack_code"] = d["cno"] + "-" + d["polno"]  # polno alone repeats across factories
    d["ts"] = pd.to_datetime(d["m_time"]) + pd.Timedelta(hours=1)  # Taipei UTC+8 -> KST UTC+9
    d["slot"] = d["ts"].dt.floor("30min")
    d["pos"] = d["ts"].dt.minute % 30
    d["value"] = pd.to_numeric(d["m_value"], errors="coerce")
    d["limit"] = pd.to_numeric(d["std"], errors="coerce").where(lambda s: s > 0)
    d["code2"] = d["code2"].fillna("")

    d = d.drop_duplicates(STACK + ["item", "ts", "value", "limit", "code2"])  # repeated identical rows
    d["good"] = d["code2"].str.fullmatch(USABLE_CODE2) & d["value"].notna() & d["limit"].notna()
    d.loc[d.duplicated(STACK + ["item", "ts"], keep=False), "good"] = False  # same time, different values: conflict

    d = d.sort_values("ts")
    d["good_value"] = d["value"].where(d["good"])
    d["good_limit"] = d["limit"].where(d["good"])
    d["p0"] = d["good"] & (d["pos"] == 0)
    d["p15"] = d["good"] & (d["pos"] == 15)
    out = d.groupby(STACK + ["item", "slot"]).agg(
        value=("good_value", "mean"),
        limit=("limit", "first"),
        n_limits=("good_limit", "nunique"),
        has_p0=("p0", "any"),
        has_p15=("p15", "any"),
        n_good=("good", "sum"),
        code2_a=("code2", "first"),
        code2_b=("code2", "last"),
    ).reset_index()

    ok = out["has_p0"] & out["has_p15"] & (out["n_limits"] == 1)
    out["status"] = np.select([ok, out["limit"].isna(), out["n_good"] == 1], ["ok", "not_monitored", "partial"], "invalid")
    out["value"] = out["value"].where(ok)
    out["ratio"] = out["value"] / out["limit"]
    out["code2"] = out["code2_a"].where(out["code2_a"] == out["code2_b"], out["code2_a"] + "|" + out["code2_b"])
    both = lambda c: out["code2_a"].str[2:].eq(c) & out["code2_b"].str[2:].eq(c)
    out["flag_code_ratio_mismatch"] = (both("10") & (out["ratio"] >= 1)) | (both("11") & (out["ratio"] < 1))
    out["ts_local"] = out["slot"] - pd.Timedelta(hours=1)
    out = out.rename(columns={"slot": "ts_kst"})
    return out[COLUMNS].sort_values(STACK + ["item", "ts_kst"]).reset_index(drop=True)


def build(source: Path, silver_dir: Path) -> Path:
    # ponytail: a month is held in memory after prep(); chunk by factory (cno) if a month no longer fits
    reader = pd.read_json(source, lines=True, chunksize=250_000, dtype=False)
    raw = pd.concat([prep(chunk) for chunk in reader], ignore_index=True)
    silver = to_silver(raw)
    out = silver_dir / "tw_cems" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    silver.to_parquet(out, index=False)
    print(f"tw_cems: {len(raw):,} usable-item rows -> {len(silver):,} 30-min rows, {silver['stack_code'].nunique()} stacks, status={silver['status'].value_counts().to_dict()}")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Taiwan CEMS 15-minute JSONL -> silver parquet (K-TMS contract)")
    p.add_argument("source", type=Path)
    p.add_argument("--silver-dir", type=Path, default=Path("data/silver"))
    a = p.parse_args()
    build(a.source, a.silver_dir)


if __name__ == "__main__":
    main()
