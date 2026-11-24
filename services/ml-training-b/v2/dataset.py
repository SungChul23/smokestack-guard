"""대만 24/6/6 분할의 2단계 Parquet 준비. Feature 재계산·보간·샘플링 없음."""
from pathlib import Path
import hashlib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from config import FEATURE_COLUMNS, LOAD_COLUMNS
from dataset import _prepare_batch
from v2.contract import eligibility, C_POLICY_REFERENCE

SLOT_NS = 30 * 60 * 10**9
STRIDE = 2**24
BOUNDS = {
    "train": ("2023-11-01", "2025-10-31 23:00"),
    "validation": ("2025-11-01", "2026-04-30 23:00"),
    "test": ("2026-05-01", "2026-11-01"),
}


def normalize_times(raw):
    """대만 CEMS UTC 표기는 현지 벽시계로 해석한다."""
    t = pd.to_datetime(raw, errors="raise")
    zone = str(t.dt.tz) if t.dt.tz is not None else None
    if zone not in (None, "UTC", "Etc/UTC", "Asia/Taipei"):
        raise ValueError("확인되지 않은 대만 시간대")
    t = t.dt.tz_localize(None).dt.tz_localize("Asia/Taipei")
    if t.isna().any() or ((t.dt.minute % 30 != 0) | (t.dt.second != 0)
                        | (t.dt.microsecond != 0) | (t.dt.nanosecond != 0)).any():
        raise ValueError("측정 시각은 유효한 30분 슬롯이어야 합니다")
    return t


class ObservationIndex:
    """전체 입력의 compact 관측 인덱스. 모델 입력에는 포함하지 않는다."""
    def __init__(self, batches):
        self.groups = {}
        chunks = []
        for frame in batches:
            k = self.keys_for(frame, register=True)
            chunks.append((k, *(frame[c].to_numpy(dtype=float, na_value=np.nan)
                               for c in ("ratio_pct", "measure_value", "standard_value"))))
        if not chunks:
            raise ValueError("빈 입력")
        keys = np.concatenate([p[0] for p in chunks])
        order = np.argsort(keys, kind="stable")
        self.keys = keys[order]
        self.values = [np.concatenate([p[j] for p in chunks])[order] for j in (1, 2, 3)]
        if np.any(self.keys[1:] == self.keys[:-1]):
            raise ValueError("중복 굴뚝·물질·시각이 있습니다")
        self.rows = len(self.keys)

    def keys_for(self, data, register=False):
        t = normalize_times(data.measured_at)
        naive = t.dt.tz_localize(None).to_numpy(dtype="datetime64[ns]").astype("int64")
        slot = naive // SLOT_NS
        if ((slot < 0) | (slot >= STRIDE)).any():
            raise ValueError("지원하지 않는 시간 범위")
        codes, unique = pd.factorize(pd.MultiIndex.from_frame(data[["stack_code", "item_code"]]), sort=False)
        mapping = []
        for pair in unique:
            if pair not in self.groups:
                if not register:
                    raise ValueError("두 스캔의 관측 키가 다릅니다")
                self.groups[pair] = len(self.groups)
            mapping.append(self.groups[pair])
        return np.asarray(mapping, dtype=np.int64)[codes] * STRIDE + slot

    def lookup(self, target):
        i = np.searchsorted(self.keys, target)
        safe = np.minimum(i, len(self.keys) - 1)
        found = (i < len(self.keys)) & (self.keys[safe] == target)
        values = [np.where(found, v[safe], np.nan) for v in self.values]
        return (*values, found)



