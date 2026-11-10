"""Silver -> ML-ready: lag/trend/time features from past slots, labels from future slots, per stack and item."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ENTRY_PCT = 90.0
ML_ITEMS = ["nox", "sox"]
WINDOW = 6  # 30-min slots in 3 hours
FEATURE_VERSION = LABEL_VERSION = "v1"
QUALITY_POLICY_VERSION = "v2"
LAGS = [30, 60, 90, 120, 150]
COLUMNS = (
    ["stack_code", "item_code", "measured_at", "ratio_pct", "headroom_pct", "measure_value", "standard_value"]
    + [f"ratio_lag_{m}m" for m in LAGS]
    + ["ratio_diff_30m", "ratio_diff_60m", "ratio_rolling_mean_1h", "ratio_rolling_mean_3h", "ratio_rolling_std_3h",
       "ratio_rolling_max_3h", "ratio_range_3h", "ratio_slope_3h", "rise_count_3h", "ratio_acceleration",
       "hour_sin", "hour_cos", "month_sin", "month_cos", "day_of_week",
       "label_entry_60m", "label_ratio_60m",
       "feature_valid", "classification_eligible", "regression_eligible",
       "feature_version", "label_version", "quality_policy_version"]
)


def _time_features(ts: pd.DatetimeIndex) -> pd.DataFrame:
    hours = ts.hour.to_numpy(dtype=float)
    months = ts.month.to_numpy(dtype=float)
    return pd.DataFrame(
        {
            "hour_sin": np.sin(2 * np.pi * hours / 24.0),
            "hour_cos": np.cos(2 * np.pi * hours / 24.0),
            "month_sin": np.sin(2 * np.pi * months / 12.0),
            "month_cos": np.cos(2 * np.pi * months / 12.0),
            "day_of_week": ts.day_of_week.to_numpy(dtype=float),
        },
        index=ts,
    )


def to_ml_ready(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)

    if "ts_kst" in df.columns:  # silver (tw_cems or ktms): keep the slots the model may use
        df = df[(df["status"] == "ok") & df["item"].isin(ML_ITEMS)]
        if "unit" in df.columns:  # ktms has no unit column; its nox/sox are taken as ppm
            df = df[df["unit"] == "ppm"]
        clock = "ts_local" if "ts_local" in df.columns else "ts_kst"
        if clock == "ts_kst":  # ktms: no single stack id, so area + facility + stack_code
            df = df.assign(stack_code=df["area_nm"] + "|" + df["fact_manage_nm"] + "|" + df["stack_code"])
        df = df.rename(
            columns={clock: "measured_at", "item": "item_code", "value": "measure_value", "limit": "standard_value"}
        ).assign(ratio_pct=lambda x: x["ratio"] * 100)
    out = df.copy()
    required = {"stack_code", "item_code", "measured_at", "ratio_pct"}
    missing = sorted(required - set(out.columns))
    if missing:
        raise ValueError(f"Missing required ML-ready input columns: {missing}")

    out["measured_at"] = pd.to_datetime(out["measured_at"])
    if out["measured_at"].dt.tz is not None:  # hour/month features use the Taiwan wall clock
        out["measured_at"] = out["measured_at"].dt.tz_convert("Asia/Taipei").dt.tz_localize(None)
    out["ratio_pct"] = pd.to_numeric(out["ratio_pct"], errors="coerce")
    out["measure_value"] = pd.to_numeric(out.get("measure_value", pd.Series(np.nan, index=out.index)), errors="coerce")
    out["standard_value"] = pd.to_numeric(out.get("standard_value", pd.Series(np.nan, index=out.index)), errors="coerce")
    out = out.sort_values(["stack_code", "item_code", "measured_at"]).reset_index(drop=True)

    frames = []
    for (stack_code, item_code), g in out.groupby(["stack_code", "item_code"], sort=False):
        g = g.drop_duplicates("measured_at").set_index("measured_at").sort_index()
        # full 30-min grid, so lags and labels shift by time and never bridge a gap
        observed = pd.Series(True, index=g.index)
        g = g.reindex(pd.date_range(g.index[0], g.index[-1], freq="30min"))
        observed = observed.reindex(g.index, fill_value=False)

        r = g["ratio_pct"]
        g["headroom_pct"] = ENTRY_PCT - r
        for minutes in LAGS:
            g[f"ratio_lag_{minutes}m"] = r.shift(minutes // 30)

        d = r.diff()
        g["ratio_diff_30m"] = d
        g["ratio_diff_60m"] = r - r.shift(2)
        g["ratio_acceleration"] = d - d.shift(1)
        g["ratio_rolling_mean_1h"] = r.rolling(2, min_periods=2).mean()
        win = r.rolling(WINDOW, min_periods=WINDOW)
        g["ratio_rolling_mean_3h"] = win.mean()
        g["ratio_rolling_std_3h"] = win.std()
        g["ratio_rolling_max_3h"] = win.max()
        g["ratio_range_3h"] = g["ratio_rolling_max_3h"] - win.min()
        # least-squares slope per slot over the last WINDOW points
        g["ratio_slope_3h"] = sum((WINDOW - 1 - j - (WINDOW - 1) / 2) * r.shift(j) for j in range(WINDOW)) / sum(
            (k - (WINDOW - 1) / 2) ** 2 for k in range(WINDOW)
        )
        g["rise_count_3h"] = d.gt(0).astype(float).where(d.notna()).rolling(WINDOW - 1, min_periods=WINDOW - 1).sum()

        for col, values in _time_features(g.index).items():
            g[col] = values.to_numpy()

        g["feature_valid"] = r.notna().rolling(WINDOW, min_periods=WINDOW).sum().eq(WINDOW)

        g["label_ratio_60m"] = r.shift(-2)
        ahead = pd.concat([r.shift(-1), r.shift(-2)], axis=1)
        reached = ahead.ge(ENTRY_PCT).any(axis=1)
        known = reached | ahead.notna().all(axis=1)  # "no entry" needs both slots
        below = r < ENTRY_PCT
        # 1 = reaches 90% at +30/+60 min, 0 = does not, NaN = already >= 90% or undecidable
        g["label_entry_60m"] = np.where(below & known, np.where(reached, 1.0, 0.0), np.nan)
        # two different limits seen in a row's window (150 min back .. 60 min ahead) taint that row,
        # even when slots between them are missing
        sv = g["standard_value"]
        limit_changed = (sv.rolling(WINDOW + 2, min_periods=1).max() - sv.rolling(WINDOW + 2, min_periods=1).min()).shift(-2).fillna(0).gt(0)
        g["classification_eligible"] = g["feature_valid"] & g["label_entry_60m"].notna() & ~limit_changed
        g["regression_eligible"] = g["feature_valid"] & g["label_ratio_60m"].notna() & ~limit_changed

        g = g[observed.to_numpy()]
        g["stack_code"] = stack_code
        g["item_code"] = item_code
        g = g.rename_axis("measured_at").reset_index()
        frames.append(g)

    if not frames:
        return pd.DataFrame(columns=COLUMNS)

    result = pd.concat(frames, ignore_index=True)
    result = result.sort_values(["stack_code", "item_code", "measured_at"]).reset_index(drop=True)
    result["feature_version"], result["label_version"], result["quality_policy_version"] = FEATURE_VERSION, LABEL_VERSION, QUALITY_POLICY_VERSION
    return result[COLUMNS]


def build(source: Path, output_dir: Path, table: str = "tw_cems_ml_ready") -> Path:
    files = sorted(source.glob("ts_date=*/part.parquet")) if source.is_dir() else [source]  # ktms: partitions only
    silver = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    ml_ready = to_ml_ready(silver)
    out = output_dir / table / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    ml_ready.to_parquet(out, index=False)
    print(f"{table}: {len(silver):,} silver rows -> {len(ml_ready):,} ml-ready rows")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Taiwan CEMS / K-TMS silver -> ML-ready silver")
    parser.add_argument("source", type=Path, help="Path to a silver parquet file or partition directory")
    parser.add_argument("--output-dir", type=Path, default=Path("data/silver"))
    parser.add_argument("--table", default="tw_cems_ml_ready", help="output table name, e.g. ktms_ml_ready")
    args = parser.parse_args()
    build(args.source, args.output_dir, args.table)


if __name__ == "__main__":
    main()
