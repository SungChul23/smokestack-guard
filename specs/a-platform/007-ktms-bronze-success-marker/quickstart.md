# Quickstart: 확정 표지 배포와 백필 검증

실행 위치: 코드·테스트·백필은 WSL, Terraform은 PowerShell. AWS에 쓰는 명령은 모두 사람이 실행한다.

## 1. 로컬 테스트

```bash
cd services/tms-collector
uv run --with pytest pytest -q
```

기대: 수집(정상·점검 실패·업로드 실패·원문 같음·재실행 3경우)과 백필(통과·실패 사유·이미 있음·미리보기·재실행) 사례가 모두 통과.

## 2. 배포 (스케줄은 끄지 않는다)

```powershell
cd infra/stacks/tms-collection
terraform plan
```

- 기대: `aws_lambda_function`(tms-collector) 코드 변경 1개뿐. 스케줄·알람·역할 변경이 있으면 apply하지 않는다.
- **수집 직후(매시 x2~x5분)에** `terraform apply`. 배포 시각을 UTC로 적어 둔다(백필 `--before`).

## 3. 배포 직후 확인

- 다음 실행(x0분) 로그 `/aws/lambda/tms-collector`: 오류 없음, 요약에 `marker` 필드.
- 원문이 바뀐 실행(보통 30분 안)의 폴더:
  ```bash
  aws s3 ls s3://smokestack-tms-raw-952900391026/tms_cleansys/ingest_date=<UTC 날짜>/hour=<HH>/run_ts=<...>/
  ```
  기대: `snapshot.json.gz`, `snapshot.meta.json`, `manifest.json`, `_SUCCESS` 네 개.
- 알람 `tms-collector-errors`가 울리지 않음.
- **실패하면**: 이 브랜치 변경을 되돌린 커밋으로 `terraform apply` (research R7).

## 4. 백필

```bash
cd services/tms-collector
uv run --with boto3 python backfill_markers.py --before <배포 시각 UTC, 예: 20261110T060000Z>                  # 미리보기
uv run --with boto3 python backfill_markers.py --before <같은 값> --apply --report /tmp/backfill.json          # 실행
uv run --with boto3 python backfill_markers.py --before <같은 값>                                              # 재확인: would_mark=0
```

기대:
- 미리보기 `targets` ≈ 526 + (배포 전까지 늘어난 폴더), `failed`는 사유와 함께 목록.
- 실행 뒤 `marked` = 미리보기의 `would_mark`.
- 재확인에서 `would_mark=0`, `skipped` = `marked`.

## 5. 결과 확인 (SC-003, SC-004, SC-006)

- 원문·메타 개수·크기: 백필 전후 `aws s3 ls --recursive` 결과에서 `snapshot.*` 줄을 비교해 같음.
- `_SUCCESS` 폴더 수 = `marked` + 배포 이후 수집 Lambda가 표지를 붙인 폴더 수.
- C에게 공유: 배포 시각, 백필 결과(표지 수, 실패 폴더와 사유).

## 실행 결과 (2026-11-11)

| 항목 | 결과 |
|---|---|
| `terraform plan` | 2 to change: 수집 Lambda `source_code_hash`, 스케줄 호출 정책(Lambda 변경 때문에 apply 시 다시 읽을 뿐 내용 같음). 누락률 Lambda·스케줄·버킷 변경 없음 |
| 배포 | 10:32 KST (`20261111T0132xxZ`), 10:30 실행 직후. 스케줄은 끄지 않음 |
| 첫 표지 폴더 | `ingest_date=2026-11-11/hour=01/run_ts=20261111T014000Z/` 네 파일, manifest `backfilled: false`, `committed_at` 01:40:32Z |
| 백필 `--before` | `20261111T013500Z` (마지막 옛 코드 실행 01:30Z와 첫 새 코드 실행 01:40Z 사이) |
| 미리보기 | `targets=562 would_mark=561 skipped=0 failed=1` |
| 실행 (`--apply`) | `marked=561 failed=1` |
| 재확인 | `would_mark=0 skipped=561 failed=1` |
| 실패 폴더 | `ingest_date=2026-10-31/hour=23/run_ts=20261031T235000Z` `inspect_fail`: 수집 당시 메타에 점검 실패(`inspect.ok=false`)로 기록된 스냅샷. 표지 없이 보존, 읽는 쪽은 건너뜀 |

- 원문·메타 개수·크기 전후 비교(SC-004)는 백필 전 목록을 받지 않아 하지 않았다. 백필은 `IfNoneMatch="*"`로 `manifest.json`·`_SUCCESS`만 새로 쓰고 원문·메타·상태 파일에는 put하지 않는다(`tests/test_backfill.py`).
