"""대만만 학습하는 부분 이력 후보. import 시 학습/조회 없음."""
import argparse
import json
import os
import sys
from pathlib import Path
from importlib.metadata import version
from math import isfinite
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import FEATURE_COLUMNS
from v2.artifacts import save_artifacts
from monitoring import _log_memory
from v2.dataset import prepare
from v2.evaluation import select_validation_points, evaluate_rows, event_report, warning_bundles

from v2.config import SCALES


def fit_candidate(datasets, model_id):
    """전체 적격 Train fit 1회. sample_weight·국내 데이터·추가 하이퍼파라미터 없음."""
    if model_id not in SCALES:
        raise ValueError("지원하지 않는 모델")
    if version("xgboost") != "3.4.1":
        raise RuntimeError("기존 환경과 같은 XGBoost 3.4.1이 필요합니다")
    from xgboost import XGBClassifier
    for name in ("train", "validation", "test"):
        data = datasets[name]
        if tuple(data["X"].columns) != FEATURE_COLUMNS or data["X"].empty:
            raise ValueError("Feature 순서 또는 비어 있는 데이터")
        if not data["X"].index.equals(data["y"].index) or not data["X"].index.equals(data["rows"].index):
            raise ValueError("X/y/식별자 행 대응 오류")
        if not data["y"].isin((0, 1)).all():
            raise ValueError("분류 Label 오류")
        if name in ("train", "validation") and data["y"].nunique() != 2:
            raise ValueError(f"{name}: 양성/음성이 모두 필요합니다")
    model = XGBClassifier(random_state=42, scale_pos_weight=SCALES[model_id])
    _log_memory("partial_history/fit_before", include_cgroup=True)
    model.fit(datasets["train"]["X"], datasets["train"]["y"])
    _log_memory("partial_history/fit_after", include_cgroup=True)
    return model


def run(model_id, input_path, output_dir, *, normalized_silver_confirmed=False, batch_size=65536):
    """새 전용 하위 경로에만 원자적으로 저장한다. 기존 후보도 재사용/덮어쓰기하지 않는다."""
    parent = Path(output_dir).resolve() / "partial-history-tw-v2"
    if (parent / model_id).exists() or (parent / model_id).is_symlink():
        raise FileExistsError("기존 후보 결과가 있습니다")
    _log_memory("partial_history/prepare_before", include_cgroup=True)
    prepared = prepare(input_path, model_id, normalized_silver_confirmed=normalized_silver_confirmed,
                       batch_size=batch_size)
    datasets, metadata, catalogs = prepared["datasets"], prepared["metadata"], prepared["catalogs"]
    del prepared
    _log_memory("partial_history/data_ready", include_cgroup=True)
    model = fit_candidate(datasets, model_id)
    train = datasets.pop("train")
    metrics = {"train": {"rows": len(train["y"]), "positive": int(train["y"].eq(1).sum())}}
    del train
    positive = list(model.classes_).index(1)
    for name in ("validation", "test"):
        data = datasets.pop(name)
        _log_memory(f"partial_history/{name}_before", include_cgroup=True)
        probability = model.predict_proba(data["X"])[:, positive]
        if name == "validation":
            points = select_validation_points(data["y"], probability)
        metrics[name] = evaluate_rows(data, probability, points,
                                      metadata["audit"][name]["population_rows"])
        metrics[name]["events"] = event_report(catalogs[name], data["rows"], probability, points["f2"])
        metrics[name]["warnings"] = warning_bundles(data["rows"], data["y"], probability, points["f2"])
        del data, probability
    metadata.update(
        experiment_id=f"{model_id}-partial-history-tw-v2",
        baseline_reference="N1-C-V1.0" if model_id == "N3-C" else "S1-C-V1.1-W5",
        xgboost_version=version("xgboost"), scale_pos_weight=SCALES[model_id],
        model_settings={k: str(v) if isinstance(v, float) and not isfinite(v) else v
                        for k, v in model.get_params(deep=False).items()},
        effective_booster_config=json.loads(model.get_booster().save_config()),
        validation_points=points,
        test_role="Taiwan historical holdout; not new domestic final evaluation",
    )
    _log_memory("partial_history/save_before", include_cgroup=True)
    return save_artifacts(model, model_id, metrics, metadata, parent)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model-id", required=True, choices=tuple(SCALES))
    p.add_argument("--input", default=os.environ.get("SM_CHANNEL_TRAIN"))
    p.add_argument("--output-dir", default=os.environ.get("SM_MODEL_DIR"))
    p.add_argument("--batch-size", type=int, default=65536)
    p.add_argument("--confirm-normalized-silver", choices=("true", "false"), default="false")
    args = p.parse_args(argv)
    if not args.input or not args.output_dir:
        p.error("--input/SM_CHANNEL_TRAIN 및 --output-dir/SM_MODEL_DIR가 필요합니다")
    return run(args.model_id, args.input, args.output_dir,
               normalized_silver_confirmed=args.confirm_normalized_silver == "true",
               batch_size=args.batch_size)


if __name__ == "__main__":
    main()
