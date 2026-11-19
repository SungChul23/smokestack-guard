"""B 분류용 혼합 X/y와 출처별 sample_weight 구성. 학습·보간·샘플링 없음."""
import pandas as pd

if __package__:
    from .config import CLASSIFICATION_MODELS, FEATURE_COLUMNS, SOURCE_WEIGHTS, SOURCES
    from .dataset import load_source
    from .split import iter_split_batches
else:
    from config import CLASSIFICATION_MODELS, FEATURE_COLUMNS, SOURCE_WEIGHTS, SOURCES
    from dataset import load_source
    from split import iter_split_batches


def make_sample_weights(data_source, experiment):
    """출처와 같은 행 순서·인덱스로 가중치를 만든다. 양성 클래스 가중치는 곱하지 않는다.

    동일 X/y에 A/B/C를 비교할 때 이 함수로 Train 가중치만 다시 구성할 수 있다.
    """
    if experiment not in SOURCE_WEIGHTS:
        raise ValueError("출처 가중치 실험은 A, B, C 중 하나여야 합니다")
    if not isinstance(data_source, pd.Series):
        raise TypeError("data_source는 pandas.Series여야 합니다")
    if not data_source.isin(SOURCES).all():
        raise ValueError("sample_weight에 미확인·결측 출처가 있습니다")
    return data_source.map(SOURCE_WEIGHTS[experiment]).astype("float64").rename("sample_weight")


def summarize_train_weights(train, model_id, experiment):
    """실제 행별 가중치를 검증하고 출처 비중을 계산한다.

    sample_weight_share는 출처 가중치 합의 비중이다.
    combined_label_weight_share는 양성에 scale_pos_weight까지 곱한 명목 비중이며
    실제 모델 중요도나 예측 영향력을 뜻하지 않는다.
    """
    if model_id not in CLASSIFICATION_MODELS:
        raise ValueError("지원하는 분류 모델은 N2-C, S2-C입니다")
    source, y, weight = train["data_source"], train["y"], train["sample_weight"]
    if not (len(train["X"]) == len(source) == len(y) == len(weight)):
        raise ValueError("Train X/y/출처/가중치 길이가 다릅니다")
    if not all(value.index.equals(train["X"].index) for value in (source, y, weight)):
        raise ValueError("Train X/y/출처/가중치 인덱스가 다릅니다")
    if not y.isin((0, 1)).all():
        raise ValueError("분류 Label은 0 또는 1이어야 합니다")
    expected = make_sample_weights(source, experiment)
    if not weight.equals(expected):
        raise ValueError("실제 sample_weight가 승인된 출처 가중치와 다릅니다")
    scale = CLASSIFICATION_MODELS[model_id]["scale_pos_weight"]
    records = []
    for name, row_weight in SOURCE_WEIGHTS[experiment].items():
        mask = source.eq(name)
        n, positive = int(mask.sum()), int(y.loc[mask].eq(1).sum())
        records.append({
            "data_source": name, "rows": n, "positive": positive,
            "positive_ratio": positive / n if n else None,
            "row_weight": row_weight, "sample_weight_sum": n * row_weight,
            "negative_weight": row_weight, "positive_weight": row_weight * scale,
            "combined_label_weight_sum": row_weight * (n - positive + positive * scale),
        })
    total = len(source)
    weight_total = sum(r["sample_weight_sum"] for r in records)
    combined_total = sum(r["combined_label_weight_sum"] for r in records)
    for r in records:
        r.update(
            row_share=r["rows"] / total if total else None,
            sample_weight_share=r["sample_weight_sum"] / weight_total if weight_total else None,
            combined_label_weight_share=(r["combined_label_weight_sum"] / combined_total
                                         if combined_total else None),
        )
    return records


