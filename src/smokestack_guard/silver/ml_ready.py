"""ML-ready feature table derived from the Taiwan CEMS silver output.

This layer follows the "대만 CEMS 데이터 활용" design for model training:
- the upstream silver table is kept as the validated observation layer
- ML-ready adds lag, rolling, time-period, and label features without
  leaking future information into the current row
- the output is meant for model training and evaluation, not for raw data
  integrity checks
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ENTRY_PCT = 90.0
WINDOW = 6  # 3 hours of 30-min slots


FEATURE_VERSION = LABEL_VERSION = QUALITY_POLICY_VERSION = "v1"
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
            "day_of_week": ts.dayofweek.to_numpy(dtype=float),
        },
        index=ts,
    )


def to_ml_ready(df: pd.DataFrame) -> pd.DataFrame:
    """Build the ML-ready silver table from the already-generated 30-minute silver data.

    The input is expected to contain at least the following columns:
      stack_code, item_code, measured_at, measure_value, standard_value, ratio_pct
    """
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)

    if "ts_kst" in df.columns:  # silver in the K-TMS contract (tw_cems.py): usable rows only, ratio as a fraction; local clock drives hour features
        df = df[df["status"] == "ok"].rename(
            columns={"ts_local": "measured_at", "item": "item_code", "value": "measure_value", "limit": "standard_value"}
        ).assign(ratio_pct=lambda x: x["ratio"] * 100)
    out = df.copy()
    required = {"stack_code", "item_code", "measured_at", "ratio_pct"}
    missing = sorted(required - set(out.columns))
    if missing:
        raise ValueError(f"Missing required ML-ready input columns: {missing}")

    out["measured_at"] = pd.to_datetime(out["measured_at"])
    if out["measured_at"].dt.tz is not None:  # always a naive Taiwan wall clock, so hour/month features are local
        out["measured_at"] = out["measured_at"].dt.tz_convert("Asia/Taipei").dt.tz_localize(None)
    out["ratio_pct"] = pd.to_numeric(out["ratio_pct"], errors="coerce")
    out["measure_value"] = pd.to_numeric(out.get("measure_value", pd.Series(np.nan, index=out.index)), errors="coerce")
    out["standard_value"] = pd.to_numeric(out.get("standard_value", pd.Series(np.nan, index=out.index)), errors="coerce")
    out = out.sort_values(["stack_code", "item_code", "measured_at"]).reset_index(drop=True)

    frames = []
    for (stack_code, item_code), g in out.groupby(["stack_code", "item_code"], sort=False):
        g = g.drop_duplicates("measured_at").set_index("measured_at").sort_index()
        # Silver leaves missing slots empty, so shift by time, not by row: put the group on a full 30-minute grid.
        observed = pd.Series(True, index=g.index)
        g = g.reindex(pd.date_range(g.index[0], g.index[-1], freq="30min"))
        observed = observed.reindex(g.index, fill_value=False)

        r = g["ratio_pct"]
        g["headroom_pct"] = ENTRY_PCT - r  # distance to the 90% entry line
        for minutes in LAGS:
            g[f"ratio_lag_{minutes}m"] = r.shift(minutes // 30)

        d = r.diff()  # grid-based, so a missing slot gives NaN instead of bridging the gap
        g["ratio_diff_30m"] = d
        g["ratio_diff_60m"] = r - r.shift(2)
        g["ratio_acceleration"] = d - d.shift(1)
        g["ratio_rolling_mean_1h"] = r.rolling(2, min_periods=2).mean()
        win = r.rolling(WINDOW, min_periods=WINDOW)
        g["ratio_rolling_mean_3h"] = win.mean()
        g["ratio_rolling_std_3h"] = win.std()
        g["ratio_rolling_max_3h"] = win.max()
        g["ratio_range_3h"] = g["ratio_rolling_max_3h"] - win.min()
        # least-squares slope per 30-min slot over the last 6 points: sum((x - mean_x) * y) / sum((x - mean_x)^2)
        g["ratio_slope_3h"] = sum((WINDOW - 1 - j - (WINDOW - 1) / 2) * r.shift(j) for j in range(WINDOW)) / sum(
            (k - (WINDOW - 1) / 2) ** 2 for k in range(WINDOW)
        )
        g["rise_count_3h"] = d.gt(0).astype(float).where(d.notna()).rolling(WINDOW - 1, min_periods=WINDOW - 1).sum()

        for col, values in _time_features(g.index).items():
            g[col] = values.to_numpy()

        # feature: current and the 5 previous slots must all exist (past values only, no future info)
        g["feature_valid"] = r.notna().rolling(WINDOW, min_periods=WINDOW).sum().eq(WINDOW)

        # label: looks only forward from t, judged separately from the features
        g["label_ratio_60m"] = r.shift(-2)
        ahead = pd.concat([r.shift(-1), r.shift(-2)], axis=1)
        reached = ahead.ge(ENTRY_PCT).any(axis=1)
        known = reached | ahead.notna().all(axis=1)  # a miss is only certain when both slots exist
        below = r < ENTRY_PCT
        # 1 = a new entry at +30 or +60 min; 0 = no entry; NaN = already >= 90 now, or not decidable
        g["label_entry_60m"] = np.where(below & known, np.where(reached, 1.0, 0.0), np.nan)
        g["classification_eligible"] = g["feature_valid"] & g["label_entry_60m"].notna()
        g["regression_eligible"] = g["feature_valid"] & g["label_ratio_60m"].notna() & below  # initial scope: current < 90%

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


def build(source: Path, output_dir: Path) -> Path:
    """Read a parquet silver table and write the ML-ready silver parquet output."""
    silver = pd.read_parquet(source)
    ml_ready = to_ml_ready(silver)
    out = output_dir / "tw_cems_ml_ready" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    ml_ready.to_parquet(out, index=False)
    print(f"tw_cems_ml_ready: {len(silver):,} silver rows -> {len(ml_ready):,} ml-ready rows")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Taiwan CEMS silver -> ML-ready silver")
    parser.add_argument("source", type=Path, help="Path to a silver parquet file")
    parser.add_argument("--output-dir", type=Path, default=Path("data/silver"))
    args = parser.parse_args()
    build(args.source, args.output_dir)


if __name__ == "__main__":
    main()
