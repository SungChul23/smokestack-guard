"""모델 하나의 학습·평가·저장을 명시적 main 실행으로 연결한다."""

import argparse
import os
from importlib import import_module
from pathlib import Path


TRAINERS = {
    "N1-C": ("train_n1", "train_n1_classifier"),
    "N1-R": ("train_n1", "train_n1_regressor"),
    "S1-C": ("train_s1", "train_s1_classifier"),
    "S1-R": ("train_s1", "train_s1_regressor"),
    "RN1": ("train_rf", "train_rn1_regressor"),
    "RS1": ("train_rf", "train_rs1_regressor"),
}


def main(argv=None) -> dict:
    """CLI 호출 시에만 Parquet 로딩·단일 모델 학습·평가·저장을 수행한다.

    --model-id는 필수다. --input-path/--output-dir를 생략하면 각각
    SM_CHANNEL_TRAIN/SM_MODEL_DIR를 사용한다. 입력은 두 물질을 포함한
    전체 ML-ready 파일 또는 Parquet 디렉터리이며 먼저 필터링하지 않는다.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", required=True, choices=tuple(TRAINERS))
    parser.add_argument("--input-path", default=os.environ.get("SM_CHANNEL_TRAIN"))
    parser.add_argument("--output-dir", default=os.environ.get("SM_MODEL_DIR"))
    args = parser.parse_args(argv)
    if not args.input_path or not args.output_dir:
        parser.error("입력·출력 경로 인자 또는 SM_CHANNEL_TRAIN·SM_MODEL_DIR가 필요합니다")

    input_path = Path(args.input_path).resolve()
    output_dir = Path(args.output_dir).resolve()
    target = output_dir / args.model_id
    if not input_path.exists():
        raise FileNotFoundError(f"Parquet 입력 경로가 없습니다: {input_path}")
    if not (input_path.is_file() or input_path.is_dir()):
        raise ValueError(f"Parquet 파일 또는 디렉터리가 아닙니다: {input_path}")
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"기존 모델 결과 경로를 덮어쓸 수 없습니다: {target}")
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError(f"출력 경로가 디렉터리가 아닙니다: {output_dir}")
    if input_path.is_relative_to(target) or (
        input_path.is_dir() and target.is_relative_to(input_path)
    ):
        raise ValueError("입력 데이터 경로와 모델 결과 경로를 분리해야 합니다")

    # 의존성 로딩과 모든 작업은 명시적인 main 호출 이후에만 수행한다.
    from artifacts import save_artifacts
    from evaluation import (
        evaluate_classifier,
        evaluate_regressor,
        select_f2_threshold,
    )

    module_name, function_name = TRAINERS[args.model_id]
    train = getattr(import_module(module_name), function_name)
    # 경로만 전달한다. 공통 데이터 준비가 두 번 스캔한 뒤 전체 적격 X/y를
    # 반환하므로 fit 중 원본 35개 컬럼 DataFrame을 보관하지 않는다.
    result = train(input_path)
    model = result["model"]
    datasets = result["datasets"]
    metadata = dict(result["metadata"])
    for name in ("validation", "test"):
        if datasets[name]["X"].empty:
            raise ValueError(f"{args.model_id}: {name} 적격 평가 데이터가 없습니다")

    # 분류 임계값은 Validation에서만 선택하고 Test에는 동일 값을 적용한다.
    metrics = {}
    if args.model_id.endswith("-C"):
        classes = list(model.classes_)
        if 1 not in classes:
            raise ValueError("분류 모델에 양성 클래스 1이 없습니다")
        positive_column = classes.index(1)
        validation = datasets["validation"]
        probability = model.predict_proba(validation["X"])[:, positive_column]
        metrics["validation"] = select_f2_threshold(validation["y"], probability)
        threshold = metrics["validation"]["threshold"]
        del probability
        test = datasets["test"]
        probability = model.predict_proba(test["X"])[:, positive_column]
        metrics["test"] = evaluate_classifier(test["y"], probability, threshold)
        metadata["classification_threshold"] = threshold
        del probability
    else:
        for name in ("validation", "test"):
            dataset = datasets[name]
            prediction = model.predict(dataset["X"])
            metrics[name] = evaluate_regressor(dataset["y"], prediction)
            del prediction

    # 기존 메타데이터의 분할 시각·전체/적격 건수를 유지하고 확인된 정보만 추가한다.
    metadata["model_id"] = args.model_id
    metadata["model_class"] = type(model).__name__
    metadata["model_settings"] = {
        "random_state": model.get_params()["random_state"],
        "remaining_parameters": "library_defaults",
    }
    metadata["feature_columns"] = list(datasets["train"]["X"].columns)
    metadata["input_path"] = str(input_path)
    # 전체 get_params에는 NaN 기본값 등이 있을 수 있어 JSON에 그대로 넘기지 않는다.
    # 모델 객체 자체의 전체 설정은 model.joblib에 보존된다.
    return save_artifacts(model, args.model_id, metrics, metadata, output_dir)


if __name__ == "__main__":
    main()
