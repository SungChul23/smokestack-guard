"""B 분류 모델 하나를 학습한다. import 시 데이터 조회·학습 없음."""
import json
from importlib.metadata import version
from math import isfinite

if __package__:
    from .config import CLASSIFICATION_MODELS, FEATURE_COLUMNS
    from .mixed_dataset import prepare_mixed_datasets, summarize_train_weights
    from .monitoring import _log_memory
else:
    from config import CLASSIFICATION_MODELS, FEATURE_COLUMNS
    from mixed_dataset import prepare_mixed_datasets, summarize_train_weights
    from monitoring import _log_memory


def _validate_datasets(datasets, model_id, experiment):
    """행 대응·출처·Feature 순서 및 Train/Validation 두 클래스를 확인한다."""
    for name in ("train", "validation", "test"):
        data = datasets[name]
        x, y, source = data["X"], data["y"], data["data_source"]
        if x.empty or tuple(x.columns) != FEATURE_COLUMNS:
            raise ValueError(f"{name}: 비어 있거나 Feature 22개 순서가 다릅니다")
        if not (len(x) == len(y) == len(source)
                and x.index.equals(y.index) and x.index.equals(source.index)):
            raise ValueError(f"{name}: X/y/출처 행 대응이 다릅니다")
        if not y.isin((0, 1)).all():
            raise ValueError(f"{name}: Label은 0/1이어야 합니다")
        if name in ("train", "validation") and y.nunique() != 2:
            raise ValueError(f"{name}: 양성·음성이 모두 필요합니다")
        if name != "train" and (
            not source.eq("ktms").all() or "sample_weight" in data
        ):
            raise ValueError(f"{name}: 국내 실측만 무가중 평가해야 합니다")
    summarize_train_weights(datasets["train"], model_id, experiment)


def train_classifier(model_id, experiment, source_batches=None):
    """전체 적격 Train에 sample_weight를 전달해 fit 1회. 평가 데이터는 fit에 미사용."""
    if model_id not in CLASSIFICATION_MODELS:
        raise ValueError("분류 모델은 N2-C 또는 S2-C여야 합니다")
    # A W10/W5와 같은 버전의 기본 하이퍼파라미터를 사용한다.
    if version("xgboost") != "3.4.1":
        raise RuntimeError("A W10/W5 재현을 위해 XGBoost 3.4.1이 필요합니다")
    from xgboost import XGBClassifier

    _log_memory(f"{model_id}/{experiment}/prepare_before", include_cgroup=True)
    prepared = prepare_mixed_datasets(model_id, experiment, source_batches)
    datasets, metadata = prepared["datasets"], dict(prepared["metadata"])
    del prepared
    _validate_datasets(datasets, model_id, experiment)
    _log_memory(f"{model_id}/{experiment}/data_ready", include_cgroup=True)
    scale = CLASSIFICATION_MODELS[model_id]["scale_pos_weight"]
    model = XGBClassifier(random_state=42, scale_pos_weight=float(scale))
    train = datasets["train"]
    _log_memory(f"{model_id}/{experiment}/fit_before", include_cgroup=True)
    model.fit(train["X"], train["y"], sample_weight=train["sample_weight"])
    _log_memory(f"{model_id}/{experiment}/fit_after", include_cgroup=True)
    # A와 동일하게 비유한 기본 missing 마커만 문자열로 기록한다.
    metadata["model_settings"] = {
        key: (str(value) if isinstance(value, float) and not isfinite(value) else value)
        for key, value in model.get_params(deep=False).items()
    }
    metadata["effective_booster_config"] = json.loads(model.get_booster().save_config())
    metadata.update(
        model_version="V2", model_class=type(model).__name__,
        experiment_id=f"{model_id}-weights-{experiment}",
        baseline_reference="N1-C-V1.2-W10" if model_id == "N2-C" else "S1-C-V1.1-W5",
        xgboost_version=version("xgboost"),
    )
    return {"model": model, "datasets": datasets, "metadata": metadata}
