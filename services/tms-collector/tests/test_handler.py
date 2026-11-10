"""수집 Lambda의 저장 흐름과 확정 표지 (spec US1, research R1~R4)."""

from __future__ import annotations

import gzip
import hashlib
import json

import pytest
from botocore.exceptions import ClientError
from conftest import make_payload

import bronze_marker as bm

EVENT = {"time": "2026-11-10T06:00:00Z"}
PREFIX = "tms_cleansys/ingest_date=2026-11-10/hour=06/run_ts=20261110T060000Z"
STATE = "tms_cleansys/_state/latest.json"
RAW, META, MANIFEST, SUCCESS = (bm.key(PREFIX, n) for n in (bm.RAW_NAME, bm.META_NAME, bm.MANIFEST_NAME, bm.SUCCESS_NAME))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _put_state(s3, sha: str, raw_key: str = "tms_cleansys/old/snapshot.json.gz"):
    state = {"sha256_raw": sha, "last_changed_at": "2026-11-10T05:00:00+00:00",
             "last_checked_at": "2026-11-10T05:50:00+00:00", "raw_key": raw_key}
    s3.objects[STATE] = json.dumps(state).encode("utf-8")
    return state


def _state(s3) -> dict:
    return json.loads(s3.objects[STATE])


def _summary(capsys) -> dict:
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    return json.loads(lines[-1])


# ---------------------------------------------------------------------------
# T007 정상 저장
# ---------------------------------------------------------------------------


def test_changed_writes_four_files_in_order_then_state(handler, fetch, s3, capsys):
    _put_state(s3, "0" * 64)
    content = make_payload(tag="new")
    fetch(content)

    out = handler.lambda_handler(EVENT, None)

    assert s3.put_log == [RAW, META, MANIFEST, SUCCESS, STATE]
    manifest = json.loads(s3.objects[MANIFEST])
    assert manifest["files"] == [
        {"name": bm.RAW_NAME, "bytes": len(s3.objects[RAW]), "sha256": _sha(s3.objects[RAW])},
        {"name": bm.META_NAME, "bytes": len(s3.objects[META]), "sha256": _sha(s3.objects[META])},
    ]
    assert manifest["raw_sha256"] == _sha(content) == json.loads(s3.objects[META])["sha256_raw"]
    assert manifest["backfilled"] is False
    assert gzip.decompress(s3.objects[RAW]) == content

    assert s3.objects[SUCCESS] == b""
    assert s3.content_types[SUCCESS] == "application/octet-stream"
    for k in (RAW, META, MANIFEST):
        assert s3.put_kwargs[k]["ChecksumSHA256"] == bm.checksum_b64(s3.objects[k])

    state = _state(s3)
    assert set(state) == {"sha256_raw", "last_changed_at", "last_checked_at", "raw_key"}
    assert state["sha256_raw"] == _sha(content)
    assert state["raw_key"] == RAW
    assert state["last_changed_at"] == state["last_checked_at"] == "2026-11-10T06:00:00+00:00"

    assert out["changed"] is True and out["marker"] == "written"
    assert _summary(capsys)["marker"] == "written"


def test_first_run_without_state_also_commits(handler, fetch, s3):
    fetch(make_payload())
    handler.lambda_handler(EVENT, None)
    assert SUCCESS in s3.objects and _state(s3)["raw_key"] == RAW


# ---------------------------------------------------------------------------
# T008 원문 점검 실패
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("content", [make_payload(code="99"), make_payload(items=3, total=5), b"not json"])
def test_inspect_fail_keeps_raw_meta_but_no_marker_no_state(handler, fetch, s3, content):
    before = _put_state(s3, "0" * 64)
    fetch(content)

    with pytest.raises(RuntimeError):
        handler.lambda_handler(EVENT, None)

    assert RAW in s3.objects and META in s3.objects
    assert MANIFEST not in s3.objects and SUCCESS not in s3.objects
    assert _state(s3) == before