def prepare_mixed_datasets(model_id, experiment, source_batches=None):
    """세 출처의 검증·분할된 적격 행으로 분류 데이터를 구성한다.

    source_batches: 출처별 DataFrame 배치 iterator 사전. None일 때만 기존 로더 사용.
    반환: {"datasets": {train/validation/test: {X, y, data_source, ...}}, "metadata": ...}.
    sample_weight는 Train에만 제공한다. 출처/시각/Label은 X에 포함하지 않는다.
    원본 35열 전체를 합치지 않고, 배치마다 필요한 Feature·Label·출처·정렬키만 보관한다.
    최종 시각순 정렬키는 UTC 절대시각이며 출처별 벽시계 해석·분할은 split에 맡긴다.
    """
    if model_id not in CLASSIFICATION_MODELS:
        raise ValueError("지원하는 분류 모델은 N2-C, S2-C입니다")
    if experiment not in SOURCE_WEIGHTS:
        raise ValueError("출처 가중치 실험은 A, B, C 중 하나여야 합니다")
    if source_batches is None:
        source_batches = {source: load_source(source) for source in SOURCES}
    if set(source_batches) != set(SOURCES):
        raise ValueError("대만 실측·국내 실측·국내 합성의 세 출처가 모두 필요합니다")
    model = CLASSIFICATION_MODELS[model_id]
    parts = {name: [] for name in ("train", "validation", "test")}
    source_metadata = {}
    for source in SOURCES:
        audit = {"input_rows": 0, "outside_period_rows": 0, "embargo_rows": 0}
        if isinstance(source_batches[source], pd.DataFrame):
            raise TypeError("source_batches의 값은 DataFrame이 아닌 배치 iterator여야 합니다")
        for result in iter_split_batches(source_batches[source], source):
            meta = result["metadata"]
            for key in ("input_rows", "outside_period_rows", "embargo_rows"):
                audit[key] += meta[key]
            audit["boundaries"] = meta["boundaries"]
            audit["snapshot_id"] = meta["snapshot_id"]
            for name in parts:
                if name != "train" and source != "ktms":
                    if not result[name].empty:
                        raise ValueError("Validation/Test에는 국내 실측만 허용됩니다")
                    continue
                frame = result[name]
                mask = (frame["item_code"].eq(model["pollutant"])
                        & frame["classification_eligible"].eq(True).fillna(False)
                        & frame["feature_valid"].eq(True).fillna(False))
                # split에서 전체 배치를 검증했으므로 22열을 직접 투영한다.
                selected = frame.loc[mask, [*FEATURE_COLUMNS, "label_entry_60m",
                                            "data_source", "measured_at"]].copy()
                if selected.empty:
                    continue
                selected["measured_at"] = selected["measured_at"].dt.tz_convert("UTC")
                parts[name].append(selected)
            del result, frame, selected
        source_metadata[source] = audit

    datasets = {}
    for name in ("train", "validation", "test"):
        chunks = parts.pop(name)
        if not chunks:
            raise ValueError(f"{model_id}: {name}에 분류 적격 행이 없습니다")
        packed = pd.concat(chunks, ignore_index=True)
        del chunks
        packed.sort_values("measured_at", kind="stable", inplace=True, ignore_index=True)
        # X/y/출처를 같은 정렬 결과에서 위치 기반으로 추출해 중복 원본 인덱스와 분리한다.
        datasets[name] = {
            "X": packed.loc[:, list(FEATURE_COLUMNS)],
            "y": packed["label_entry_60m"].rename("label_entry_60m"),
            "data_source": packed["data_source"],
        }
        del packed
    train = datasets["train"]
    train["sample_weight"] = make_sample_weights(train["data_source"], experiment)
    summary = summarize_train_weights(train, model_id, experiment)
    if any(record["rows"] == 0 for record in summary):
        raise ValueError("Train에서 적격 행이 없는 출처가 있습니다")
    return {
        "datasets": datasets,
        "metadata": {
            "model_id": model_id, "experiment": experiment,
            "pollutant": model["pollutant"], "scale_pos_weight": model["scale_pos_weight"],
            "source_weights": dict(SOURCE_WEIGHTS[experiment]),
            "feature_columns": list(FEATURE_COLUMNS), "label_column": "label_entry_60m",
            "source_audit": source_metadata, "train_sources": summary,
            "split_rows": {name: len(data["y"]) for name, data in datasets.items()},
            "weight_policy": "Train sample_weight=source_weight; positive objective weight=source_weight*scale_pos_weight",
            "evaluation_weighted": False,
        },
    }
