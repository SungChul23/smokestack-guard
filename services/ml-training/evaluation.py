"""분류·회귀 평가 함수. import 시 학습·예측·평가를 실행하지 않는다.

입력은 같은 행 순서의 1차원 정답·예측이다. 인덱스로 자동 결합하지 않는다.
모델 간 평가 행 동일성은 호출자가 확인해야 하며 공정 비교를 선언하지 않는다.
"""

from fractions import Fraction
from math import sqrt

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    fbeta_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    recall_score,
)


def _validate_pair(y_true, y_prediction, classification=False):
    """빈 입력·길이·차원·유한값 및 분류의 정답/확률 범위를 확인한다."""
    arrays = []
    for name, values in (("y_true", y_true), ("y_prediction", y_prediction)):
        try:
            raw = np.asarray(values)
            if np.iscomplexobj(raw):
                raise ValueError("복소수 입력")
            array = np.asarray(values, dtype=float)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{name}: 유한한 실수 배열이 필요합니다") from exc
        if array.ndim != 1 or array.size == 0:
            raise ValueError(f"{name}: 비어 있지 않은 1차원 입력이 필요합니다")
        if not np.isfinite(array).all():
            raise ValueError(f"{name}: NaN 또는 무한대가 있습니다")
        arrays.append(array)
    truth, prediction = arrays
    if len(truth) != len(prediction):
        raise ValueError("정답과 예측의 입력 길이가 다릅니다")
    if classification:
        if not np.isin(truth, (0, 1)).all():
            raise ValueError("분류 정답은 0 또는 1이어야 합니다")
        if ((prediction < 0) | (prediction > 1)).any():
            raise ValueError("양성 클래스 확률은 0~1이어야 합니다")
    return truth, prediction


def select_f2_threshold(y_true, y_probability) -> dict:
    """Validation 전용: F2 최대 → Recall 최대 → 낮은 임계값 순으로 선택.

    y_probability는 Validation의 양성 클래스 확률이다. 반환 threshold를
    보존하여 Test의 evaluate_classifier에 그대로 전달한다. Test로 호출 금지.
    배열만으로 분할 출처를 확인할 수 없으므로 이 계약은 호출자가 지켜야 한다.
    """
    truth, probability = _validate_pair(y_true, y_probability, classification=True)
    if np.unique(truth).size != 2:
        raise ValueError("Validation 정답에 0과 1이 모두 있어야 임계값을 선정할 수 있습니다")

    # 고유 확률별 건수를 한 번 집계하여 모든 실제 예측 구성을 비교한다.
    thresholds, inverse, counts = np.unique(
        probability, return_inverse=True, return_counts=True
    )
    positives = np.bincount(inverse[truth == 1], minlength=len(thresholds))
    tp_counts = positives[::-1].cumsum()[::-1]
    predicted_counts = counts[::-1].cumsum()[::-1]
    total_positive = int(positives.sum())

    # F2 = 5TP/(5TP+4FN+FP). 유리수 비교로 반올림·허용오차에 의한
    # 가짜 동점을 막는다. 동일 정답에서 Recall 비교는 TP 비교와 같다.
    def rank(index):
        tp = int(tp_counts[index])
        fp = int(predicted_counts[index]) - tp
        fn = total_positive - tp
        return Fraction(5 * tp, 5 * tp + 4 * fn + fp), tp, -float(thresholds[index])

    # 두 클래스가 있으므로 모두 음성인 후보의 F2=0은 최적이 될 수 없다.
    best = max(range(len(thresholds)), key=rank)
    result = evaluate_classifier(truth, probability, float(thresholds[best]))
    result["selection_split"] = "validation"
    return result


def evaluate_classifier(y_true, y_probability, threshold) -> dict:
    """고정 임계값으로 평가한다. 양성은 probability >= threshold이다.

    Test에서는 Validation에서 선택한 threshold를 그대로 사용한다.
    정의되지 않는 지표는 None, 그 이유는 undefined_metrics에 반환한다.
    """
    truth, probability = _validate_pair(y_true, y_probability, classification=True)
    try:
        if np.ndim(threshold) != 0 or np.iscomplexobj(threshold):
            raise ValueError("임계값은 실수 하나여야 합니다")
        threshold = float(threshold)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("threshold는 0~1의 유한한 실수여야 합니다") from exc
    if not np.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("threshold는 0~1의 유한한 실수여야 합니다")

    predicted = (probability >= threshold).astype(int)
    tn, fp, fn, tp = (
        int(value) for value in confusion_matrix(truth, predicted, labels=[0, 1]).ravel()
    )
    reasons = {}
    result = {"threshold": threshold, "tp": tp, "fp": fp, "fn": fn, "tn": tn}

    # 분모가 0인 지표는 임의 점수로 대체하지 않는다.
    metrics = (
        ("precision", tp + fp, lambda: precision_score(truth, predicted)),
        ("recall", tp + fn, lambda: recall_score(truth, predicted)),
        ("f1", 2 * tp + fp + fn, lambda: f1_score(truth, predicted)),
        ("f2", 5 * tp + fp + 4 * fn, lambda: fbeta_score(truth, predicted, beta=2)),
    )
    for name, denominator, calculate in metrics:
        result[name] = float(calculate()) if denominator else None
        if not denominator:
            reasons[name] = "정의에 필요한 분모가 0입니다"
    if tp + fp == 0:
        reasons["precision"] = "예측 양성이 0건입니다"
    if tp + fn == 0:
        reasons["recall"] = "실제 양성이 0건입니다"

    # AP는 PR-AUC의 요약 지표이며 사다리꼴 적분값과 구분한다.
    result["average_precision"] = None
    if np.unique(truth).size == 2:
        result["average_precision"] = float(average_precision_score(truth, probability))
    else:
        reasons["average_precision"] = "정답이 단일 클래스여서 AP를 해석할 수 없습니다"
    result["undefined_metrics"] = reasons
    return result


def evaluate_regressor(y_true, y_pred) -> dict:
    """동일 행 순서의 기준대비율을 MAE·RMSE(%p)로 평가한다.

    100% 초과 정답·예측값을 허용한다. 모델 간 동일 평가 행 여부는
    이 함수의 인자로 증명할 수 없으며 호출자가 별도로 확인해야 한다.
    """
    truth, prediction = _validate_pair(y_true, y_pred)
    mae = float(mean_absolute_error(truth, prediction))
    rmse = sqrt(float(mean_squared_error(truth, prediction)))
    if not np.isfinite((mae, rmse)).all():
        raise ValueError("회귀 오차 계산 결과가 유한하지 않습니다: 입력 수치 범위를 확인하세요")
    return {"mae": mae, "rmse": rmse, "unit": "%p"}
