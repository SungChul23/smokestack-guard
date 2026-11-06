"""Taiwan CEMS 15-minute records (AQX_P_186 monthly JSON) -> silver in the same long contract as K-TMS silver (ktms.py).

One row per stack x item x unit x 30-minute slot:
    area_nm, fact_manage_nm, stack_code, item, value, limit, status, ts_kst, ratio   (the K-TMS columns)
    + unit, ts_local (Taiwan wall clock, for hour-of-day features), code2 (tracing), flag_code_ratio_mismatch

Rules:
- every item is converted (nox, sox, co, ..., o2, flow, temp); units differ per item, so `unit` is kept and nothing is converted.
  Choosing what a model may use (nox/sox in ppm, status ok) is the ML-ready layer's job, not silver's.
- M_Time is the interval start in Taiwan time (UTC+8) [verified against the hourly dataset AQX_P_187, 2025-10: hourly T == mean of the 15-min rows T, T+15, T+30, T+45]; ts_local keeps it, ts_kst is +1h like K-TMS. A 30-minute slot is the :00 and :15 row.
- a slot has a value when both rows are numeric and there is at most one limit: value = their mean, ratio = value / limit. Nothing is filled or interpolated.
- the status says whether the slot is fit for ML:
    ok            both rows NA10/NA11 and a limit exists   (11 = over the limit, kept)
    other_code    value present but a row is not NA10/NA11 (FA10 stopped, NB/AA ..): kept so the policy can be widened without a re-run
    not_monitored value present, both NA10/NA11, no limit  (o2/flow/temp and most items without a standard)
    partial       only one numeric row, value empty
    invalid       no numeric row, or two different limits, value empty
- code2 is kept ("NA10|NA11" when the pair differs); NA10 with ratio >= 1 or NA11 with ratio < 1 is flagged, never dropped.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ITEMS = {"912": "pm", "922": "sox", "923": "nox", "924": "co", "925": "trs", "926": "hcl", "927": "voc", "936": "o2", "948": "flow", "959": "temp"}
USABLE_CODE2 = r"NA(?:10|11)"  # initial ML policy: normal operation + normal measurement
STACK = ["area_nm", "fact_manage_nm", "stack_code"]
COLUMNS = STACK + ["item", "unit", "value", "limit", "status", "ts_kst", "ratio", "ts_local", "code2", "flag_code_ratio_mismatch"]
RAW = ["cno", "polno", "item", "unit", "m_time", "m_value", "std", "code2", "abbr", "epb_county"]
TEXT = STACK + ["item", "unit", "code2"]


def prep(df: pd.DataFrame) -> pd.DataFrame:
    """Parse and shrink the raw rows (typed, compact text) so a whole month can be held in memory."""
    df = df.rename(columns=str.lower).reindex(columns=RAW)
    d = pd.DataFrame({
        "area_nm": df["epb_county"].fillna(""),
        "fact_manage_nm": df["abbr"].fillna(""),
        "stack_code": df["cno"] + "-" + df["polno"],  # polno alone repeats across factories
        "item": df["item"].map(lambda c: ITEMS.get(c, c)),  # unknown codes keep their number
        "unit": df["unit"].fillna(""),
        # Taipei UTC+8 -> KST UTC+9; ISO8601 accepts both "T" and space separators (some months mix them)
        "ts": pd.to_datetime(df["m_time"], format="ISO8601") + pd.Timedelta(hours=1),
        "value": pd.to_numeric(df["m_value"], errors="coerce"),
        "limit": pd.to_numeric(df["std"], errors="coerce").where(lambda s: s > 0),
        "code2": df["code2"].fillna(""),
    })
    return d.astype({c: "string[pyarrow]" for c in TEXT})


def to_silver(df: pd.DataFrame) -> pd.DataFrame:
    d = (df if "ts" in df.columns else prep(df)).copy()
    key = STACK + ["item", "unit"]
    d = d.drop_duplicates(key + ["ts", "value", "limit", "code2"])  # repeated identical rows
    d["slot"] = d["ts"].dt.floor("30min")
    pos = d["ts"].dt.minute % 30
    num = d["value"].notna() & ~d.duplicated(key + ["ts"], keep=False)  # same time, different values: conflict
    d["num"] = num
    d["num_value"] = d["value"].where(num)
    d["num_limit"] = d["limit"].where(num)
    d["p0"] = num & (pos == 0)
    d["p15"] = num & (pos == 15)
    d["code_ok"] = num & d["code2"].str.fullmatch(USABLE_CODE2).fillna(False).astype(bool)

    d = d.sort_values("ts")
    out = d.groupby(key + ["slot"]).agg(
        value=("num_value", "mean"),
        limit=("limit", "first"),
        n_limits=("num_limit", "nunique"),
        has_p0=("p0", "any"),
        has_p15=("p15", "any"),
        n_num=("num", "sum"),
        n_code_ok=("code_ok", "sum"),
        code2_a=("code2", "first"),
        code2_b=("code2", "last"),
    ).reset_index()
    out[["code2_a", "code2_b"]] = out[["code2_a", "code2_b"]].astype(object)

    pair = out["has_p0"] & out["has_p15"] & (out["n_limits"] <= 1)
    both_ok = pair & (out["n_code_ok"] == 2)
    out["status"] = np.select(
        [both_ok & out["limit"].notna(), both_ok, pair, out["n_num"] == 1],
        ["ok", "not_monitored", "other_code", "partial"],
        "invalid",
    )
    out["value"] = out["value"].where(pair)
    out["ratio"] = out["value"] / out["limit"]
    out["code2"] = out["code2_a"].where(out["code2_a"] == out["code2_b"], out["code2_a"] + "|" + out["code2_b"])
    both = lambda c: (out["code2_a"] == f"NA{c}") & (out["code2_b"] == f"NA{c}")
    out["flag_code_ratio_mismatch"] = (both("10") & (out["ratio"] >= 1)) | (both("11") & (out["ratio"] < 1))
    out["ts_local"] = out["slot"] - pd.Timedelta(hours=1)
    out = out.rename(columns={"slot": "ts_kst"})
    return out[COLUMNS].sort_values(STACK + ["item", "unit", "ts_kst"]).reset_index(drop=True)


def build(source: Path, silver_dir: Path) -> Path:
    # ponytail: a month is held in memory after prep(); chunk by factory (cno) if a month no longer fits
    reader = pd.read_json(source, lines=True, chunksize=250_000, dtype=False)
    raw = pd.concat([prep(chunk) for chunk in reader], ignore_index=True)
    silver = to_silver(raw)
    out = silver_dir / "tw_cems" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    silver.to_parquet(out, index=False)
    print(f"tw_cems: {len(raw):,} rows -> {len(silver):,} 30-min rows, {silver['stack_code'].nunique()} stacks, status={silver['status'].value_counts().to_dict()}")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Taiwan CEMS 15-minute JSONL -> silver parquet (K-TMS contract)")
    p.add_argument("source", type=Path)
    p.add_argument("--silver-dir", type=Path, default=Path("data/silver"))
    a = p.parse_args()
    build(a.source, a.silver_dir)


if __name__ == "__main__":
    main()