def event_catalog(index, pollutant):
    """compact 인덱스로 실제 진입을 한 번 집계. 미래는 평가 사건 확인에만 사용한다."""
    keys, ratio = index.keys, index.values[0]
    previous = np.r_[np.nan, ratio[:-1]]
    adjacent = np.r_[False, np.diff(keys) == 1]
    groups = [None] * len(index.groups)
    for pair, code in index.groups.items():
        groups[code] = pair
    group_items = np.asarray([pair[1] for pair in groups])
    event = (np.isfinite(ratio) & np.isfinite(previous) & adjacent
             & (previous < 90) & (ratio >= 90)
             & (group_items[keys // STRIDE] == pollutant))
    ek = keys[event]
    history = np.column_stack([index.lookup(ek - j)[0] for j in range(2, 8)])
    complete = np.isfinite(history).all(axis=1)
    maximum = np.full(len(ek), np.nan)
    maximum[complete] = history[complete].max(axis=1)
    category = np.full(len(ek), "C", dtype="<U1")
    category[complete & (maximum < 90)] = "A"
    category[complete & (maximum >= 90)] = "B"
    clock = pd.to_datetime((ek % STRIDE) * SLOT_NS).tz_localize("Asia/Taipei")
    for bound in ("2025-11-01", "2026-05-01"):
        at = pd.Timestamp(bound, tz="Asia/Taipei")
        category[(clock >= at) & (clock < at + pd.Timedelta(minutes=60))] = "C"
    return pd.DataFrame({
        "stack_code": [groups[int(k // STRIDE)][0] for k in ek],
        "item_code": pollutant, "measured_at": clock,
        "ratio60": index.lookup(ek - 2)[0], "reentry_group": category,
    })


def local_files(path):
    path = Path(path)
    files = [path] if path.is_file() else sorted(path.rglob("*.parquet")) if path.is_dir() else []
    if not files or any(p.suffix.lower() != ".parquet" for p in files):
        raise ValueError("로컬 Parquet 파일 또는 디렉터리가 필요합니다")
    return tuple(p.resolve() for p in files)


def fingerprint(files):
    """메모리 복제 없이 파일 목록·크기·시각·SHA256을 비교한다. Linux lease 불필요."""
    result = []
    for p in files:
        before = p.stat()
        h = hashlib.sha256()
        with p.open("rb") as stream:
            for block in iter(lambda: stream.read(8 * 1024**2), b""):
                h.update(block)
        after = p.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError("해시 계산 중 입력 변경")
        result.append((str(p), after.st_size, after.st_mtime_ns, h.hexdigest()))
    return tuple(result)


def read_batches(files, columns, batch_size):
    for p in files:
        parquet = pq.ParquetFile(p)
        if not set(columns).issubset(parquet.schema_arrow.names):
            raise ValueError(f"{p.name}: 입력 컬럼 누락")
        for batch in parquet.iter_batches(columns=list(columns), batch_size=batch_size, use_threads=False):
            yield batch.to_pandas()


def prepare(path, model_id, *, normalized_silver_confirmed=False, batch_size=65536):
    """첫 스캔 compact 이력 인덱스 → 두 번째 스캔 검증·V2 마스크·22열 선택."""
    if model_id not in ("N3-C", "S3-C"):
        raise ValueError("N3-C 또는 S3-C가 필요합니다")
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
        raise ValueError("batch_size는 양의 정수")
    files = local_files(path)
    initial = fingerprint(files)
    index = ObservationIndex(read_batches(files, ("stack_code", "item_code", "measured_at",
                                                  "ratio_pct", "measure_value", "standard_value"), batch_size))
    def unchanged():
        if local_files(path) != files or fingerprint(files) != initial:
            raise RuntimeError("2단계 스캔 사이 입력 파일 내용/목록 변경")
    unchanged()
    parts = {name: [] for name in BOUNDS}
    audit = {name: {"baseline": 0, "partial": 0, "baseline_positive": 0,
                    "partial_positive": 0, "population_rows": 0} for name in BOUNDS}
    pollutant = "nox" if model_id == "N3-C" else "sox"
    for raw in read_batches(files, LOAD_COLUMNS, batch_size):
        frame = _prepare_batch(raw, "tw_cems", "inspection")
        if (frame.measured_at.lt(pd.Timestamp("2023-11-01", tz="Asia/Taipei"))
                | frame.measured_at.ge(pd.Timestamp("2026-11-01", tz="Asia/Taipei"))).any():
            raise ValueError("대만 36개월 확정 기간 밖 입력")
        masks = eligibility(frame, index, normalized_silver_confirmed=normalized_silver_confirmed)
        for name, (start, end) in BOUNDS.items():
            period = (frame.measured_at.ge(pd.Timestamp(start, tz="Asia/Taipei"))
                      & frame.measured_at.lt(pd.Timestamp(end, tz="Asia/Taipei"))
                      & frame.item_code.eq(pollutant))
            audit[name]["population_rows"] += int(period.sum())
            for cohort in ("baseline", "partial"):
                accepted = period & masks[cohort]
                audit[name][cohort] += int(accepted.sum())
                audit[name][cohort + "_positive"] += int((accepted & frame.label_entry_60m.eq(1)).sum())
            selected = period & masks.eligible_v2
            if selected.any():
                packed = frame.loc[selected, [*FEATURE_COLUMNS, "label_entry_60m",
                                              "stack_code", "item_code", "measured_at"]].copy()
                packed["history_cohort"] = np.where(masks.partial.loc[selected], "partial", "complete")
                parts[name].append(packed)
        del raw, frame, masks
    unchanged()
    catalog = event_catalog(index, pollutant)
    catalogs = {}
    for name, (start, end) in BOUNDS.items():
        physical_end = pd.Timestamp(end, tz="Asia/Taipei")
        if name != "test":
            physical_end += pd.Timedelta(minutes=60)
        catalogs[name] = catalog.loc[
            catalog.measured_at.ge(pd.Timestamp(start, tz="Asia/Taipei"))
            & catalog.measured_at.lt(physical_end)].copy()
    del index, catalog
    datasets = {}
    for name in BOUNDS:
        chunks = parts.pop(name)
        if not chunks:
            raise ValueError(f"{name}: V2 적격 행 없음")
        packed = pd.concat(chunks, ignore_index=True)
        del chunks
        packed.sort_values("measured_at", kind="stable", inplace=True, ignore_index=True)
        datasets[name] = {"X": packed.loc[:, list(FEATURE_COLUMNS)],
                          "y": packed.label_entry_60m,
                          "rows": packed.loc[:, ["stack_code", "item_code", "measured_at", "history_cohort"]]}
    if not audit["train"]["partial"]:
        raise ValueError("Train에 증명 가능한 부분 이력 행이 없습니다. 정규화 출처·품질 확인 필요")
    return {"datasets": datasets, "catalogs": catalogs, "metadata": {
        "candidate": "partial-history-tw-v2", "model_id": model_id,
        "training_source": "tw_cems", "source_weights": None,
        "feature_columns": list(FEATURE_COLUMNS), "audit": audit,
        "periods_end_exclusive": BOUNDS, "embargo_minutes": 60,
        "normalized_silver_confirmed": normalized_silver_confirmed,
        "quality_policy_reference": C_POLICY_REFERENCE,
        "input_manifest": initial, "integrity_limit":
        "checksums before/between/after scans; transient mutate-and-restore not excluded",
        "domestic_final_evaluation": "reserved from 2026-11-22; not accessed",
        "domestic_reused_period": "2026-11-11..21 exploratory only",
    }}
