# Bronze 확정 표지(manifest.json, _SUCCESS). 수집 Lambda(handler.py)와 백필(backfill_markers.py)이 함께 쓴다.
# 형식: specs/a-platform/007-ktms-bronze-success-marker/data-model.md
# 원안: B의 8-k-tms-bronze 브랜치(ab11d17). 필드는 같고 backfilled만 더했다.
# 표준 라이브러리만 쓴다(Lambda zip에 들어간다).

import base64
import gzip
import hashlib
import json
import zlib
from datetime import datetime, timezone

RAW_NAME = "snapshot.json.gz"               # 원문 (gzip)
META_NAME = "snapshot.meta.json"            # 수집 메타
MANIFEST_NAME = "manifest.json"             # 파일 목록과 해시
SUCCESS_NAME = "_SUCCESS"                   # 폴더 완성 표지 (0바이트, 마지막에 쓴다)
MANIFEST_VERSION = 1


# 데이터의 SHA-256 (소문자 hex)
def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# S3 put_object의 ChecksumSHA256 값 (digest의 base64). S3가 받은 내용과 다르면 업로드를 거부한다.
def checksum_b64(data: bytes) -> str:
    return base64.b64encode(hashlib.sha256(data).digest()).decode("ascii")


# 폴더 경로와 파일 이름으로 객체 키 생성
def key(prefix: str, name: str) -> str:
    return f"{prefix.rstrip('/')}/{name}"


# 현재 UTC 시각 (초 단위 ISO 8601)
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec = "seconds")


# manifest.json 본문. files의 sha256은 저장된 바이트(gzip, 메타 JSON) 기준, raw_sha256은 압축 전 원문 기준
def build_manifest(raw_gz: bytes, meta_bytes: bytes, raw_sha256: str, committed_at: str, backfilled: bool = False) -> bytes:
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "files": [
            {"name": RAW_NAME, "bytes": len(raw_gz), "sha256": sha256_hex(raw_gz)},
            {"name": META_NAME, "bytes": len(meta_bytes), "sha256": sha256_hex(meta_bytes)},
        ],
        "raw_sha256": raw_sha256,
        "committed_at": committed_at,
        "backfilled": backfilled,
    }
    return json.dumps(manifest, ensure_ascii = False, indent = 2).encode("utf-8")


# 백필 판정 (data-model.md §5의 3~7). 통과하면 (None, raw_sha256), 아니면 (사유 코드, None)
def check_folder(prefix: str, raw_gz: bytes | None, meta_bytes: bytes | None) -> tuple[str | None, str | None]:
    if raw_gz is None:
        return "raw_missing", None
    if meta_bytes is None:
        return "meta_missing", None
    try:
        meta = json.loads(meta_bytes)
        expected = meta["sha256_raw"]
    except (ValueError, KeyError, TypeError):
        return "meta_invalid", None

    try:
        actual = sha256_hex(gzip.decompress(raw_gz))
    except (OSError, EOFError, zlib.error):                         # gzip이 깨졌으면 원문이 메타와 같다고 볼 수 없다
        return "hash_mismatch", None
    if actual != expected:
        return "hash_mismatch", None

    if not (meta.get("inspect") or {}).get("ok"):
        return "inspect_fail", None
    if meta.get("raw_key") != key(prefix, RAW_NAME):
        return "raw_key_mismatch", None
    return None, actual