# ---------------------------------------------------------------------------
# T009 업로드 실패
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("failing", [RAW, META, MANIFEST, SUCCESS])
def test_upload_failure_stops_before_marker_and_state(handler, fetch, s3, failing):
    before = _put_state(s3, "0" * 64)
    fetch(make_payload(tag="new"))
    s3.fail_on_put[failing] = "BadDigest"

    with pytest.raises(ClientError):
        handler.lambda_handler(EVENT, None)

    assert SUCCESS not in s3.objects
    assert _state(s3) == before
    order = [RAW, META, MANIFEST, SUCCESS]
    assert s3.put_log == order[: order.index(failing)]          # 실패한 단계 뒤로는 아무것도 쓰지 않는다


# ---------------------------------------------------------------------------
# T010 원문이 이전과 같음
# ---------------------------------------------------------------------------


def test_unchanged_only_updates_last_checked_at(handler, fetch, s3):
    content = make_payload(tag="same")
    before = _put_state(s3, _sha(content))
    fetch(content)

    out = handler.lambda_handler(EVENT, None)

    assert s3.put_log == [STATE]
    state = _state(s3)
    assert state == {**before, "last_checked_at": "2026-11-10T06:00:00+00:00"}
    assert out["changed"] is False
    assert "marker" not in out


# ---------------------------------------------------------------------------
# T011 같은 run_ts 재실행 (research R4)
# ---------------------------------------------------------------------------


def test_retry_rewrites_uncommitted_folder(handler, fetch, s3):
    _put_state(s3, "0" * 64)
    s3.objects[RAW] = b"partial from first attempt"             # 앞 시도: 원문만 쓰고 끊김
    content = make_payload(tag="new")
    fetch(content)

    out = handler.lambda_handler(EVENT, None)

    assert out["marker"] == "written"
    assert gzip.decompress(s3.objects[RAW]) == content
    assert SUCCESS in s3.objects and _state(s3)["sha256_raw"] == _sha(content)


def _commit_first_attempt(handler, fetch, s3, content):
    """앞 시도가 표지까지 쓰고 상태 저장에서 실패한 상황을 만든다."""
    _put_state(s3, "0" * 64)
    fetch(content)
    s3.fail_on_put[STATE] = "InternalError"
    with pytest.raises(ClientError):
        handler.lambda_handler(EVENT, None)
    assert SUCCESS in s3.objects
    s3.fail_on_put.clear()
    s3.put_log.clear()


def test_retry_same_raw_on_committed_folder_only_saves_state(handler, fetch, s3):
    content = make_payload(tag="new")
    _commit_first_attempt(handler, fetch, s3, content)
    folder = {k: v for k, v in s3.objects.items() if k.startswith(PREFIX)}

    out = handler.lambda_handler(EVENT, None)

    assert s3.put_log == [STATE]
    assert {k: v for k, v in s3.objects.items() if k.startswith(PREFIX)} == folder
    assert _state(s3)["sha256_raw"] == _sha(content) and _state(s3)["raw_key"] == RAW
    assert out["marker"] == "already_committed"


def test_retry_different_raw_on_committed_folder_writes_nothing(handler, fetch, s3, capsys):
    _commit_first_attempt(handler, fetch, s3, make_payload(tag="first"))
    folder = {k: v for k, v in s3.objects.items() if k.startswith(PREFIX)}
    state_before = s3.objects[STATE]
    fetch(make_payload(tag="second"))

    out = handler.lambda_handler(EVENT, None)                   # 예외 없이 끝난다

    assert s3.put_log == []
    assert {k: v for k, v in s3.objects.items() if k.startswith(PREFIX)} == folder
    assert s3.objects[STATE] == state_before
    assert out["marker"] == "skipped_committed_folder"
    assert _summary(capsys)["marker"] == "skipped_committed_folder"


# ---------------------------------------------------------------------------
# T012 로그에 본문·키가 없다
# ---------------------------------------------------------------------------


def test_log_has_summary_only(handler, fetch, s3, capsys):
    _put_state(s3, "0" * 64)
    content = make_payload(tag="secret-body-marker")
    fetch(content)

    handler.lambda_handler(EVENT, None)

    out = capsys.readouterr().out
    assert "secret-body-marker" not in out
    assert "test-api-key" not in out
