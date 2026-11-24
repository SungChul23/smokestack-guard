"""S3.1-C 혼합 학습→대만 Validation 선정→대만 Test 고정 평가→저장."""
import argparse
import json
import os
import sys
from pathlib import Path
from importlib.metadata import version
from math import isfinite
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import FEATURE_COLUMNS
from monitoring import _log_memory
from v2.evaluation import select_validation_points, evaluate_rows, event_report, warning_bundles
from s31.config import MODEL_ID, SCALE_POS_WEIGHT
from s31.dataset import prepare_mixed
from s31.artifacts import save_artifacts


def fit_classifier(datasets):
    """출처 sample_weight 없이 모든 Train 행에 fit 정확히 1회."""
    if version("xgboost") != "3.4.1":
        raise RuntimeError("기존 S3-C와 같은 XGBoost 3.4.1이 필요합니다")
    from xgboost import XGBClassifier
    for name, data in datasets.items():
        if data["X"].empty or tuple(data["X"].columns) != FEATURE_COLUMNS:
            raise ValueError(f"{name}: 빈 입력 또는 Feature 순서 불일치")
        if not data["X"].index.equals(data["y"].index) or not data["X"].index.equals(data["rows"].index):
            raise ValueError("X/y/식별자 행 대응 오류")
        if not data["y"].isin((0, 1)).all() or np.isinf(data["X"].to_numpy(dtype=float)).any():
            raise ValueError("Label 또는 Feature Inf 오류")
        if name in ("train", "validation") and data["y"].nunique() != 2:
            raise ValueError("Train/Validation에는 두 클래스가 필요합니다")
    model = XGBClassifier(random_state=42, scale_pos_weight=SCALE_POS_WEIGHT)
    _log_memory("S3.1-C/fit_before", include_cgroup=True)
    model.fit(datasets["train"]["X"], datasets["train"]["y"])
    _log_memory("S3.1-C/fit_after", include_cgroup=True)
    return model


def run(input_path, output_dir, *, normalized_silver_confirmed=False, batch_size=65536):
    target = Path(output_dir).resolve() / MODEL_ID
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"기존 S3.1-C 결과를 덮어쓸 수 없습니다: {target}")
    _log_memory("S3.1-C/prepare_before", include_cgroup=True)
    prepared = prepare_mixed(input_path, normalized_silver_confirmed=normalized_silver_confirmed,
                             batch_size=batch_size)
    datasets, catalogs, metadata = prepared["datasets"], prepared["catalogs"], prepared["metadata"]
    del prepared
    _log_memory("S3.1-C/data_ready", include_cgroup=True)
    model = fit_classifier(datasets)
    train = datasets.pop("train")
    metrics = {"train": {"rows": len(train["y"]),
                         "positive": int(train["y"].eq(1).sum()),
                         "by_source": metadata["training_sources"]}}
    del train
    column = list(model.classes_).index(1)
    for name in ("validation", "test"):
        data = datasets.pop(name)
        _log_memory(f"S3.1-C/{name}_before", include_cgroup=True)
        probability = model.predict_proba(data["X"])[:, column]
        if name == "validation":
            points = select_validation_points(data["y"], probability)
        metrics[name] = evaluate_rows(
            data, probability, points, metadata["taiwan_audit"][name]["population_rows"])
        metrics[name]["events"] = event_report(catalogs[name], data["rows"], probability, points["f2"])
        metrics[name]["warnings"] = warning_bundles(
            data["rows"], data["y"], probability, points["f2"])
        del data, probability
    metadata.update(
        experiment_id=MODEL_ID, scale_pos_weight=SCALE_POS_WEIGHT,
        xgboost_version=version("xgboost"), validation_points=points,
        model_settings={k: str(v) if isinstance(v, float) and not isfinite(v) else v
                        for k, v in model.get_params(deep=False).items()},
        effective_booster_config=json.loads(model.get_booster().save_config()),
    )
    _log_memory("S3.1-C/save_before", include_cgroup=True)
    return save_artifacts(model, metrics, metadata, output_dir)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model-id", choices=(MODEL_ID,), default=MODEL_ID)
    p.add_argument("--input", default=os.environ.get("SM_CHANNEL_TRAIN"))
    p.add_argument("--output-dir", default=os.environ.get("SM_MODEL_DIR"))
    p.add_argument("--batch-size", type=int, default=65536)
    p.add_argument("--confirm-normalized-silver", choices=("true", "false"), default="false")
    args = p.parse_args(argv)
    if not args.input or not args.output_dir:
        p.error("--input/SM_CHANNEL_TRAIN 및 --output-dir/SM_MODEL_DIR가 필요합니다")
    return run(args.input, args.output_dir,
               normalized_silver_confirmed=args.confirm_normalized_silver == "true",
               batch_size=args.batch_size)


if __name__ == "__main__":
    main()
