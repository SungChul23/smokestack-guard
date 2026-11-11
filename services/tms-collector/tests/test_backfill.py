"""백필 명령 (spec US2, data-model.md §5, contracts/backfill-cli.md)."""

from __future__ import annotations

import gzip
import hashlib
import json

from conftest import make_payload

import backfill_markers as bf
import bronze_marker as bm

BEFORE = "20261110T060000Z"
STATE = "tms_cleansys/_state/latest.json"


def _folder(run_ts: str) -> str:
    return f"tms_cleansys/ingest_date={run_ts[:4]}-{run_ts[4:6]}-{run_ts[6:8]}/hour={run_ts[9:11]}/run_ts={run_ts}"


def _put_snapshot(s3, run_ts: str, *, raw=True, meta=True, inspect_ok=True, sha_override=None,
                  raw_key_override=None, meta_bytes=None, tag="x") -> str:
    folder = _folder(run_ts)
    content = make_payload(tag=tag + run_ts)
    if raw:
        s3.objects[bm.key(folder, bm.RAW_NAME)] = gzip.compress(content, mtime=0)
    if meta:
        body = meta_bytes if meta_bytes is not None else json.dumps({
            "sha256_raw": sha_override or hashlib.sha256(content).hexdigest(),
            "raw_key": raw_key_override or bm.key(folder, bm.RAW_NAME),
            "inspect": {"ok": inspect_ok},
        }).encode("utf-8")
        s3.objects[bm.key(folder, bm.META_NAME)] = body
    return folder


def _scenario(s3) -> dict[str, str]:
    """통과 1, 사유별 실패 6, 이미 표지 1, 기준 시각 이후 1."""
    f = {
        "ok": _put_snapshot(s3, "20261101T000000Z"),
        "raw_missing": _put_snapshot(s3, "20261101T001000Z", raw=False),
        "meta_missing": _put_snapshot(s3, "20261101T002000Z", meta=False),
        "meta_invalid": _put_snapshot(s3, "20261101T003000Z", meta_bytes=b"{not json"),
        "hash_mismatch": _put_snapshot(s3, "20261101T004000Z", sha_override="0" * 64),
        "inspect_fail": _put_snapshot(s3, "20261101T005000Z", inspect_ok=False),
        "raw_key_mismatch": _put_snapshot(s3, "20261101T010000Z", raw_key_override="tms_cleansys/other/snapshot.json.gz"),
        "marked": _put_snapshot(s3, "20261101T011000Z"),
        "after": _put_snapshot(s3, "20261110T061000Z"),
    }
    s3.objects[bm.key(f["marked"], bm.SUCCESS_NAME)] = b""
    s3.objects[STATE] = b'{"sha256_raw": "x"}'
    return f


def _run(s3, *args):
    return bf.main(["--before", BEFORE, *args], s3=s3)


def test_preview_writes_nothing_and_counts(s3, capsys):
    _scenario(s3)
    before = dict(s3.objects)

    code = _run(s3)

    assert code == 0
    assert s3.put_log == [] and s3.objects == before
    out = capsys.readouterr().out
    assert out.splitlines()[0] == f"mode=preview before={BEFORE} targets=8 marked=0 would_mark=1 skipped=1 failed=6"


def test_apply_marks_only_valid_folder_with_reasons(s3, capsys, tmp_path):
    f = _scenario(s3)
    report_path = tmp_path / "report.json"

    code = _run(s3, "--apply", "--report", str(report_path))

    assert code == 0
    ok = f["ok"]
    assert s3.put_log == [bm.key(ok, bm.MANIFEST_NAME), bm.key(ok, bm.SUCCESS_NAME)]
    manifest = json.loads(s3.objects[bm.key(ok, bm.MANIFEST_NAME)])
    raw = s3.objects[bm.key(ok, bm.RAW_NAME)]
    assert manifest["backfilled"] is True
    assert manifest["raw_sha256"] == hashlib.sha256(gzip.decompress(raw)).hexdigest()
    assert manifest["files"][0] == {"name": bm.RAW_NAME, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    assert s3.objects[bm.key(ok, bm.SUCCESS_NAME)] == b""
    for k in s3.put_log:                                          # 없을 때만 생성 + 체크섬
        assert s3.put_kwargs[k]["IfNoneMatch"] == "*"
        assert s3.put_kwargs[k]["ChecksumSHA256"] == bm.checksum_b64(s3.objects[k])

    report = json.loads(report_path.read_text())
    assert (report["mode"], report["targets"], report["marked"], report["skipped"]) == ("apply", 8, 1, 1)
    assert {r["reason"]: r["folder"] for r in report["failed"]} == {
        reason: f[reason] for reason in
        ("raw_missing", "meta_missing", "meta_invalid", "hash_mismatch", "inspect_fail", "raw_key_mismatch")
    }
    out = capsys.readouterr().out
    assert f"FAILED {f['inspect_fail']} inspect_fail" in out
    assert bm.key(f["after"], bm.SUCCESS_NAME) not in s3.objects   # 기준 시각 이후는 대상 아님


def test_apply_never_touches_raw_meta_or_state(s3):
    _scenario(s3)
    snapshot = {k: v for k, v in s3.objects.items() if not k.endswith((bm.MANIFEST_NAME, bm.SUCCESS_NAME))}

    _run(s3, "--apply")

    assert {k: v for k, v in s3.objects.items() if not k.endswith((bm.MANIFEST_NAME, bm.SUCCESS_NAME))} == snapshot
    assert all(k.endswith((bm.MANIFEST_NAME, bm.SUCCESS_NAME)) for k in s3.put_log)


def test_rerun_marks_nothing(s3, capsys):
    _scenario(s3)
    _run(s3, "--apply")
    s3.put_log.clear()
    capsys.readouterr()

    _run(s3, "--apply")

    assert s3.put_log == []
    assert "marked=0" in capsys.readouterr().out.splitlines()[0]


def test_manifest_without_success_from_interrupted_run_is_completed(s3):
    f = _scenario(s3)
    ok = f["ok"]
    _run(s3, "--apply")
    del s3.objects[bm.key(ok, bm.SUCCESS_NAME)]                   # 지난 백필이 manifest만 쓰고 끊긴 상태
    manifest_before = s3.objects[bm.key(ok, bm.MANIFEST_NAME)]
    s3.put_log.clear()

    report = bf.run(s3, "b", "tms_cleansys", BEFORE, apply=True)

    assert s3.put_log == [bm.key(ok, bm.SUCCESS_NAME)]
    assert s3.objects[bm.key(ok, bm.MANIFEST_NAME)] == manifest_before
    assert report["marked"] == 1


def test_conflicting_manifest_is_failure(s3):
    f = _scenario(s3)
    ok = f["ok"]
    s3.objects[bm.key(ok, bm.MANIFEST_NAME)] = json.dumps({"raw_sha256": "f" * 64}).encode("utf-8")

    report = bf.run(s3, "b", "tms_cleansys", BEFORE, apply=True)

    assert bm.key(ok, bm.SUCCESS_NAME) not in s3.objects
    assert {"folder": ok, "reason": "manifest_conflict"} in report["failed"]


def test_bad_before_argument_exits_1(s3):
    assert bf.main(["--before", "2026-11-10"], s3=s3) == 1
