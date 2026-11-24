"""대만+국내 실측+합성 v2의 동일 행 가중치 Train 구성. import 시 조회 없음."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import FunctionType
import numpy as np
import pandas as pd

from config import LOAD_COLUMNS, FEATURE_COLUMNS
from contract import validate_contract
from dataset import _prepare_batch
from v2.contract import eligibility
from v2.dataset import ObservationIndex, read_batches, prepare as prepare_taiwan
from s31.config import (
    MODEL_ID, POLLUTANT, DATABASE, WORKGROUP, SNAPSHOTS, DOMESTIC_START,
    DOMESTIC_END_EXCLUSIVE, DOMESTIC_USABLE_END_EXCLUSIVE, CONTEXT_START,
)


def domestic_sql(source):
    """고정 Snapshot과 승인된 Train+과거 품질검증 구간만 조회한다."""
    if source not in SNAPSHOTS:
        raise ValueError("국내 실측 또는 합성 v2 출처가 필요합니다")
    config = SNAPSHOTS[source]
    columns = ", ".join(f'"{c}"' for c in LOAD_COLUMNS)
    return (
        f'SELECT {columns} FROM "{DATABASE}"."{config["table"]}" '
        f'FOR VERSION AS OF {config["snapshot_id"]} '
        f"WHERE item_code = 'sox' "
        f"AND measured_at >= TIMESTAMP '{CONTEXT_START}' "
        f"AND measured_at < TIMESTAMP '{DOMESTIC_END_EXCLUSIVE}'"
    )


def domestic_batches(source, batch_size=65536):
    """실제 소비 시에만 Athena 실행. 직접 Iceberg/Parquet 읽기는 사용하지 않는다."""
    import awswrangler as wr
    for frame in wr.athena.read_sql_query(
        sql=domestic_sql(source), database=DATABASE, workgroup=WORKGROUP,
        ctas_approach=False, unload_approach=False, chunksize=batch_size, keep_files=True,
    ):
        query_id = getattr(frame, "query_metadata", {}).get("QueryExecutionId")
        normalized = _prepare_batch(frame, source, "train")
        normalized.attrs["athena_query_id"] = query_id
        # 공통 B 로더의 이전 Snapshot 메타데이터는 새로 지정한 값으로 명확히 교체한다.
        normalized.attrs["snapshot_id"] = SNAPSHOTS[source]["snapshot_id"]
        yield normalized


def domestic_clock(raw):
    """한국 벽시계 보존. 대만 전용 UTC 표기 제거 로직을 적용하지 않는다."""
    times = pd.to_datetime(raw, errors="raise")
    zone = str(times.dt.tz) if times.dt.tz is not None else None
    if zone not in (None, "Asia/Seoul"):
        raise ValueError("미확인 국내 시간대")
    times = times.dt.tz_localize("Asia/Seoul") if zone is None else times
    if times.isna().any() or (
        times.dt.minute.mod(30).ne(0) | times.dt.second.ne(0)
        | times.dt.microsecond.ne(0) | times.dt.nanosecond.ne(0)
    ).any():
        raise ValueError("국내 관측은 유효한 30분 슬롯이어야 합니다")
    return times


# V2의 동일한 compact 인덱스·품질식에 출처별 시간 해석/검증만 연결한다.
# 기존 모듈의 전역 변수·모델 설정은 변경하지 않는다.
_index_globals = dict(ObservationIndex.keys_for.__globals__)
_index_globals["normalize_times"] = domestic_clock


class DomesticIndex(ObservationIndex):
    keys_for = FunctionType(ObservationIndex.keys_for.__code__, _index_globals,
                            "keys_for", ObservationIndex.keys_for.__defaults__,
                            ObservationIndex.keys_for.__closure__)


def domestic_eligibility(frame, index, source, confirmed):
    globals_for_source = dict(eligibility.__globals__)
    globals_for_source["validate_contract"] = lambda data, _source: validate_contract(data, source)
    function = FunctionType(eligibility.__code__, globals_for_source,
                            "domestic_training_eligibility", eligibility.__defaults__,
                            eligibility.__closure__)
    function.__kwdefaults__ = eligibility.__kwdefaults__
    return function(frame, index, normalized_silver_confirmed=confirmed)


def prepare_domestic(source, batches, *, normalized_silver_confirmed, batch_size=65536):
    """Athena 1회 결과를 임시 디스크에 배치 보관하고 두 번 로컬 스캔한다.

    스냅샷을 두 번 조회하지 않으며 원본 35열 전체를 메모리에 concat하지 않는다.
    현재/과거/미래 검증은 같은 고정 스냅샷의 모든 조회 배치를 참조한다.
    """
    if source not in SNAPSHOTS:
        raise ValueError("국내 출처 오류")
    audit = {"source": source, **SNAPSHOTS[source], "queried_rows": 0,
             "context_rows": 0, "embargo_rows": 0,
             "complete_rows": 0, "partial_rows": 0,
             "train_rows": 0, "athena_query_id": None}
    with TemporaryDirectory(prefix="s31-domestic-") as temporary:
        cache = Path(temporary)
        files = []
        for number, raw in enumerate(batches):
            query_id = raw.attrs.get("athena_query_id")
            frame = _prepare_batch(raw, source, "train")
            frame.attrs["snapshot_id"] = SNAPSHOTS[source]["snapshot_id"]
            if not frame.item_code.eq(POLLUTANT).all():
                raise ValueError("국내 조회에 SOx 외 물질이 포함됐습니다")
            start = pd.Timestamp(CONTEXT_START, tz="Asia/Seoul")
            end = pd.Timestamp(DOMESTIC_END_EXCLUSIVE, tz="Asia/Seoul")
            if not (frame.measured_at.ge(start) & frame.measured_at.lt(end)).all():
                raise ValueError("국내 승인 조회 구간 밖 데이터입니다")
            if query_id and audit["athena_query_id"] not in (None, query_id):
                raise ValueError("서로 다른 Athena 결과가 섞였습니다")
            if query_id:
                audit["athena_query_id"] = query_id
            path = cache / f"{number:06d}.parquet"
            frame.to_parquet(path, index=False)
            files.append(path)
            audit["queried_rows"] += len(frame)
        if not files:
            raise ValueError(f"{source}: 국내 Train 조회 결과가 없습니다")
        index = DomesticIndex(read_batches(
            files, ("stack_code", "item_code", "measured_at",
                    "ratio_pct", "measure_value", "standard_value"), batch_size))
        parts = []
        for frame in read_batches(files, LOAD_COLUMNS, batch_size):
            mask = domestic_eligibility(frame, index, source, normalized_silver_confirmed)
            times = domestic_clock(frame.measured_at)
            period = times.ge(pd.Timestamp(DOMESTIC_START, tz="Asia/Seoul"))
            usable = period & times.lt(pd.Timestamp(DOMESTIC_USABLE_END_EXCLUSIVE, tz="Asia/Seoul"))
            audit["context_rows"] += int((~period).sum())
            audit["embargo_rows"] += int((period & ~usable).sum())
            audit["complete_rows"] += int((usable & mask.baseline).sum())
            audit["partial_rows"] += int((usable & mask.partial).sum())
            selected = usable & mask.eligible_v2
            if selected.any():
                part = frame.loc[selected, [
                    *FEATURE_COLUMNS, "label_entry_60m",
                    "stack_code", "item_code", "measured_at"]].copy()
                part["history_cohort"] = np.where(mask.partial.loc[selected], "partial", "complete")
                parts.append(part)
        del index
        if not parts:
            raise ValueError(f"{source}: SOx 적격 Train 행이 없습니다")
        packed = pd.concat(parts, ignore_index=True)
        del parts
        packed = packed.sort_values("measured_at", kind="stable", ignore_index=True)
        result = {
            "X": packed.loc[:, list(FEATURE_COLUMNS)],
            "y": packed.label_entry_60m,
            "rows": packed.loc[:, ["stack_code", "item_code", "measured_at", "history_cohort"]],
        }
        audit["train_rows"] = len(packed)
        audit["positive_ratio"] = int(packed.label_entry_60m.eq(1).sum()) / len(packed)
        return result, audit


def prepare_mixed(input_path, *, normalized_silver_confirmed=False, batch_size=65536,
                  supplied_domestic=None):
    """세 출처 적격 행을 보존·시간순 결합. 표본 축소·출처별 보정 없음."""
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
        raise ValueError("batch_size는 양의 정수")
    taiwan = prepare_taiwan(input_path, "S3-C",
                           normalized_silver_confirmed=normalized_silver_confirmed,
                           batch_size=batch_size)
    datasets, catalogs, twmeta = taiwan["datasets"], taiwan["catalogs"], taiwan["metadata"]
    del taiwan
    train_parts = [datasets.pop("train")]
    source_names = ["tw_cems"]
    audits = {}
    for source in SNAPSHOTS:
        batches = (supplied_domestic[source] if supplied_domestic is not None
                   else domestic_batches(source, batch_size))
        train, audit = prepare_domestic(
            source, batches, normalized_silver_confirmed=normalized_silver_confirmed,
            batch_size=batch_size)
        train_parts.append(train)
        source_names.append(source)
        audits[source] = audit
    times = np.concatenate([
        data["rows"].measured_at.dt.tz_convert("UTC").to_numpy(dtype="datetime64[ns]").astype("int64")
        for data in train_parts])
    order = np.argsort(times, kind="stable")
    x = pd.concat([data["X"] for data in train_parts], ignore_index=True)
    y = pd.concat([data["y"] for data in train_parts], ignore_index=True)
    row_parts = []
    summaries = []
    for source, data in zip(source_names, train_parts):
        frame = data["rows"].copy()
        frame["measured_at"] = frame.measured_at.dt.tz_convert("UTC")
        frame["data_source"] = source
        row_parts.append(frame)
        count, positive = len(data["y"]), int(data["y"].eq(1).sum())
        summaries.append({"data_source": source, "train_rows": count,
                          "positive_ratio": positive/count})
    del train_parts
    rows = pd.concat(row_parts, ignore_index=True)
    del row_parts
    datasets["train"] = {
        "X": x.iloc[order].reset_index(drop=True),
        "y": y.iloc[order].reset_index(drop=True),
        "rows": rows.iloc[order].reset_index(drop=True),
    }
    metadata = {
        "model_id": MODEL_ID, "candidate": "mixed-partial-history-s31",
        "baseline_reference": "S3-C", "training_sources": summaries,
        "domestic_snapshot_audit": audits,
        "domestic_train_start": DOMESTIC_START,
        "domestic_train_end_exclusive": DOMESTIC_END_EXCLUSIVE,
        "domestic_usable_end_exclusive": DOMESTIC_USABLE_END_EXCLUSIVE,
        "embargo_minutes": 60, "feature_columns": twmeta["feature_columns"],
        "taiwan_periods_end_exclusive": twmeta["periods_end_exclusive"],
        "taiwan_input_manifest": twmeta["input_manifest"],
        "taiwan_audit": twmeta["audit"],
        "quality_policy_reference": twmeta["quality_policy_reference"],
        "validation_source": "tw_cems", "test_source": "tw_cems",
        "domestic_exploratory_period": "2026-11-11..21 not accessed",
        "domestic_final_period": "2026-11-22 onward not accessed",
        "synthetic_generation_reference_period": "not verified by this implementation",
        "fit_uses_sample_weight": False,
    }
    return {"datasets": datasets, "catalogs": catalogs, "metadata": metadata}
