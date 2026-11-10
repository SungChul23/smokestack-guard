# Contract: 백필 명령 `backfill_markers.py`

위치: `services/tms-collector/backfill_markers.py` (Lambda zip에 들어가지 않는다). 실행: 사람(A), WSL, 본인 AWS 자격 증명.

## 인자

| 인자 | 필수 | 기본 | 설명 |
|---|---|---|---|
| `--before` | ✅ | | 이 UTC 시각(`YYYYMMDDTHHMMSSZ`) **이전** `run_ts` 폴더만 대상. 배포 시각을 넣는다 |
| `--apply` | | 꺼짐 | 켜야 S3에 쓴다. 없으면 미리보기 |
| `--bucket` | | `smokestack-tms-raw-952900391026` | |
| `--prefix` | | `tms_cleansys` | |
| `--report` | | 없음 | 결과 JSON을 이 로컬 경로에 저장 |
| `--profile`, `--region` | | 기본 자격 증명, `ap-northeast-2` | |

## 출력

표준 출력에 요약 한 줄과 실패 목록을 쓴다.

```
mode=preview before=20261110T060000Z targets=526 marked=0 would_mark=523 skipped=0 failed=3
FAILED tms_cleansys/ingest_date=.../run_ts=... inspect_fail
```

`--report` JSON:

```json
{"mode": "apply", "before": "20261110T060000Z", "targets": 526, "marked": 523, "skipped": 0,
 "failed": [{"folder": "tms_cleansys/...", "reason": "inspect_fail"}], "finished_at": "..."}
```

## 종료 코드

| 코드 | 의미 |
|---|---|
| 0 | 끝까지 실행 (실패 폴더가 있어도 0. 실패는 목록으로 판단) |
| 1 | 인자 오류, 자격 증명·권한 오류 등으로 중단 |

## 보장

- 기존 객체를 덮어쓰거나 지우지 않는다. 쓰기는 "없을 때만 생성" 조건으로 한다.
- 다시 실행해도 결과가 같다. 이미 표지가 있는 폴더는 `skipped`로 센다.
- `_state/latest.json`은 읽지도 쓰지도 않는다.
- 지난 실행이 `manifest.json`만 쓰고 끊긴 폴더는, 그 manifest의 원문 해시가 같으면 `_SUCCESS`만 마저 쓴다. 다르면 `manifest_conflict`로 실패 목록에 남긴다.

실패 사유 코드: `raw_missing`, `meta_missing`, `meta_invalid`, `hash_mismatch`, `inspect_fail`, `raw_key_mismatch`, `manifest_conflict` (data-model.md §5)
