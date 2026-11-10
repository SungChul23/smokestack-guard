"""배포 이전 K-TMS 스냅샷 폴더에 확정 표지(manifest.json, _SUCCESS)를 붙인다. 사람이 한 번 실행한다.

규칙: specs/a-platform/007-ktms-bronze-success-marker (data-model.md §5, contracts/backfill-cli.md)
- --before 이전 run_ts 폴더 중 원문·메타가 온전하고 원문 점검을 통과한 폴더에만 표지를 추가한다.
- 기본은 미리보기(쓰지 않음). --apply일 때만 쓴다.
- 쓰기는 IfNoneMatch="*"(없을 때만 생성)와 ChecksumSHA256으로 한다. 기존 객체는 덮어쓰거나 지우지 않는다.
- _state/latest.json은 읽지도 쓰지도 않는다.

이 파일은 Lambda zip에 들어가지 않는다(infra/modules/scheduled-collector excludes).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from botocore.exceptions import ClientError

import bronze_marker as bm

DEFAULT_BUCKET = "smokestack-tms-raw-952900391026"
DEFAULT_PREFIX = "tms_cleansys"
DEFAULT_REGION = "ap-northeast-2"
RUN_TS_RE = re.compile(r"^\d{8}T\d{6}Z$")
FOLDER_RE = re.compile(r"^(?P<folder>.+/run_ts=(?P<run_ts>\d{8}T\d{6}Z))/(?P<name>[^/]+)$")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="K-TMS Bronze 확정 표지 백필 (기본: 미리보기)")
    parser.add_argument("--before", required=True, help="이 UTC 시각(YYYYMMDDTHHMMSSZ) 이전 run_ts 폴더만 대상")
    parser.add_argument("--apply", action="store_true", help="S3에 쓴다. 없으면 미리보기")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--report", type=Path, default=None, help="결과 JSON을 저장할 로컬 경로")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--region", default=DEFAULT_REGION)
    args = parser.parse_args(argv)
    if not RUN_TS_RE.match(args.before):
        parser.error(f"--before는 YYYYMMDDTHHMMSSZ 형식이어야 한다: {args.before!r}")
    return args


# run_ts 폴더별 파일 이름 모음 {폴더: (run_ts, {이름})}
def list_folders(s3, bucket: str, prefix: str) -> dict[str, tuple[str, set[str]]]:
    folders: dict[str, tuple[str, set[str]]] = {}
    names: dict[str, set[str]] = defaultdict(set)
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=f"{prefix.rstrip('/')}/ingest_date="):
        for obj in page.get("Contents", []):
            m = FOLDER_RE.match(obj["Key"])
            if m:
                names[m["folder"]].add(m["name"])
                folders[m["folder"]] = (m["run_ts"], names[m["folder"]])
    return folders


def _get(s3, bucket: str, key: str) -> bytes:
    return s3.get_object(Bucket=bucket, Key=key)["Body"].read()


def _create(s3, bucket: str, key: str, body: bytes, content_type: str) -> bool:
    """없을 때만 생성. 이미 있으면 False."""
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type,
                      ChecksumSHA256=bm.checksum_b64(body), IfNoneMatch="*")
    except ClientError as exc:
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if exc.response["Error"]["Code"] == "PreconditionFailed" or status == 412:
            return False
        raise
    return True


# 폴더 하나 처리. 결과: "marked" | "would_mark" | "skipped" | 실패 사유 코드
def process_folder(s3, bucket: str, folder: str, names: set[str], apply: bool) -> str:
    if bm.SUCCESS_NAME in names:
        return "skipped"
    raw = _get(s3, bucket, bm.key(folder, bm.RAW_NAME)) if bm.RAW_NAME in names else None
    meta = _get(s3, bucket, bm.key(folder, bm.META_NAME)) if bm.META_NAME in names else None
    reason, raw_sha = bm.check_folder(folder, raw, meta)
    if reason:
        return reason

    manifest_key = bm.key(folder, bm.MANIFEST_NAME)
    if bm.MANIFEST_NAME in names:                                   # 지난 백필이 manifest만 쓰고 끊긴 경우
        existing = json.loads(_get(s3, bucket, manifest_key))
        if existing.get("raw_sha256") != raw_sha:
            return "manifest_conflict"
    if not apply:
        return "would_mark"

    manifest = bm.build_manifest(raw, meta, raw_sha, bm.now_iso(), backfilled=True)
    if not _create(s3, bucket, manifest_key, manifest, "application/json"):
        existing = json.loads(_get(s3, bucket, manifest_key))       # 목록을 읽은 뒤 생긴 manifest
        if existing.get("raw_sha256") != raw_sha:
            return "manifest_conflict"
    if not _create(s3, bucket, bm.key(folder, bm.SUCCESS_NAME), b"", "application/octet-stream"):
        return "skipped"
    return "marked"


def run(s3, bucket: str, prefix: str, before: str, apply: bool) -> dict:
    report = {"mode": "apply" if apply else "preview", "before": before,
              "targets": 0, "marked": 0, "would_mark": 0, "skipped": 0, "failed": []}
    for folder, (run_ts, names) in sorted(list_folders(s3, bucket, prefix).items()):
        if run_ts >= before:                                        # 배포 이후 폴더는 수집 Lambda가 표지를 붙인다
            continue
        report["targets"] += 1
        outcome = process_folder(s3, bucket, folder, names, apply)
        if outcome in ("marked", "would_mark", "skipped"):
            report[outcome] += 1
        else:
            report["failed"].append({"folder": folder, "reason": outcome})
    report["finished_at"] = bm.now_iso()
    return report


def main(argv: list[str] | None = None, s3=None) -> int:
    try:
        args = parse_args(argv)
    except SystemExit:
        return 1
    if s3 is None:
        import boto3

        s3 = boto3.Session(profile_name=args.profile, region_name=args.region).client("s3")

    try:
        report = run(s3, args.bucket, args.prefix, args.before, args.apply)
    except ClientError as exc:
        print(f"중단: {exc.response['Error']['Code']} ({exc.operation_name})", file=sys.stderr)
        return 1

    print(f"mode={report['mode']} before={report['before']} targets={report['targets']} "
          f"marked={report['marked']} would_mark={report['would_mark']} "
          f"skipped={report['skipped']} failed={len(report['failed'])}")
    for item in report["failed"]:
        print(f"FAILED {item['folder']} {item['reason']}")
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
