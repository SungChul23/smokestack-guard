"""시나리오 B 승인 기간 분할. 가중치·학습·Feature/Label 재계산 없음."""
import pandas as pd

if __package__:
    from .config import DOMESTIC_TEST_END_EXCLUSIVE, check_source
    from .dataset import _prepare_batch
else:
    from config import DOMESTIC_TEST_END_EXCLUSIVE, check_source
    from dataset import _prepare_batch


# 끝 시각은 미포함. Train/Validation의 끝 직전 60분은 별도로 제외한다.
PERIODS = {
    "tw_cems": {
        "train": ("2023-11-01", "2025-11-01"),
    },
    "ktms": {
        "train": ("2026-10-30", "2026-11-11"),
        "validation": ("2026-11-11", "2026-11-14"),
        "test": ("2026-11-14", DOMESTIC_TEST_END_EXCLUSIVE),
    },
    "ktms_synth": {
        "train": ("2026-10-30", "2026-11-11"),
    },
}
EMBARGO = pd.Timedelta(minutes=60)


def summarize_splits(splits):
    """분할별 전체·출처별·물질별 건수를 집계한다. 양성 비율의 분모는 분류 적격 행이다.

    splits는 train/validation/test를 키로 하는 DataFrame 사전이다.
    빈 분류 적격 집합의 양성 비율은 None으로 반환한다.
    """
    def counts(frame):
        classification = frame["classification_eligible"].eq(True).fillna(False)
        regression = frame["regression_eligible"].eq(True).fillna(False)
        n = int(classification.sum())
        positive = int((classification & frame["label_entry_60m"].eq(1).fillna(False)).sum())
        return {
            "rows": len(frame),
            "classification_eligible": n,
            "regression_eligible": int(regression.sum()),
            "positive": positive,
            "negative": n - positive,
            "positive_ratio": positive / n if n else None,
        }

    summary = {}
    for name, frame in splits.items():
        summary[name] = {
            **counts(frame),
            "by_source_pollutant": [
                {"data_source": source, "item_code": pollutant, **counts(group)}
                for (source, pollutant), group in frame.groupby(
                    ["data_source", "item_code"], sort=True, observed=True
                )
            ],
        }
    return summary


def split_by_time(data, source):
    """검증된 출처 정책으로 단일 출처 DataFrame/배치를 분할한다.

    반환: {"train": DataFrame, "validation": DataFrame, "test": DataFrame,
           "metadata": dict}.
    원본을 변경하지 않고 출처별 현지 시각과 동일 시각의 입력 순서를 유지한다.
    적격성 필터는 적용하지 않으며 기존 플래그를 보존·집계한다.
    기간 밖 행과 embargo 행은 metadata에 각각 집계한다.
    """
    config = check_source(source)
    # 기존 로더와 동일한 시간 해석·계약 검증을 재사용한다.
    frame = _prepare_batch(data, source, "inspection")
    times = frame["measured_at"]
    inside = pd.Series(False, index=frame.index)
    embargo = pd.Series(False, index=frame.index)
    splits = {}
    boundaries = {}
    for name in ("train", "validation", "test"):
        if name not in PERIODS[source]:
            splits[name] = frame.iloc[:0].copy()
            continue
        start_text, end_text = PERIODS[source][name]
        start = pd.Timestamp(start_text, tz=config.timezone)
        end = pd.Timestamp(end_text, tz=config.timezone)
        usable_end = end - EMBARGO if name in ("train", "validation") else end
        in_period = times.ge(start) & times.lt(end)
        inside |= in_period
        embargo |= in_period & times.ge(usable_end)
        selected = frame.loc[in_period & times.lt(usable_end)]
        splits[name] = selected.sort_values("measured_at", kind="stable")
        boundaries[name] = {
            "start_inclusive": start.isoformat(),
            "end_exclusive": end.isoformat(),
            "usable_end_exclusive": usable_end.isoformat(),
        }

    for name, selected in splits.items():
        selected.attrs.update(split_applied=True, purpose=name)
    return {
        **splits,
        "metadata": {
            "source": source,
            "timezone": config.timezone,
            "snapshot_id": config.snapshot_id,
            "boundaries": boundaries,
            "embargo_minutes": 60,
            "input_rows": len(frame),
            "outside_period_rows": int((~inside).sum()),
            "embargo_rows": int(embargo.sum()),
            "summary": summarize_splits(splits),
        },
    }


def iter_split_batches(batches, source):
    """출처별 로더 iterator를 배치 단위로 분할한다. 전체 입력을 concat하지 않는다.

    각 반환값은 split_by_time과 같다. 배치 간 전체 정렬·혼합은 수행하지 않는다.
    후속 구성 단계는 세 출처의 Train만 합치고 국내 실측 Validation/Test만 사용한다.
    """
    check_source(source)
    for batch in batches:
        yield split_by_time(batch, source)
