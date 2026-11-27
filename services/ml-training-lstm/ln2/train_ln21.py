"""Issue #85 LN2.1 Feature Fusion의 로컬 Parquet / SageMaker File 채널 학습 진입점."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import shutil

import numpy as np

# SageMaker 소스 번들과 로컬 실행에서 동일한 C파트 모듈을 읽는다.
service = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(service), str(service.parents[1] / "src")]

from adapter import EMBARGO, LABEL, PERIODS, SLOT_COLUMNS, TIMEZONE, VERSIONS
from ln2_data import FEATURE_COLUMNS, STAT_COLUMNS, TIME_COLUMNS, FusionNormalizer, FusionStream
from ln2_model import build_model
from normalization import INPUT_SHAPE
from train_entrypoint import BATCH_SIZE, MAX_EPOCHS, PATIENCE, SEED, SHUFFLE_BUFFER

MODEL_DIRECTORY = "LN2.1"
MONITOR = "val_pr_auc"


def make_dataset(
    stream: FusionStream, split: str, normalizer: FusionNormalizer, row_count: int
):
    """읽기 청크에서 개별 행을 꺼내 학습용 512행 배치로 다시 묶는다."""
    import tensorflow as tf

    def batches():
        for X, y in stream.iter_split(split):
            yield normalizer.transform(X), y.astype(np.float32, copy=False).reshape(-1, 1)

    dataset = tf.data.Dataset.from_generator(
        batches,
        output_signature=(
            {
                "sequence": tf.TensorSpec((None, *INPUT_SHAPE), tf.float32),
                "features": tf.TensorSpec((None, len(FEATURE_COLUMNS)), tf.float32),
            },
            tf.TensorSpec((None, 1), tf.float32),
        ),
    ).unbatch()
    # Keras가 유한한 분할의 길이를 알고 매 epoch 새 순회를 시작하게 한다.
    dataset = dataset.apply(tf.data.experimental.assert_cardinality(row_count))
    if split == "train":
        dataset = dataset.shuffle(
            min(SHUFFLE_BUFFER, row_count), seed=SEED, reshuffle_each_iteration=True
        )
    return dataset.batch(BATCH_SIZE, drop_remainder=False).prefetch(1)


def save_run(model, normalizer: FusionNormalizer, metrics: dict, metadata: dict, parent: Path, best_checkpoint: Path) -> Path:
    """완성된 결과를 같은 부모 아래 공개한다. 기존 모델 결과는 덮어쓰지 않는다."""
    destination = parent / MODEL_DIRECTORY
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".LN2.1-", dir=parent) as temp:
        pending = Path(temp) / MODEL_DIRECTORY
        pending.mkdir()
        model.save(pending / "model.keras")
        shutil.copy2(best_checkpoint, pending / "best.weights.h5")
        normalizer.save(pending / "normalization.json")
        for name, value in (("metrics.json", metrics), ("metadata.json", metadata)):
            (pending / name).write_text(
                json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                encoding="utf-8",
            )
        pending.rename(destination)
    return destination


def run_training(input_path: str | Path, output_dir: str | Path) -> Path:
    """Train으로 학습하고 Validation의 최고 PR-AUC 시점으로 복원한 뒤 Test를 평가한다."""
    import tensorflow as tf

    parent = Path(output_dir)
    destination = parent / MODEL_DIRECTORY
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)

    stream = FusionStream(input_path)
    normalizer, counts = stream.scan()
    for name, split in counts.items():
        if split["rows"] == 0:
            raise ValueError(f"{name}: 학습 계약을 충족하는 행이 없습니다")
        if name != "test" and not 0 < split["positive"] < split["rows"]:
            raise ValueError(f"{name}: 양성과 음성이 모두 필요합니다")
    print(f"Eligible rows by split: {json.dumps(counts)}", flush=True)
    tf.keras.utils.set_random_seed(SEED)
    train, validation, test = (
        make_dataset(stream, name, normalizer, counts[name]["rows"])
        for name in ("train", "validation", "test")
    )
    model = build_model()
    parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".LN2.1-checkpoint-", dir=parent) as checkpoint_dir:
        best_checkpoint = Path(checkpoint_dir) / "best.weights.h5"
        checkpoint = tf.keras.callbacks.ModelCheckpoint(
            filepath=str(best_checkpoint), monitor=MONITOR, mode="max",
            save_best_only=True, save_weights_only=True,
        )
        stopping = tf.keras.callbacks.EarlyStopping(
            monitor=MONITOR, mode="max", min_delta=0.0, patience=PATIENCE, restore_best_weights=True
        )
        history = model.fit(
            train, validation_data=validation, epochs=MAX_EPOCHS, callbacks=[checkpoint, stopping]
        )
        curves = {name: [float(value) for value in values] for name, values in history.history.items()}
        validation_score = curves[MONITOR]
        if not validation_score or not np.isfinite(validation_score).all():
            raise ValueError("Validation PR-AUC가 비어 있거나 유한하지 않습니다")
        best_index = int(np.argmax(validation_score))
        if not best_checkpoint.is_file():
            raise RuntimeError("최고 Validation PR-AUC 체크포인트가 없습니다")
        model.load_weights(best_checkpoint)
        test_metrics = {name: float(value) for name, value in model.evaluate(test, return_dict=True).items()}
        if counts["test"]["positive"] in (0, counts["test"]["rows"]):
            test_metrics["pr_auc"] = None
        metrics = {
            "split_counts": counts,
            "epochs_run": len(validation_score),
            "best_epoch": best_index + 1,
            "best_pr_auc_epoch": best_index + 1,
            "selection_criterion": {"monitor": MONITOR, "mode": "max", "tie": "first epoch"},
            "restored_checkpoint": "best.weights.h5",
            "best_validation": {"loss": curves["val_loss"][best_index], "pr_auc": curves["val_pr_auc"][best_index]},
            "history": curves,
            "test": test_metrics,
        }
        metadata = {
            "issue": 85,
            "model": MODEL_DIRECTORY,
            "model_id": MODEL_DIRECTORY,
            "tensorflow_version": tf.__version__,
            "pollutant": "nox",
            "source": "tw_cems",
            "input_files": stream.manifest,
            "input_shape": {"sequence": INPUT_SHAPE, "features": (len(FEATURE_COLUMNS),)},
            "feature_columns": FEATURE_COLUMNS,
            "slot_columns": SLOT_COLUMNS,
            "label": LABEL,
            "contract_versions": VERSIONS,
            "eligibility": "LN1 eligibility; non-finite fusion features abort the run",
            "timezone": TIMEZONE,
            "periods_end_exclusive_before_embargo": PERIODS,
            "train_validation_end_embargo_minutes": int(EMBARGO.total_seconds() / 60),
            "normalization": {
                "sequence": "train-only mean and population standard deviation over all six slots",
                "per_feature_train_standardization": STAT_COLUMNS,
                "passthrough": TIME_COLUMNS,
            },
            "batch_size": BATCH_SIZE,
            "max_epochs": MAX_EPOCHS,
            "early_stopping": {
                "monitor": MONITOR, "mode": "max", "min_delta": 0.0,
                "patience": PATIENCE, "restore_best_weights": True,
            },
            "pr_auc_definition": "Keras threshold-grid PR AUC, not exact Average Precision",
            "train_shuffle_buffer": min(SHUFFLE_BUFFER, counts["train"]["rows"]),
            "seed": SEED,
            "class_weights": {"0": 1, "1": 1},
        }
        return save_run(model, normalizer, metrics, metadata, parent, best_checkpoint)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=os.environ.get("SM_CHANNEL_TRAIN"))
    parser.add_argument("--output-dir", default=os.environ.get("SM_MODEL_DIR"))
    args = parser.parse_args(argv)
    if not args.input or not args.output_dir:
        parser.error("--input/SM_CHANNEL_TRAIN 및 --output-dir/SM_MODEL_DIR가 필요합니다")
    if "://" in args.input or "://" in args.output_dir:
        parser.error("로컬 경로 또는 SageMaker의 로컬 채널 경로만 허용합니다")
    return run_training(args.input, args.output_dir)


if __name__ == "__main__":
    main()
