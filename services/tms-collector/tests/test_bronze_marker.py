"""bronze_marker: manifest 형식(data-model.md §2)과 키 이름."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
from datetime import datetime

import bronze_marker as bm

PREFIX = "tms_cleansys/ingest_date=2026-11-10/hour=06/run_ts=20261110T060000Z"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_names_and_keys():
    assert (bm.RAW_NAME, bm.META_NAME, bm.MANIFEST_NAME, bm.SUCCESS_NAME) == (
        "snapshot.json.gz", "snapshot.meta.json", "manifest.json", "_SUCCESS"
    )
    assert bm.key(PREFIX, bm.SUCCESS_NAME) == f"{PREFIX}/_SUCCESS"
    assert bm.key(PREFIX + "/", bm.RAW_NAME) == f"{PREFIX}/snapshot.json.gz"


def test_checksum_b64_is_s3_format():
    data = b"hello"
    assert bm.checksum_b64(data) == base64.b64encode(hashlib.sha256(data).digest()).decode()
    assert bm.sha256_hex(data) == _sha(data)


def test_build_manifest_fields():
    raw = b'{"response": 1}'
    gz = gzip.compress(raw, mtime=0)
    meta = json.dumps({"sha256_raw": _sha(raw)}).encode("utf-8")
    body = bm.build_manifest(gz, meta, _sha(raw), "2026-11-10T06:00:05+00:00")
    m = json.loads(body)

    assert list(m) == ["manifest_version", "files", "raw_sha256", "committed_at", "backfilled"]
    assert m["manifest_version"] == 1
    assert m["files"] == [
        {"name": "snapshot.json.gz", "bytes": len(gz), "sha256": _sha(gz)},
        {"name": "snapshot.meta.json", "bytes": len(meta), "sha256": _sha(meta)},
    ]
    assert m["raw_sha256"] == _sha(raw)
    assert m["committed_at"] == "2026-11-10T06:00:05+00:00"
    assert m["backfilled"] is False
    assert all(f["sha256"] == f["sha256"].lower() and len(f["sha256"]) == 64 for f in m["files"])


def test_build_manifest_backfilled_flag():
    m = json.loads(bm.build_manifest(b"x", b"y", "0" * 64, "2026-11-10T06:00:05+00:00", backfilled=True))
    assert m["backfilled"] is True


def test_now_iso_is_utc_seconds():
    stamp = bm.now_iso()
    parsed = datetime.fromisoformat(stamp)
    assert parsed.utcoffset().total_seconds() == 0
    assert parsed.microsecond == 0
