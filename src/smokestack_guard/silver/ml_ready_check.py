"""ML-ready 테이블이 컬럼 계약(36컬럼, 정의·규칙 버전)을 지키는지 검사한다. 합성데이터 테이블(ktms_synth)도 같은 검사를 통과해야 한다.

검사는 두 가지다.
 1. 형식: 컬럼 목록·순서, data_source(비어 있지 않고 한 값), 버전 컬럼, 키(stack_code, item_code, measured_at) 중복
 2. 재계산: 테이블의 원본 열(ratio_pct·measure_value·standard_value)만으로 to_ml_ready를 다시 돌려 모든 Feature·라벨·적격 여부가 같은지
테이블이 기간 일부만 담으면 앞뒤 가장자리 행은 재계산 값이 달라질 수 있다(이력·미래 슬롯이 잘려서). 그 차이는 불일치로 보고된다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from smokestack_guard.silver.ml_ready import (
    COLUMNS,
    ENTRY_PCT,
    FEATURE_VERSION,
    LABEL_VERSION,
    QUALITY_POLICY_VERSION,
    to_ml_ready,
)

KEY = ["stack_code", "item_code", "measured_at"]
SOURCE_COLUMNS = KEY + ["ratio_pct", "measure_value", "standard_value"]
SKIP_RECOMPUTE = {"data_source", "feature_version", "label_version", "quality_policy_version"}
VERSIONS = {"feature_version": FEATURE_VERSION, "label_version": LABEL_VERSION, "quality_policy_version": QUALITY_POLICY_VERSION}


def _format_checks(df: pd.DataFrame, expected_source: str | None) -> list[str]:
    bad = []
    if list(df.columns) != COLUMNS:
        missing, extra = [c for c in COLUMNS if c not in df.columns], [c for c in df.columns if c not in COLUMNS]
        bad.append(f"컬럼 불일치: 없음 {missing}, 추가 {extra}, 순서 {'다름' if not (missing or extra) else '확인 불가'}")
        return bad
    sources = df["data_source"].dropna().unique().tolist()
    if df["data_source"].isna().any() or len(sources) != 1:
        bad.append(f"data_source는 비어 있지 않은 한 값이어야 한다: 값 {sources}, 빈 행 {int(df['data_source'].isna().sum())}")
    elif expected_source and sources[0] != expected_source:
        bad.append(f"data_source가 {sources[0]!r}이다(기대: {expected_source!r})")
    for col, want in VERSIONS.items():
        got = df[col].dropna().unique().tolist()
        if got != [want] or df[col].isna().any():
            bad.append(f"{col}는 {want!r}이어야 한다: {got}")
    dup = int(df.duplicated(KEY).sum())
    if dup:
        bad.append(f"키 중복 {dup}행")
    return bad


def _rule_checks(df: pd.DataFrame) -> list[str]:
    bad = []
    both = df["measure_value"].notna() & df["standard_value"].gt(0)
    err = (df["measure_value"] / df["standard_value"] * 100 - df["ratio_pct"])[both].abs()
    if (err > 1e-6).any():
        bad.append(f"ratio_pct != measure_value / standard_value × 100: {int((err > 1e-6).sum())}행")
    head = (ENTRY_PCT - df["ratio_pct"] - df["headroom_pct"]).abs()
    if (head > 1e-6).any():
        bad.append(f"headroom_pct != 90 − ratio_pct: {int((head > 1e-6).sum())}행")
    if not df["label_entry_60m"].dropna().isin([0.0, 1.0]).all():
        bad.append("label_entry_60m은 0, 1, 비움이어야 한다")
    cls = df["classification_eligible"].astype(bool)
    if (cls & (df["label_entry_60m"].isna() | ~df["feature_valid"].astype(bool))).any():
        bad.append("classification_eligible인데 라벨이 없거나 feature_valid가 아닌 행이 있다")
    reg = df["regression_eligible"].astype(bool)
    if (reg & (df["label_ratio_60m"].isna() | ~df["feature_valid"].astype(bool))).any():
        bad.append("regression_eligible인데 라벨이 없거나 feature_valid가 아닌 행이 있다")
    part = df["partial_history_usable"].astype(bool)
    if (part & (df["label_entry_60m"].isna() | df["ratio_lag_30m"].isna() | df["feature_valid"].astype(bool))).any():
        bad.append("partial_history_usable인데 라벨·직전 30분 값이 없거나 feature_valid인 행이 있다")
    return bad


def _recompute_checks(df: pd.DataFrame, atol: float) -> list[str]:
    src = df[SOURCE_COLUMNS].copy()
    again = to_ml_ready(src, data_source="check").sort_values(KEY).reset_index(drop=True)
    cur = df.sort_values(KEY).reset_index(drop=True)
    if len(again) != len(cur):
        return [f"재계산 행 수 {len(again)} != 테이블 {len(cur)}"]
    bad = []
    for col in COLUMNS:
        if col in SKIP_RECOMPUTE or col in KEY:
            continue
        a, b = again[col], cur[col]
        if a.dtype == bool or b.dtype == bool or a.dtype == object:
            diff = a.astype("object").fillna(-1).ne(b.astype("object").fillna(-1))
        else:
            a, b = a.astype("float64"), b.astype("float64")
            diff = ~((a - b).abs() <= atol) & ~(a.isna() & b.isna())
        if diff.any():
            first = cur.loc[diff.idxmax(), KEY].tolist()
            bad.append(f"재계산 불일치 {col}: {int(diff.sum())}행 (첫 행 {first})")
    return bad


def check(df: pd.DataFrame, expected_source: str | None = None, real_stacks: set[str] | None = None, atol: float = 1e-4) -> list[str]:
    """계약 위반 목록을 돌려준다(비어 있으면 통과). real_stacks를 주면 실데이터와 굴뚝 키가 겹치는지도 본다."""
    bad = _format_checks(df, expected_source)
    if bad and list(df.columns) != COLUMNS:
        return bad
    bad += _rule_checks(df) + _recompute_checks(df, atol)
    if real_stacks:
        shared = set(df["stack_code"].unique()) & real_stacks
        if shared:
            bad.append(f"실데이터와 굴뚝 키가 겹친다: {len(shared)}개 (예: {sorted(shared)[:3]})")
    return bad


def _read(path: Path, item: str | None) -> pd.DataFrame:
    files = sorted(path.rglob("*.parquet")) if path.is_dir() else [path]
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    return df[df["item_code"] == item] if item else df


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("table", type=Path, help="ML-ready parquet 파일 또는 폴더")
    ap.add_argument("--expect-source", help="기대하는 data_source (예: ktms_synth)")
    ap.add_argument("--real", type=Path, help="실데이터 ML-ready 경로. 굴뚝 키가 겹치는지 본다(합성데이터용)")
    ap.add_argument("--item", help="한 항목만 검사 (nox 또는 sox)")
    args = ap.parse_args()
    df = _read(args.table, args.item)
    real = set(_read(args.real, None)["stack_code"].unique()) if args.real else None
    failures = check(df, args.expect_source, real)
    print(f"{args.table}: {len(df):,}행, {df['stack_code'].nunique():,}굴뚝")
    for line in failures:
        print("  실패:", line)
    print("통과" if not failures else f"실패 {len(failures)}건")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
