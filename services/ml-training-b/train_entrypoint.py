"""B 단일 모델·출처 가중치 실험의 학습→국내 평가→원자적 저장."""
import argparse
import os
from pathlib import Path

if __package__:
    from .config import BATCH_SIZE, CEMS_INPUT_URI, CLASSIFICATION_MODELS, SOURCE_WEIGHTS
    from .dataset import load_source, _batch_size
    from .train_classifier import train_classifier
    from .evaluation import select_f2_threshold, evaluate_classifier
    from .artifacts import save_artifacts
    from .monitoring import _log_memory
else:
    from config import BATCH_SIZE, CEMS_INPUT_URI, CLASSIFICATION_MODELS, SOURCE_WEIGHTS
    from dataset import load_source, _batch_size
    from train_classifier import train_classifier
    from evaluation import select_f2_threshold, evaluate_classifier
    from artifacts import save_artifacts
    from monitoring import _log_memory


def run_training(model_id, experiment, output_dir, *, source_batches=None):
    """실험별 weights-A/B/C/<model_id>/에 저장한다. 기존 경로는 학습 전에 거부한다."""
    if model_id not in CLASSIFICATION_MODELS or experiment not in SOURCE_WEIGHTS:
        raise ValueError("지원하지 않는 모델 또는 출처 가중치 실험입니다")
    parent = Path(output_dir).resolve() / f"weights-{experiment}"
    target = parent / model_id
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"기존 결과를 덮어쓸 수 없습니다: {target}")
    if parent.exists() and not parent.is_dir():
        raise ValueError(f"출력 경로가 디렉터리가 아닙니다: {parent}")
    result = train_classifier(model_id, experiment, source_batches)
    model, datasets, metadata = result["model"], result["datasets"], result["metadata"]
    del result
    classes = list(model.classes_)
    if classes.count(1) != 1:
        raise ValueError("모델의 양성 클래스 1을 확인할 수 없습니다")
    positive_column = classes.index(1)
    train = datasets.pop("train")
    train_rows = len(train["y"])
    train_positive = int(train["y"].eq(1).sum())
    metrics = {"train": {"rows": train_rows, "positive": train_positive,
                         "negative": train_rows - train_positive,
                         "positive_ratio": train_positive / train_rows}}
    del train
    _log_memory(f"{model_id}/{experiment}/train_released", include_cgroup=True)
    for name in ("validation", "test"):
        data = datasets[name]
        _log_memory(f"{model_id}/{experiment}/{name}_before", include_cgroup=True)
        probability = model.predict_proba(data["X"])[:, positive_column]
        if name == "validation":
            metrics[name] = select_f2_threshold(data["y"], probability)
            threshold = metrics[name]["threshold"]
            metadata["classification_threshold"] = threshold
        else:
            metrics[name] = evaluate_classifier(data["y"], probability, threshold)
        n, positives = len(data["y"]), int(data["y"].eq(1).sum())
        metrics[name].update(rows=n, positive=positives, negative=n-positives,
                             positive_ratio=positives/n, data_source="ktms",
                             evaluation_weighted=False)
        del probability
        _log_memory(f"{model_id}/{experiment}/{name}_after", include_cgroup=True)
    metadata["threshold_selection_split"] = "domestic_real_validation"
    del data, datasets
    _log_memory(f"{model_id}/{experiment}/save_before", include_cgroup=True)
    paths = save_artifacts(model, model_id, metrics, metadata, parent)
    _log_memory(f"{model_id}/{experiment}/save_after", include_cgroup=True)
    return paths


def main(argv=None):
    """명시적 CLI 실행에서만 로딩·학습한다. SageMaker Job 제출 기능은 없다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", required=True, choices=tuple(CLASSIFICATION_MODELS))
    parser.add_argument("--weight-experiment", required=True, choices=tuple(SOURCE_WEIGHTS))
    parser.add_argument("--output-dir", default=os.environ.get("SM_MODEL_DIR"))
    parser.add_argument("--cems-input", default=os.environ.get("SM_CHANNEL_TRAIN", CEMS_INPUT_URI))
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args(argv)
    if not args.output_dir:
        parser.error("--output-dir 또는 SM_MODEL_DIR가 필요합니다")
    _batch_size(args.batch_size)
    # iterator 생성은 조회하지 않는다. 국내 고정 Snapshot은 기존 로더 계약을 유지한다.
    sources = {
        "tw_cems": load_source("tw_cems", path=args.cems_input, batch_size=args.batch_size),
        "ktms": load_source("ktms", batch_size=args.batch_size),
        "ktms_synth": load_source("ktms_synth", batch_size=args.batch_size),
    }
    return run_training(args.model_id, args.weight_experiment, args.output_dir,
                        source_batches=sources)


if __name__ == "__main__":
    main()
