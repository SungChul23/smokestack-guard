"""B 출처별 배치 로더. 날짜 분할·출처 혼합·모델 학습은 구현하지 않는다."""
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd

if __package__:
    from .config import (ATHENA_DATABASE, ATHENA_WORKGROUP, BATCH_SIZE, CEMS_INPUT_URI,
                         LOAD_COLUMNS, REGION, check_source)
    from .contract import validate_contract
else:
    from config import (ATHENA_DATABASE, ATHENA_WORKGROUP, BATCH_SIZE, CEMS_INPUT_URI,
                        LOAD_COLUMNS, REGION, check_source)
    from contract import validate_contract


def _batch_size(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("batch_size는 양의 정수여야 합니다")
    return value


def _prepare_batch(frame, source, purpose):
    """출처별로 확인된 벽시계를 해석한다. Feature·Label 값은 변경하지 않는다."""
    config = check_source(source, purpose)
    validate_contract(frame, source)
    result = frame.copy()
    try:
        times = pd.to_datetime(frame["measured_at"], errors="raise")
        zone = str(times.dt.tz) if times.dt.tz is not None else None
        if source == "tw_cems":
            # CEMS의 UTC 표기는 절대시각이 아니라 대만 현지 벽시계다.
            if zone not in (None, "UTC", "Etc/UTC", "Asia/Taipei"):
                raise ValueError(f"확인되지 않은 대만 시간대: {zone}")
            times = times.dt.tz_localize(None).dt.tz_localize(config.timezone)
        else:
            # 국내 naive 시각은 KST다. 미확인 UTC 입력을 임의 보정하지 않는다.
            if zone not in (None, "Asia/Seoul"):
                raise ValueError(f"확인되지 않은 국내 시간대: {zone}")
            times = times.dt.tz_localize(config.timezone) if zone is None else times
        if not times.dt.minute.isin((0, 30)).all() or (
            times.dt.second.ne(0) | times.dt.microsecond.ne(0) | times.dt.nanosecond.ne(0)
        ).any():
            raise ValueError("measured_at은 30분 격자여야 합니다")
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"{source}: 시간 해석 실패: {exc}") from exc
    result["measured_at"] = times
    result.attrs.update(
        source=source, snapshot_id=config.snapshot_id, timezone=config.timezone,
        purpose=purpose, split_applied=False,
    )
    return result


def iter_cems_batches(path=CEMS_INPUT_URI, *, boto3_session=None,
                      batch_size=BATCH_SIZE, purpose="inspection"):
    """대만 일반 ML-ready Parquet만 읽는다. Iceberg 국내 입력에 사용하지 않는다."""
    check_source("tw_cems", purpose)
    _batch_size(batch_size)
    import pyarrow.dataset as ds
    import pyarrow.fs as fs

    path = str(path)
    parsed = urlsplit(path)
    filesystem = None
    if parsed.scheme == "s3":
        import boto3
        session = boto3_session or boto3.Session(region_name=REGION)
        credentials = session.get_credentials()
        if credentials is None:
            raise ValueError("대만 S3 읽기 인증정보가 없습니다")
        credentials = credentials.get_frozen_credentials()
        filesystem = fs.S3FileSystem(
            region=REGION, access_key=credentials.access_key,
            secret_key=credentials.secret_key, session_token=credentials.token,
        )
        path = parsed.netloc + "/" + parsed.path.lstrip("/")
    elif parsed.scheme and not Path(path).is_absolute():
        raise ValueError("대만 입력은 로컬 경로 또는 s3:// 경로여야 합니다")
    elif not Path(path).exists():
        raise FileNotFoundError(path)
    dataset = ds.dataset(path, format="parquet", filesystem=filesystem)
    for fragment in dataset.get_fragments():
        missing = set(LOAD_COLUMNS) - set(fragment.physical_schema.names)
        if missing:
            raise ValueError(f"{fragment.path}: 필수 컬럼 누락 {sorted(missing)}")
    scanner = dataset.scanner(columns=list(LOAD_COLUMNS), batch_size=batch_size,
                              use_threads=False, batch_readahead=0, fragment_readahead=0)
    for batch in scanner.to_batches():
        frame = _prepare_batch(batch.to_pandas(), "tw_cems", purpose)
        frame.attrs["input_path"] = str(path)
        yield frame


def iter_domestic_batches(source, *, boto3_session=None,
                          batch_size=BATCH_SIZE, purpose="inspection"):
    """지정 Iceberg 스냅샷을 Athena로 조회한다. 원본 Parquet 직접 읽기 금지.

    purpose는 출처 사용 제한만 확인한다. 전체 snapshot을 로드하며 날짜 분할은
    하지 않는다. 확인 기간·Test 종료 상한은 후속 분할 단계에서 적용해야 한다.
    Athena 결과는 workgroup 설정 경로에 남기며 원본 테이블을 수정하지 않는다.
    """
    config = check_source(source, purpose)
    if source not in ("ktms", "ktms_synth"):
        raise ValueError("국내 로더는 ktms 또는 ktms_synth만 지원합니다")
    _batch_size(batch_size)
    import awswrangler as wr

    columns = ", ".join(f'"{column}"' for column in LOAD_COLUMNS)
    sql = (f'SELECT {columns} FROM "{ATHENA_DATABASE}"."{config.table}" '
           f'FOR VERSION AS OF {config.snapshot_id}')
    batches = wr.athena.read_sql_query(
        sql=sql, database=ATHENA_DATABASE, workgroup=ATHENA_WORKGROUP,
        ctas_approach=False, unload_approach=False, chunksize=batch_size,
        boto3_session=boto3_session, keep_files=True,
    )
    for batch in batches:
        query_metadata = getattr(batch, "query_metadata", {})
        frame = _prepare_batch(batch, source, purpose)
        frame.attrs["athena_query_id"] = query_metadata.get("QueryExecutionId")
        yield frame


def load_source(source, **kwargs):
    """출처별 로더 선택만 수행한다. 반환 iterator를 소비할 때 조회가 시작된다."""
    check_source(source, kwargs.get("purpose", "inspection"))
    if source == "tw_cems":
        return iter_cems_batches(**kwargs)
    return iter_domestic_batches(source, **kwargs)
