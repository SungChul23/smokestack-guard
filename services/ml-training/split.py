"""대만 현지 측정 시각 기준의 공통 시간 분할과 Label 경계 제외."""

import pandas as pd


def _normalize_times(
    raw_times: pd.Series, *, tw_cems_wall_clock: bool = False,
) -> pd.Series:
    """TW CEMS에만 UTC 표기를 제거해 대만 벽시계 시각을 보존한다."""
    if not pd.api.types.is_datetime64_any_dtype(raw_times.dtype) and (
        pd.api.types.is_numeric_dtype(raw_times.dtype) or raw_times.dropna().map(
            pd.api.types.is_number
        ).any()
    ):
        raise ValueError("measured_at은 숫자 대신 측정 시각이어야 합니다")
    try:
        times = pd.to_datetime(raw_times, errors="raise")
        if times.isna().any():
            raise ValueError("결측 시각")
        if tw_cems_wall_clock and times.dt.tz is not None:
            # C파트 ts_local은 현지 벽시계이며 Glue의 UTC 표기는 절대시각이 아니다.
            times = times.dt.tz_localize(None)
        return (
            times.dt.tz_localize("Asia/Taipei") if times.dt.tz is None
            else times.dt.tz_convert("Asia/Taipei")
        )
    except (ValueError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError("measured_at에 결측·잘못된 형식 또는 혼합 시간대가 있습니다") from exc


def _time_metadata(start, end) -> dict:
    """사용자 확정 24/6/6 기간을 모든 물질·모델에 동일하게 적용한다."""
    train_start = pd.Timestamp("2023-11-01", tz="Asia/Taipei")
    validation_start = pd.Timestamp("2025-11-01", tz="Asia/Taipei")
    test_start = pd.Timestamp("2026-05-01", tz="Asia/Taipei")
    test_end_exclusive = pd.Timestamp("2026-11-01", tz="Asia/Taipei")
    # 범위 밖 행을 버리거나 관측 기간에 맞춰 경계를 재계산하지 않는다.
    if (
        pd.isna(start) or pd.isna(end) or start > end
        or start < train_start or end >= test_end_exclusive
    ):
        raise ValueError(
            "전체 입력의 관측 시각이 확정 기간 "
            f"[2023-11-01, 2026-11-01) 밖이거나 유효하지 않습니다: {start} ~ {end}. "
            "범위 밖 행을 자동 삭제하지 않습니다"
        )
    horizon = pd.Timedelta(minutes=60)
    return {
        "timezone": "Asia/Taipei", "period_policy": "24/6/6_months",
        "train_start": train_start, "test_end_exclusive": test_end_exclusive,
        "observed_start": start, "observed_end": end,
        "validation_start": validation_start, "test_start": test_start,
        "train_end_exclusive": validation_start - horizon,
        "validation_end_exclusive": test_start - horizon,
        "label_horizon_minutes": 60,
    }


def _split_masks(times: pd.Series, metadata: dict) -> dict:
    return {
        "train": (
            (times >= metadata["train_start"])
            & (times < metadata["train_end_exclusive"])
        ),
        "validation": (
            (times >= metadata["validation_start"])
            & (times < metadata["validation_end_exclusive"])
        ),
        "test": (
            (times >= metadata["test_start"])
            & (times < metadata["test_end_exclusive"])
        ),
    }


def split_by_time(
    data: pd.DataFrame,
    ratios=None,
    *,
    tw_cems_wall_clock: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict]:
    """Train/Validation/Test 복사본과 경계·실제 관측 범위 정보를 반환한다.

    measured_at의 시간대 없는 값은 대만 현지 시각으로 해석하고,
    시간대가 있는 값은 Asia/Taipei로 변환하여 계산한다.
    대만 CEMS ML-ready에는 tw_cems_wall_clock=True로 UTC 표기를 제거하고
    벽시계 날짜·시간을 대만 현지 시각으로 해석한다. 일반 UTC 입력은 변환한다.
    반환 데이터의 컬럼 값·인덱스는 보존하며 시각순으로만 정렬한다.
    24/6/6 확정 기간을 사용하며 과거 ratios 인자는 더 이상 허용하지 않는다.
    """
    # 입력 오류는 보간·삭제 없이 명시적으로 알린다.
    if not isinstance(data, pd.DataFrame):
        raise TypeError("입력은 pandas.DataFrame이어야 합니다")
    if "measured_at" not in data.columns:
        raise ValueError("필수 시간 컬럼 누락: measured_at")
    if list(data.columns).count("measured_at") != 1:
        raise ValueError("시간 컬럼명 중복: measured_at")
    if data.empty:
        raise ValueError("빈 데이터는 시간순으로 분할할 수 없습니다")
    if ratios is not None:
        raise ValueError("비율 분할 대신 사용자 확정 24/6/6 기간만 사용할 수 있습니다")

    times = _normalize_times(data["measured_at"], tw_cems_wall_clock=tw_cems_wall_clock)
    metadata = _time_metadata(times.min(), times.max())

    # 경계 60분 전 시각도 제외하여 미래 Label이 다음 구간 경계에 닿지 않게 한다.
    order = times.argsort(kind="stable")
    sorted_times = times.iloc[order]
    sorted_data = data.iloc[order]
    masks = _split_masks(sorted_times, metadata)
    splits = {
        name: sorted_data.iloc[mask.to_numpy()].copy()
        for name, mask in masks.items()
    }

    # 정책 경계와 실제 남은 관측 범위를 구분한다. 빈 분할의 범위는 None이다.
    metadata["excluded_rows"] = len(data) - sum(len(frame) for frame in splits.values())
    metadata["splits"] = {}
    for name, mask in masks.items():
        selected_times = sorted_times.iloc[mask.to_numpy()]
        metadata["splits"][name] = {
            "start": None if selected_times.empty else selected_times.min(),
            "end": None if selected_times.empty else selected_times.max(),
            "rows": len(selected_times),
        }
    return splits, metadata
