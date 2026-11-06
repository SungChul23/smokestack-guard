"""Taiwan CEMS 15-minute records -> silver, one row per stack x item x unit x 30-minute slot (K-TMS silver contract).

A slot is the :00 and :15 rows (m_time is the interval start, Taiwan time). Nothing is filled or interpolated.
status:
  ok             both rows numeric and NA10/NA11, one limit
  not_monitored  same, but no limit
  other_code     both rows numeric, a row is not NA10/NA11 (value kept)
  partial        one numeric row
  invalid        no numeric row, or two different limits
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ITEMS = {"912": "pm", "922": "sox", "923": "nox", "924": "co", "925": "trs", "926": "hcl", "927": "voc", "936": "o2", "948": "flow", "959": "temp"}
USABLE_CODE2 = r"NA(?:10|11)"
STACK = ["area_nm", "fact_manage_nm", "stack_code"]
COLUMNS = STACK + ["item", "unit", "value", "limit", "status", "ts_kst", "ratio", "ts_local", "code2", "flag_code_ratio_mismatch"]
RAW = ["cno", "polno", "item", "unit", "m_time", "m_value", "std", "code2", "abbr", "epb_county"]
TEXT = STACK + ["item", "unit", "code2"]


def prep(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=str.lower).reindex(columns=RAW)
    d = pd.DataFrame({
        "area_nm": df["epb_county"].fillna(""),
        "fact_manage_nm": df["abbr"].fillna(""),
        "stack_code": df["cno"] + "-" + df["polno"],
        "item": df["item"].map(lambda c: ITEMS.get(c, c)),
        "unit": df["unit"].fillna(""),
        "ts": pd.to_datetime(df["m_time"], format="ISO8601") + pd.Timedelta(hours=1),  # Taipei -> KST; months mix "T"/space separators
        "value": pd.to_numeric(df["m_value"], errors="coerce"),
        "limit": pd.to_numeric(df["std"], errors="coerce").where(lambda s: s > 0),
        "code2": df["code2"].fillna(""),
    })
    return d.astype({c: "string[pyarrow]" for c in TEXT})


def to_silver(df: pd.DataFrame) -> pd.DataFrame:
    d = (df if "ts" in df.columns else prep(df)).copy()
    key = STACK + ["item", "unit"]
    d = d.drop_duplicates(key + ["ts", "value", "limit", "code2"])
    d["slot"] = d["ts"].dt.floor("30min")
    pos = d["ts"].dt.minute % 30
    num = d["value"].notna() & ~d.duplicated(key + ["ts"], keep=False)  # same time with different values is a conflict
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
    reader = pd.read_json(source, lines=True, chunksize=250_000, dtype=False)
    raw = pd.concat([prep(chunk) for chunk in reader], ignore_index=True)  # one month is held in memory
    silver = to_silver(raw)
    out = silver_dir / "tw_cems" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    silver.to_parquet(out, index=False)
    print(f"tw_cems: {len(raw):,} rows -> {len(silver):,} 30-min rows, {silver['stack_code'].nunique()} stacks, status={silver['status'].value_counts().to_dict()}")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Taiwan CEMS 15-minute JSONL -> silver parquet")
    p.add_argument("source", type=Path)
    p.add_argument("--silver-dir", type=Path, default=Path("data/silver"))
    a = p.parse_args()
    build(a.source, a.silver_dir)


if __name__ == "__main__":
    main()
