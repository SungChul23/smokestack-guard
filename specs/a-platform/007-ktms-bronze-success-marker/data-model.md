# Data Model: K-TMS Bronze 확정 표지

경로 기준: 원본 버킷 `smokestack-tms-raw-952900391026`. 시각은 UTC.

## 1. 스냅샷 폴더

`tms_cleansys/ingest_date=YYYY-MM-DD/hour=HH/run_ts=YYYYMMDDTHHMMSSZ/`

| 파일 | 쓰는 쪽 | 내용 | 변경 |
|---|---|---|---|
| `snapshot.json.gz` | 수집 Lambda | API 응답 원문 gzip(`mtime=0`) | 없음 |
| `snapshot.meta.json` | 수집 Lambda | 수집 이력·크기·`sha256_raw`·`raw_key`·`inspect` | 없음 |
| `manifest.json` | 수집 Lambda / 백필 | 아래 §2 | **새로 추가** |
| `_SUCCESS` | 수집 Lambda / 백필 | 0바이트 | **새로 추가** |

**상태 전이**

```
(없음) ─원문·메타 저장─▶ 미완성 ─점검 통과 + manifest + _SUCCESS─▶ 완성(불변)
                          │
                          └─점검 실패 / 업로드 실패─▶ 미완성으로 남음 (읽는 쪽 제외)
```

- **완성** = `_SUCCESS`가 있다. 완성된 폴더의 파일은 다시 쓰지 않는다(research R4).
- **미완성** = `_SUCCESS`가 없다. 같은 `run_ts`의 재실행만 다시 쓸 수 있다.

## 2. `manifest.json`

```json
{
  "manifest_version": 1,
  "files": [
    {"name": "snapshot.json.gz",   "bytes": 61234, "sha256": "<저장된 gzip 바이트의 SHA-256>"},
    {"name": "snapshot.meta.json", "bytes": 812,   "sha256": "<저장된 메타 바이트의 SHA-256>"}
  ],
  "raw_sha256": "<압축 전 원문 SHA-256 = 메타 sha256_raw>",
  "committed_at": "2026-11-10T06:02:11+00:00",
  "backfilled": false
}
```

| 필드 | 규칙 |
|---|---|
| `manifest_version` | 정수 1. 형식이 바뀌면 올린다 |
| `files` | 원문·메타 두 개, 이 순서. `sha256`은 **저장된 바이트**(gzip·JSON) 기준 소문자 hex |
| `raw_sha256` | 압축 전 원문 기준. 메타의 `sha256_raw`, 상태 파일의 `sha256_raw`와 같은 값 |
| `committed_at` | manifest를 쓴 시각(UTC, 초 단위 ISO 8601). 백필은 백필 실행 시각 |
| `backfilled` | 수집 Lambda `false`, 백필 `true` |

B 원안(ab11d17)의 필드(`manifest_version`, `files[name, bytes, sha256]`, `raw_sha256`, `committed_at`)에 `backfilled`만 더했다.

## 3. `_SUCCESS`

- 0바이트, `Content-Type: application/octet-stream`.
- 폴더의 마지막 파일. 있으면 그 폴더는 완성이다.

## 4. 상태 파일 `tms_cleansys/_state/latest.json` (변경 없음)

| 필드 | 의미 |
|---|---|
| `sha256_raw` | 마지막으로 저장한 원문 해시 |
| `last_changed_at` | 그 원문을 저장한 실행 시각 |
| `last_checked_at` | 마지막 실행 시각(원문이 같아도 갱신) |
| `raw_key` | 마지막 저장 원문 경로 |

이번 변경은 **언제 갱신하느냐**만 바뀐다: `_SUCCESS`를 쓴 뒤(또는 R4에서 이미 완성된 같은 원문 폴더를 확인한 뒤).

## 5. 백필 판정 (폴더 하나)

| 순서 | 검사 | 실패 사유 코드 |
|---|---|---|
| 1 | `run_ts` < `--before` | (대상 아님, 세지 않음) |
| 2 | `_SUCCESS` 없음 | `already_marked` (건너뜀) |
| 3 | 원문 있음 | `raw_missing` |
| 4 | 메타 있음, JSON으로 읽힘 | `meta_missing` / `meta_invalid` |
| 5 | 원문을 풀어 계산한 SHA-256 = 메타 `sha256_raw` | `hash_mismatch` |
| 6 | 메타 `inspect.ok` = true | `inspect_fail` |
| 7 | 메타 `raw_key` = 이 폴더의 원문 경로 | `raw_key_mismatch` |
| 8 | `manifest.json`이 이미 있으면 그 `raw_sha256` = 이번 원문 (지난 백필이 `_SUCCESS` 전에 끊긴 경우) | `manifest_conflict` |
| 통과 | manifest(`backfilled: true`, 이미 있으면 그대로) → `_SUCCESS` | |
