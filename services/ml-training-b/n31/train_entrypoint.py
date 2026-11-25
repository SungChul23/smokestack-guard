"""N3.1-C A형 보조 모델. 기존 V2 및 N3-C는 변경하지 않는다."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import joblib
from config import FEATURE_COLUMNS
from v2.dataset import prepare
from importlib.metadata import version
from v2.config import SCALES
from v2.evaluation import event_report
from evaluation import evaluate_classifier
from monitoring import _log_memory

HISTORY = ("ratio_pct", "ratio_lag_30m", "ratio_lag_60m", "ratio_lag_90m",
           "ratio_lag_120m", "ratio_lag_150m")


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
    model = XGBClassifier(random_state=42, scale_pos_weight=SCALES[model_id], n_jobs=4)
    _log_memory("n31/fit_before", include_cgroup=True)
    model.fit(datasets["train"]["X"], datasets["train"]["y"])
    _log_memory("n31/fit_after", include_cgroup=True)
    return model


def a_mask(X):
    """예측 시점의 현재 포함 6슬롯만 사용. 미래/Label로 라우팅하지 않는다."""
    values = X.loc[:, list(HISTORY)].to_numpy(dtype=float, na_value=np.nan)
    return np.isfinite(values).all(axis=1) & (values < 90).all(axis=1)


def predict_routed(auxiliary, baseline, X, auxiliary_threshold, baseline_threshold):
    """A만 보조 모델, B/C는 기존 모델의 점수 및 임계값 그대로 유지."""
    if tuple(X.columns) != FEATURE_COLUMNS:
        raise ValueError("22개 Feature 순서 불일치")
    for threshold in (auxiliary_threshold, baseline_threshold):
        if not np.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError("명시적으로 승인된 유효 임계값 필요")
    mask = a_mask(X)
    probability = np.empty(len(X), dtype=float)
    for model, selected in ((auxiliary, mask), (baseline, ~mask)):
        if selected.any():
            probability[selected] = model.predict_proba(X.loc[selected])[:, list(model.classes_).index(1)]
    if not np.isfinite(probability).all():
        raise ValueError("비유한 예측 확률")
    return {"probability": probability, "is_a": mask,
            "warning": probability >= np.where(mask, auxiliary_threshold, baseline_threshold)}


def validation_comparison(data, catalog, baseline_p, auxiliary_p, baseline_threshold):
    """Validation A형 FP 행 수를 부담 기준으로 비교. 후보 임계값은 채택하지 않는다.

    동일한 확률의 행을 쪼개지 않으므로 정확한 FP 일치는 불가능할 수 있다.
    FP 예산 이하에서 행 Recall이 최대인 비교 지점만 보고한다.
    사건 Recall은 전체 라우팅의 -60/-30 경보를 사용한다.
    """
    mask = a_mask(data["X"])
    y = np.asarray(data["y"], dtype=int)
    base_warning = baseline_p >= baseline_threshold
    budget = int((mask & (y == 0) & base_warning).sum())
    # A형 Label/양성 수는 후보 임계값 수와 무관하게 한 번만 계산한다.
    a_y = y[mask]
    positive_mask = a_y == 1
    positive_count = int(positive_mask.sum())
    values, inverse, count = np.unique(auxiliary_p[mask], return_inverse=True, return_counts=True)
    positives = np.bincount(inverse[positive_mask], minlength=len(values))
    tp = positives[::-1].cumsum()[::-1]
    fp = count[::-1].cumsum()[::-1] - tp
    curve = [{"threshold": float(t), "tp": int(a), "fp": int(b), "fn": int(positive_count - a),
              "recall": float(a / positive_count) if positive_count else None}
             for t, a, b in zip(values, tp, fp)]
    curve.append({"threshold": None, "tp": 0, "fp": 0, "fn": positive_count, "recall": 0.0 if positive_count else None})
    feasible = (v for v in curve if v["fp"] <= budget)
    point = max(feasible, key=lambda v: (v["tp"], -v["fp"],
                                        -(v["threshold"] if v["threshold"] is not None else 2)))
    routed = base_warning.copy()
    routed[mask] = False if point["threshold"] is None else auxiliary_p[mask] >= point["threshold"]
    baseline_events = event_report(catalog, data["rows"], base_warning.astype(float), .5)
    candidate_events = event_report(catalog, data["rows"], routed.astype(float), .5)
    return {"split": "tw_cems_validation", "burden_unit": "A-type false-positive rows",
            "baseline_threshold": baseline_threshold, "baseline_a_fp_budget": budget,
            "comparison_point_not_adopted": point, "exact_fp_match": point["fp"] == budget,
            "baseline_a_rows": evaluate_classifier(y[mask], baseline_p[mask], baseline_threshold),
            "candidate_a_ap_and_fixed_baseline_threshold": evaluate_classifier(y[mask], auxiliary_p[mask], baseline_threshold),
            "baseline_events": baseline_events, "routed_comparison_events": candidate_events,
            "threshold_curve": curve, "deployment_threshold": None,
            "note": "FP 행 수 기준이며 경보 묶음 수 일치가 아님. 채택 전 사용자 승인 필요"}


def run(input_path, output_dir, baseline_model, baseline_metadata, normalized_silver_confirmed=False):
    parent = Path(output_dir)
    if (parent / "N3.1-C").exists():
        raise FileExistsError("기존 결과 덮어쓰기 금지")
    meta = json.loads(Path(baseline_metadata).read_text(encoding="utf-8-sig"))
    if meta.get("model_id") != "N3-C" or tuple(meta["feature_columns"]) != FEATURE_COLUMNS:
        raise ValueError("N3-C metadata/Feature 불일치")
    # 직접 생성한 신뢰할 수 있는 joblib만 전달한다.
    from importlib.metadata import version
    if meta.get("xgboost_version") != version("xgboost"):
        raise ValueError("N3-C 학습 XGBoost 버전과 실행 환경 불일치")
    baseline = joblib.load(baseline_model)
    if baseline.get_booster().feature_names != list(FEATURE_COLUMNS):
        raise ValueError("N3-C 실제 Feature 순서 불일치")
    # 읽어온 기준 모델의 CPU 실행 설정만 변경하며 저장 모델은 수정하지 않는다.
    baseline.set_params(n_jobs=4)
    threshold = float(meta["validation_points"]["f2"])
    prepared = prepare(input_path, "N3-C", normalized_silver_confirmed=normalized_silver_confirmed)
    datasets, metadata = prepared["datasets"], prepared["metadata"]
    counts = {}
    for name, data in datasets.items():
        mask = a_mask(data["X"])
        counts[name] = {"all_rows": len(mask), "a_rows": int(mask.sum()),
                        "a_positive": int(data["y"].iloc[np.flatnonzero(mask)].sum())}
    train = datasets["train"]
    selected = a_mask(train["X"])
    datasets["train"] = {k: v.loc[selected].copy() for k, v in train.items()}
    del train, selected
    # 기존 fit 검증/기본 하이퍼파라미터/메모리 로그를 그대로 재사용한다.
    model = fit_candidate(datasets, "N3-C")
    del datasets["train"]
    _log_memory("n31/validation_before", include_cgroup=True)
    data = datasets.pop("validation")
    base_p = baseline.predict_proba(data["X"])[:, list(baseline.classes_).index(1)]
    auxiliary_p = np.full(len(data["y"]), np.nan)
    mask = a_mask(data["X"])
    if not mask.any():
        raise ValueError("Validation A형 행 없음")
    auxiliary_p[mask] = model.predict_proba(data["X"].loc[mask])[:, list(model.classes_).index(1)]
    metrics = {"train": counts["train"], "validation": validation_comparison(
        data, prepared["catalogs"]["validation"], base_p, auxiliary_p, threshold),
        "test": {"status": "reserved; threshold approval required; not predicted"}}
    del data, datasets, base_p, auxiliary_p
    metadata.update(model_id="N3.1-C", experiment_id="N3.1-C-a-type-auxiliary",
        training_selection="V2 eligible AND current+lag30..150 all finite and <90",
        scale_pos_weight=1, model_settings={k: (str(v) if isinstance(v, float) and not np.isfinite(v) else v)
                        for k, v in model.get_params(deep=False).items()},
        baseline_model_sha256=hashlib.file_digest(Path(baseline_model).open("rb"), "sha256").hexdigest(),
        baseline_threshold=threshold, routing="A auxiliary; B/C unchanged N3-C",
        deployment_threshold=None, split_counts=counts,
        artifact_scope="auxiliary only; N3-C required for B/C routing")
    # 기존 원자적 저장기를 별도 인스턴스로 재사용, 기존 허용 ID는 변경하지 않는다.
    spec = spec_from_file_location("_n31_artifacts", Path(__file__).resolve().parents[1] / "artifacts.py")
    artifacts = module_from_spec(spec); spec.loader.exec_module(artifacts)
    artifacts.MODEL_IDS = ("N3.1-C",)
    _log_memory("n31/save_before", include_cgroup=True)
    return artifacts.save_artifacts(model, "N3.1-C", metrics, metadata, parent)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model-id", choices=("N3.1-C",), required=True)
    p.add_argument("--input", default=os.environ.get("SM_CHANNEL_TRAIN"))
    p.add_argument("--output-dir", default=os.environ.get("SM_MODEL_DIR"))
    p.add_argument("--baseline-model", default=None)
    p.add_argument("--baseline-metadata", default=None)
    p.add_argument("--confirm-normalized-silver", choices=("true", "false"), default="false")
    a = p.parse_args(argv)
    if not a.input or not a.output_dir:
        p.error("입력/출력 경로가 필요합니다")
    if bool(a.baseline_model) != bool(a.baseline_metadata):
        p.error("--baseline-model과 --baseline-metadata는 함께 지정해야 합니다")
    baseline = Path(os.environ.get("SM_CHANNEL_BASELINE", "."))
    model = Path(a.baseline_model) if a.baseline_model else baseline / "model.joblib"
    metadata = Path(a.baseline_metadata) if a.baseline_metadata else baseline / "metadata.json"
    if model.is_file() and metadata.is_file():
        return run(a.input, a.output_dir, model, metadata, a.confirm_normalized_silver == "true")
    if a.baseline_model:
        p.error("명시한 기준 모델 또는 메타데이터 파일이 없습니다")
    archives = list(baseline.rglob("model.tar.gz"))
    if len(archives) != 1:
        p.error("baseline 채널에 model.tar.gz가 정확히 하나 필요합니다")
    import tarfile
    import tempfile
    import shutil
    from pathlib import PurePosixPath
    # extractall을 사용하지 않는다. 일반 파일 2개만 고정된 임시 경로로 복사한다.
    with tempfile.TemporaryDirectory(prefix="n31-baseline-") as temp:
        with tarfile.open(archives[0], "r:gz") as archive:
            selected = {}
            for member in archive.getmembers():
                parts = PurePosixPath(member.name)
                if parts.is_absolute() or ".." in parts.parts:
                    raise ValueError("안전하지 않은 기준 모델 압축 경로")
                if parts.name in ("model.joblib", "metadata.json"):
                    if not member.isfile() or parts.name in selected:
                        raise ValueError("기준 모델 압축에 중복/비정상 파일이 있습니다")
                    selected[parts.name] = member
            if set(selected) != {"model.joblib", "metadata.json"}:
                raise ValueError("압축에 model.joblib 및 metadata.json이 필요합니다")
            for name, member in selected.items():
                with archive.extractfile(member) as source, (Path(temp) / name).open("xb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
        return run(a.input, a.output_dir, Path(temp) / "model.joblib",
                   Path(temp) / "metadata.json", a.confirm_normalized_silver == "true")



if __name__ == "__main__":
    main()
