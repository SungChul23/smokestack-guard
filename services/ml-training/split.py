"""대만 현지 측정 시각 기준의 공통 시간 분할과 Label 경계 제외."""

from math import isclose, isfinite

import pandas as pd


def split_by_time(
    data: pd.DataFrame,
    ratios: tuple[float, float, float] = (0.70, 0.15, 0.15),
) -> tuple[dict[str, pd.DataFrame], dict]:
    """Train/Validation/Test 복사본과 경계·실제 관측 범위 정보를 반환한다.

    measured_at의 시간대 없는 값은 대만 현지 시각으로 해석하고,
    시간대가 있는 값은 Asia/Taipei로 변환하여 계산한다.
    반환 데이터의 컬럼 값·인덱스는 보존하며 시각순으로만 정렬한다.
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
    if (
        len(ratios) != 3
        or any(not isfinite(value) or value <= 0 for value in ratios)
        or not isclose(sum(ratios), 1.0, rel_tol=0, abs_tol=1e-9)
    ):
        raise ValueError("분할 비율은 양수 3개이고 합계가 1이어야 합니다")

    # 숫자의 나노초 자동 해석을 막고, 시간 문자열 또는 datetime만 받는다.
    raw_times = data["measured_at"]
    if pd.api.types.is_numeric_dtype(raw_times.dtype) or raw_times.dropna().map(
        pd.api.types.is_number
    ).any():
        raise ValueError("measured_at은 숫자 대신 측정 시각이어야 합니다")
    try:
        times = pd.to_datetime(raw_times, errors="raise")
        if times.isna().any():
            raise ValueError("결측 시각")
        if times.dt.tz is None:
            times = times.dt.tz_localize("Asia/Taipei")
        else:
            times = times.dt.tz_convert("Asia/Taipei")
    except (ValueError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError(
            "measured_at에 결측·잘못된 형식 또는 혼합 시간대가 있습니다"
        ) from exc

    # 전체 최소~최대 관측 시각의 시간 길이로 모든 굴뚝·물질의 경계를 계산한다.
    start, end = times.min(), times.max()
    duration = end - start
    validation_start = (start + duration * ratios[0]).ceil("30min")
    test_start = (start + duration * (ratios[0] + ratios[1])).ceil("30min")
    label_horizon = pd.Timedelta(minutes=60)
    train_end_exclusive = validation_start - label_horizon
    validation_end_exclusive = test_start - label_horizon

    # 경계 60분 전 시각도 제외하여 미래 Label이 다음 구간 경계에 닿지 않게 한다.
    order = times.argsort(kind="stable")
    sorted_times = times.iloc[order]
    sorted_data = data.iloc[order]
    masks = {
        "train": sorted_times < train_end_exclusive,
        "validation": (
            (sorted_times >= validation_start)
            & (sorted_times < validation_end_exclusive)
        ),
        "test": sorted_times >= test_start,
    }
    splits = {
        name: sorted_data.iloc[mask.to_numpy()].copy()
        for name, mask in masks.items()
    }

    # 정책 경계와 실제 남은 관측 범위를 구분한다. 빈 분할의 범위는 None이다.
    metadata = {
        "timezone": "Asia/Taipei",
        "ratios": tuple(ratios),
        "observed_start": start,
        "observed_end": end,
        "validation_start": validation_start,
        "test_start": test_start,
        "train_end_exclusive": train_end_exclusive,
        "validation_end_exclusive": validation_end_exclusive,
        "label_horizon_minutes": 60,
        "excluded_rows": len(data) - sum(len(frame) for frame in splits.values()),
        "splits": {},
    }
    for name, mask in masks.items():
        selected_times = sorted_times.iloc[mask.to_numpy()]
        metadata["splits"][name] = {
            "start": None if selected_times.empty else selected_times.min(),
            "end": None if selected_times.empty else selected_times.max(),
            "rows": len(selected_times),
        }
    return splits, metadata
