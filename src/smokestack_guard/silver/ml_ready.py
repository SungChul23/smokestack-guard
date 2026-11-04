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


def _time_features(ts: pd.DatetimeIndex) -> pd.DataFrame:
    hours = ts.hour.to_numpy(dtype=float)
    months = ts.month.to_numpy(dtype=float)
    dow = ts.dayofweek.to_numpy(dtype=float)

    return pd.DataFrame(
        {
            "hour_sin": np.sin(2 * np.pi * hours / 24.0),
            "hour_cos": np.cos(2 * np.pi * hours / 24.0),
            "month_sin": np.sin(2 * np.pi * months / 12.0),
            "month_cos": np.cos(2 * np.pi * months / 12.0),
            "dow_sin": np.sin(2 * np.pi * dow / 7.0),
            "dow_cos": np.cos(2 * np.pi * dow / 7.0),
        },
        index=ts,
    )


def to_ml_ready(df: pd.DataFrame) -> pd.DataFrame:
    """Build the ML-ready silver table from the already-generated 30-minute silver data.

    The input is expected to contain at least the following columns:
      stack_code, item_code, measured_at, measure_value, standard_value, ratio_pct
    """
    if df.empty:
        return pd.DataFrame(
            columns=[
                "stack_code",
                "item_code",
                "measured_at",
                "measure_value",
                "standard_value",
                "ratio_pct",
                "headroom_pct",
                "lag_30m",
                "lag_60m",
                "lag_90m",
                "lag_120m",
                "lag_150m",
                "delta_30m",
                "delta_60m",
                "rolling_mean_180m",
                "rolling_std_180m",
                "hour_sin",
                "hour_cos",
                "month_sin",
                "month_cos",
                "dow_sin",
                "dow_cos",
                "feature_valid",
                "label_ratio_60m",
                "label_entry_60m",
                "label_valid",
            ]
        )

    out = df.copy()
    out = out.rename(columns={"measured_at": "measured_at"})
    required = {"stack_code", "item_code", "measured_at", "ratio_pct"}
    missing = sorted(required - set(out.columns))
    if missing:
        raise ValueError(f"Missing required ML-ready input columns: {missing}")

    out["measured_at"] = pd.to_datetime(out["measured_at"], utc=True)
    out["ratio_pct"] = pd.to_numeric(out["ratio_pct"], errors="coerce")
    out["measure_value"] = pd.to_numeric(out.get("measure_value", pd.Series(np.nan, index=out.index)), errors="coerce")
    out["standard_value"] = pd.to_numeric(out.get("standard_value", pd.Series(np.nan, index=out.index)), errors="coerce")
    out = out.sort_values(["stack_code", "item_code", "measured_at"]).reset_index(drop=True)

    frames = []
    for (stack_code, item_code), g in out.groupby(["stack_code", "item_code"], sort=False):
        g = g.sort_values("measured_at").copy()
        g = g.set_index("measured_at")

        g["headroom_pct"] = 100.0 - g["ratio_pct"]
        for minutes, periods in [(30, 1), (60, 2), (90, 3), (120, 4), (150, 5)]:
            g[f"lag_{minutes}m"] = g["ratio_pct"].shift(periods)

        g["delta_30m"] = g["ratio_pct"] - g["ratio_pct"].shift(1)
        g["delta_60m"] = g["ratio_pct"] - g["ratio_pct"].shift(2)

        window = 6
        g["rolling_mean_180m"] = g["ratio_pct"].rolling(window=window, min_periods=window).mean()
        g["rolling_std_180m"] = g["ratio_pct"].rolling(window=window, min_periods=window).std()

        time_df = _time_features(g.index)
        for col in time_df.columns:
            g[col] = time_df[col].to_numpy()

        valid_window = g["ratio_pct"].notna().rolling(window=window, min_periods=window).sum()
        g["feature_valid"] = valid_window.eq(window)

        # 60-minute label target, represented as two 30-minute steps ahead.
        g["label_ratio_60m"] = g["ratio_pct"].shift(-2)
        label_valid = g["label_ratio_60m"].notna()
        current_below = g["ratio_pct"] < 90
        g["label_entry_60m"] = np.where(
            label_valid & current_below,
            np.where(g["label_ratio_60m"] < 90, 1, 0),
            np.nan,
        )
        g["label_valid"] = label_valid & g["feature_valid"]

        g["stack_code"] = stack_code
        g["item_code"] = item_code
        g = g.reset_index().rename(columns={"index": "measured_at"})
        frames.append(g)

    if not frames:
        return pd.DataFrame(columns=[
            "stack_code",
            "item_code",
            "measured_at",
            "measure_value",
            "standard_value",
            "ratio_pct",
            "headroom_pct",
            "lag_30m",
            "lag_60m",
            "lag_90m",
            "lag_120m",
            "lag_150m",
            "delta_30m",
            "delta_60m",
            "rolling_mean_180m",
            "rolling_std_180m",
            "hour_sin",
            "hour_cos",
            "month_sin",
            "month_cos",
            "dow_sin",
            "dow_cos",
            "feature_valid",
            "label_ratio_60m",
            "label_entry_60m",
            "label_valid",
        ])

    result = pd.concat(frames, ignore_index=True)
    result = result.sort_values(["stack_code", "item_code", "measured_at"]).reset_index(drop=True)
    return result


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
