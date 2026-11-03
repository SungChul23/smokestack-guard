"""ECMPS bronze (hourly CSV per monitor plan/quarter) -> silver (one row per unit-hour, wide).

Silver rules:
- value = unadjusted_hourly_value (measured); the adjusted value is only filled for ~15% of rows (FLOW bias adjustment).
- entity = unit_id, or stack_pipe_id for stack-level rows (unit_id is empty there).
- several components can report the same parameter in an hour: keep the primary-monitor (MODC 01) row.
- MODC codes are kept as `<PARAM>_modc`; only 01 is treated as a clean measurement.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

PARAMS = ["NOXC", "SO2C", "O2C", "CO2C", "H2O", "FLOW"]
KEYS = ["facility_id", "unit_id", "stack_pipe_id", "monitor_plan_id", "date", "hour"]


def read_bronze(files: list[Path]) -> pd.DataFrame:
    cols = KEYS + ["parameter_code", "unadjusted_hourly_value", "modc_code", "operating_time", "component_id"]
    # the collector may still be writing, so skip files that have no header yet
    frames = [pd.read_csv(f, encoding="utf-8-sig", dtype=str, usecols=cols) for f in files if f.stat().st_size > 0]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols)


def to_silver(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["parameter_code"].isin(PARAMS)].copy()
    df["hour"] = pd.to_numeric(df["hour"], errors="coerce")
    df = df[df["hour"].between(0, 23)]
    df["hour"] = df["hour"].astype(int)
    df["value"] = pd.to_numeric(df["unadjusted_hourly_value"], errors="coerce")
    df["operating_time"] = pd.to_numeric(df["operating_time"], errors="coerce")
    df["entity_id"] = df["unit_id"].fillna(df["stack_pipe_id"])
    df = df.dropna(subset=["entity_id"])

    key = ["facility_id", "entity_id", "monitor_plan_id", "date", "hour"]
    # primary monitor first, then drop repeated parameters from backup components
    df = df.sort_values("modc_code", key=lambda s: s != "01").drop_duplicates(key + ["parameter_code"])

    wide = df.pivot(index=key, columns="parameter_code", values="value").reindex(columns=PARAMS)
    modc = df.pivot(index=key, columns="parameter_code", values="modc_code").reindex(columns=PARAMS)
    modc.columns = [f"{p}_modc" for p in PARAMS]
    meta = df.groupby(key).agg(
        unit_id=("unit_id", "first"), stack_pipe_id=("stack_pipe_id", "first"), operating_time=("operating_time", "max")
    )
    out = pd.concat([meta, wide, modc], axis=1).reset_index()
    out["ts_local"] = pd.to_datetime(out["date"]) + pd.to_timedelta(out["hour"], unit="h")  # local standard time
    out["operating"] = out["operating_time"].fillna(0) > 0
    out["year"] = out["ts_local"].dt.year
    out["quarter"] = out["ts_local"].dt.quarter
    first = ["facility_id", "entity_id", "unit_id", "stack_pipe_id", "monitor_plan_id", "ts_local", "operating_time", "operating"]
    return out.drop(columns=["date", "hour"])[first + PARAMS + [f"{p}_modc" for p in PARAMS] + ["year", "quarter"]]


def build(raw_dir: Path, silver_dir: Path) -> list[Path]:
    """Rewrite one parquet per quarter, so a rerun is idempotent."""
    by_quarter: dict[str, list[Path]] = {}
    for f in sorted(raw_dir.glob("epa_emissions_*_*q[1-4].csv")):
        by_quarter.setdefault(f.stem.rsplit("_", 1)[1], []).append(f)
    written = []
    for tag, files in sorted(by_quarter.items()):
        silver = to_silver(read_bronze(files))
        if silver.empty:
            continue
        out = silver_dir / "ecmps" / f"year={tag[:4]}" / f"quarter={tag[-1]}" / "part.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        silver.to_parquet(out, index=False)
        written.append(out)
        print(f"{tag}: {len(files)} files -> {len(silver):,} unit-hours")
    return written


def main() -> None:
    p = argparse.ArgumentParser(description="ECMPS bronze CSV -> silver parquet")
    p.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    p.add_argument("--silver-dir", type=Path, default=Path("data/silver"))
    a = p.parse_args()
    build(a.raw_dir, a.silver_dir)


if __name__ == "__main__":
    main()
