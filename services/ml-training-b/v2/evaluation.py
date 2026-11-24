"""Validation 선정과 고정 임계값 평가를 분리한 V2 평가."""
import numpy as np
import pandas as pd
from evaluation import _validate_pair, select_f2_threshold, evaluate_classifier


def _point(y, p, threshold):
    pred = np.zeros(len(y), bool) if threshold is None else p >= threshold
    positive = y == 1
    tp, fp = int((pred & positive).sum()), int((pred & ~positive).sum())
    fn, tn = int((~pred & positive).sum()), int((~pred & ~positive).sum())
    return {"threshold": threshold, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "recall": tp / (tp + fn) if tp + fn else None,
            "precision": tp / (tp + fp) if tp + fp else None,
            "fpr": fp / (fp + tn) if fp + tn else None}


def select_validation_points(y_true, probability):
    """대만 Validation만 전달한다. 두 보조 지점도 여기서 선정 후 Test에 고정한다."""
    y, p = _validate_pair(y_true, probability, classification=True)
    main = select_f2_threshold(y, p)
    values, inverse, counts = np.unique(p, return_inverse=True, return_counts=True)
    positive = np.bincount(inverse[y == 1], minlength=len(values))
    tp = positive[::-1].cumsum()[::-1]
    predicted = counts[::-1].cumsum()[::-1]
    fp = predicted - tp
    recall = tp / int((y == 1).sum())
    fpr = fp / int((y == 0).sum())
    precision = tp / predicted
    low_fp = np.flatnonzero(fpr <= .01)
    high_recall = np.flatnonzero(recall >= .5)
    i = max(low_fp, key=lambda i: (recall[i], precision[i], -values[i])) if len(low_fp) else None
    j = max(high_recall, key=lambda i: (precision[i], recall[i], -values[i])) if len(high_recall) else None
    return {"f2": main["threshold"],
            "recall_at_fpr_1pct": float(values[i]) if i is not None else None,
            "precision_at_recall_50pct": float(values[j]) if j is not None else None,
            "selection_split": "tw_cems_validation"}


def evaluate_rows(data, probability, points, population_rows):
    """부분/완전/전체 AP와 고정 지점 실측 FPR·Recall을 반환한다. Test 재선정 없음."""
    y, p = _validate_pair(data["y"], probability, classification=True)
    cohort = data["rows"].history_cohort.to_numpy()
    result = {"prediction_coverage": len(y) / population_rows if population_rows else None,
              "predicted_rows": len(y), "population_rows": population_rows,
              "operating_point_contract": "Validation-selected thresholds, achieved Test FPR/Recall may differ"}
    for group in ("all", "complete", "partial"):
        mask = np.ones(len(y), bool) if group == "all" else cohort == group
        if not mask.any():
            result[group] = {"rows": 0, "metrics": None, "reason": "해당 이력 집단 없음"}
            continue
        yy, pp = y[mask], p[mask]
        result[group] = {"rows": len(yy), "positive": int((yy == 1).sum()),
                         **evaluate_classifier(yy, pp, points["f2"]),
                         "validation_fixed_points": {
                             name: _point(yy, pp, points[name])
                             for name in ("recall_at_fpr_1pct", "precision_at_recall_50pct")}}
    return result


def event_report(catalog, rows, probability, threshold):
    """두 후보 시점(-60/-30)이 모두 연결된 사건을 기본 분모로 센다.

    사건은 한 번만 센다. 60분 경고율은 같은 평가 사건 중 -60분 경고 비율이다.
    개별 양성 관측은 학습에서 제거하지 않는다.
    """
    frame = rows.copy()
    frame["probability"] = np.asarray(probability)
    keys = ["stack_code", "item_code", "measured_at"]
    if frame.duplicated(keys).any():
        raise ValueError("중복 예측 키")
    score = frame.set_index(keys).probability
    at60 = pd.MultiIndex.from_arrays([
        catalog.stack_code, catalog.item_code,
        catalog.measured_at - pd.Timedelta(minutes=60)], names=keys)
    history = frame.set_index(keys).history_cohort.reindex(at60).to_numpy()
    result = {}
    for name, mask in (
        ("complete_at_minus60", history == "complete"),
        ("partial_at_minus60", history == "partial"),
        ("all", np.ones(len(catalog), bool)),
        ("A", catalog.reentry_group.eq("A").to_numpy()),
        ("B", catalog.reentry_group.eq("B").to_numpy()),
        ("C", catalog.reentry_group.eq("C").to_numpy()),
        ("below50", catalog.ratio60.lt(50).to_numpy()),
        ("50to70", (catalog.ratio60.ge(50) & catalog.ratio60.lt(70)).to_numpy()),
        ("70to80", (catalog.ratio60.ge(70) & catalog.ratio60.lt(80)).to_numpy()),
        ("80to90", (catalog.ratio60.ge(80) & catalog.ratio60.lt(90)).to_numpy()),
    ):
        subset = catalog.loc[mask]
        scores = []
        for minutes in (60, 30):
            index = pd.MultiIndex.from_arrays([
                subset.stack_code, subset.item_code,
                subset.measured_at - pd.Timedelta(minutes=minutes)], names=keys)
            scores.append(score.reindex(index).to_numpy())
        a, b = scores
        coverage = np.isfinite(a) & np.isfinite(b)
        warned60, warned30 = a >= threshold, b >= threshold
        n = int(coverage.sum())
        detected = int((coverage & (warned60 | warned30)).sum())
        result[name] = {
            "observed_events": len(subset), "both_evaluable_events": n,
            "missing_or_ineligible_events": len(subset) - n,
            "detected_events": detected, "missed_events": n - detected,
            "event_recall": detected / n if n else None,
            "warning_60min_events": int((coverage & warned60).sum()),
            "warning_60min_ratio": int((coverage & warned60).sum()) / n if n else None,
            "first_warning_30min_events": int((coverage & ~warned60 & warned30).sum()),
        }
    return result


def warning_bundles(rows, y, probability, threshold):
    """기존 승인 기준: 동일 굴뚝·물질에서 정확히 30분 연속 경고를 묶는다.

    묶음 전체 Label=0만 거짓 경보 묶음. 혼합 묶음은 따로 센다.
    자정을 넘는 묶음은 시작일에 한 번 집계한다. 시설별 실제 위험 사건 수가 아니다.
    """
    frame = rows.loc[:, ["stack_code", "item_code", "measured_at"]].copy()
    frame["y"] = np.asarray(y)
    frame["warning"] = np.asarray(probability) >= threshold
    dates = frame.measured_at.dt.date.unique()
    warning = frame.loc[frame.warning].sort_values(
        ["stack_code", "item_code", "measured_at"], kind="stable")
    changed = (warning.stack_code.ne(warning.stack_code.shift())
               | warning.item_code.ne(warning.item_code.shift())
               | warning.measured_at.diff().ne(pd.Timedelta(minutes=30)))
    bundles = warning.groupby(changed.cumsum(), sort=False).agg(
        start=("measured_at", "min"), low=("y", "min"), high=("y", "max"))
    false = bundles.loc[bundles.high.eq(0)]
    by_day = false.groupby(false.start.dt.date).size().to_dict()
    return {"false_bundles": len(false),
            "mixed_bundles": int((bundles.low.eq(0) & bundles.high.eq(1)).sum()),
            "all_positive_bundles": int(bundles.low.eq(1).sum()),
            "false_bundles_by_day": {str(day): int(by_day.get(day, 0)) for day in sorted(dates)},
            "mean_per_observed_day": len(false) / len(dates) if len(dates) else None,
            "interpretation": "evaluation labels only; not a real-time eligibility rule"}
