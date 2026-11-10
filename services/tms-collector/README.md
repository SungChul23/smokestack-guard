# tms-collector

한국환경공단 굴뚝자동측정기기(CleanSYS) 공개 API를 10분마다 호출해 원본을 S3에 보존하는 Lambda입니다.
공개 API는 과거 조회를 지원하지 않으므로, 놓친 데이터는 다시 받을 수 없습니다.

## 구성

```
EventBridge Scheduler (매시 00분부터 10분 단위, Asia/Seoul)
        │  {"time": "<aws.scheduler.scheduled-time>"}
        ▼
Lambda: tms-collector ──▶ SSM Parameter Store: /tms/collector/api-key
        │
        ├──▶ CleanSYS API: rltmMesureResult
        ├──▶ S3: smokestack-tms-raw-952900391026
        └──▶ CloudWatch Logs: /aws/lambda/tms-collector (보존 14일)

CloudWatch 알람: tms-collector-errors ──▶ SNS: tms-collector-alerts ──▶ 이메일
```

| 항목 | 값 |
|---|---|
| 런타임 | Python 3.13 (표준 라이브러리 + boto3) |
| 핸들러 | `handler.lambda_handler` |
| 메모리 / 제한 시간 | 256MB / 240초 |
| 스케줄 | `cron(0/10 * * * ? *)`, 유연한 시간 창 OFF |
| 환경 변수 | `BRONZE_BUCKET`, `API_KEY_PARAMETER` |
| 인프라 코드 | `infra/stacks/tms-collection`, `infra/modules/scheduled-collector`, `infra/modules/raw-archive` |

## 처리 흐름

1. 이벤트의 `time`을 10분 단위로 내려 `run_ts`를 정합니다.
2. SSM에서 API 키를 읽어 전역 변수에 캐시합니다.
3. API 전체 스냅샷을 받아 SHA-256 해시를 계산합니다.
4. 상태 파일의 해시와 비교합니다.
   - 같으면 원문을 저장하지 않고 `last_checked_at`만 갱신합니다.
   - 다르면 gzip 원문과 메타 파일을 저장합니다. 업로드에 `ChecksumSHA256`을 붙여 S3가 받은 내용이 다르면 거부하게 합니다.
5. 응답을 점검합니다. `resultCode`가 `0`이고 전체 건수와 실제 건수가 같아야 합니다.
   - 실패하면 원문·메타는 남겨 두고, 확정 표지와 상태는 쓰지 않은 채 예외를 던집니다.
6. 점검을 통과하면 확정 표지 `manifest.json`(원문·메타의 크기·SHA-256) → `_SUCCESS`(0바이트)를 씁니다.
7. 상태 파일을 마지막에 갱신합니다. 앞 단계가 하나라도 실패하면 상태가 그대로라 다음 실행이 새 폴더에 다시 저장합니다.

**읽는 쪽은 `_SUCCESS`가 있는 폴더만 완성된 스냅샷으로 봅니다.** 규칙: [`specs/a-platform/007-ktms-bronze-success-marker/contracts/bronze-snapshot-folder.md`](../../specs/a-platform/007-ktms-bronze-success-marker/contracts/bronze-snapshot-folder.md). 표지 형식은 `bronze_marker.py`에 있습니다.

`last_checked_at`은 매 실행 갱신되므로 "API 갱신 없음"과 "수집 중단"을 구분할 수 있습니다.

## S3 경로

시각은 모두 UTC입니다. 한국 시각 14:10 실행은 `hour=05`, `run_ts=...T051000Z`에 저장됩니다.

```
tms_cleansys/
├── ingest_date=YYYY-MM-DD/hour=HH/run_ts=YYYYMMDDTHHMMSSZ/
│   ├── snapshot.json.gz     # API 응답 원문
│   ├── snapshot.meta.json   # 수집 이력, 크기, 해시, 점검 결과
│   ├── manifest.json        # 확정 표지: 위 두 파일의 크기·SHA-256, 원문 SHA-256
│   └── _SUCCESS             # 확정 표지: 0바이트, 폴더의 마지막 파일
└── _state/
    └── latest.json          # sha256_raw, last_changed_at, last_checked_at, raw_key
```

## 재시도와 실패 처리

| 단계 | 대상 | 동작 |
|---|---|---|
| 수집 코드 | 네트워크 오류, HTTP 429, 500, 502, 503, 504 | 최대 3회 시도 (2초, 5초 대기) |
| Lambda 비동기 호출 | 함수 실패 | AWS 기본값으로 최대 2회 재실행 |
| EventBridge Scheduler | Lambda 호출 전달 실패 | AWS 기본 재시도 정책 |

- 그 밖의 HTTP 오류(예: 401)는 코드에서 재시도하지 않고 바로 실패하며, Lambda 재실행 대상이 됩니다.
- Lambda 재실행은 같은 `time`을 받으므로 같은 `run_ts` 경로에 저장됩니다.
- 그 폴더에 이미 `_SUCCESS`가 있으면 다시 쓰지 않습니다. 같은 원문이면 상태 파일만 갱신하고(`marker: already_committed`), 다른 원문이면 아무것도 쓰지 않고 다음 실행에 맡깁니다(`marker: skipped_committed_folder`).
- DLQ는 없습니다. 재시도를 모두 실패하면 그 회차는 복구할 수 없으며, 알람으로만 알 수 있습니다.

## 알람

`tms-collector-errors`는 15분 단위로 `Errors` 합계가 1 이상이면 울립니다.
값이 없을 때도 경보로 처리하므로, 스케줄이 멈춰 Lambda가 호출되지 않아도 알 수 있습니다.

## 권한과 비밀값

- API 키는 SSM Parameter Store의 SecureString(`alias/aws/ssm`)에 콘솔로 직접 등록합니다. Terraform은 파라미터 이름만 참조합니다.
- 실행 역할 권한: 로그 쓰기, 원본 버킷 `s3:GetObject`/`s3:PutObject`, 파라미터 1개 `ssm:GetParameter`, 복호화.
- `s3:ListBucket`이 없어 상태 파일이 없으면 S3가 `AccessDenied`를 반환합니다. 코드는 이를 첫 실행으로 처리해 원문을 저장합니다.
- 로그에는 요약만 남기고, API 응답 본문과 키는 남기지 않습니다.

## 운영 확인

- 정상 동작: `tms_cleansys/_state/latest.json`의 `last_checked_at`이 10분마다 바뀌는지 봅니다.
- 원문이 새로 안 생겨도 `last_checked_at`이 갱신되면 API 값이 바뀌지 않은 정상 상태입니다.
- 실패 원인: CloudWatch 로그 그룹 `/aws/lambda/tms-collector`를 확인합니다.
- API 키 교체: Parameter Store 값을 바꿉니다. 실행 환경이 캐시한 이전 키가 잠시 쓰일 수 있습니다.

## 알려진 제약

- 예약 동시 실행을 쓰지 않습니다. 계정 동시 실행 한도가 10이면 설정할 수 없어서이며, 한도 상향 후 `1`로 설정합니다.
- 실행이 겹치면 상태 파일이 어긋날 수 있지만, 스냅샷이 한 번 더 저장될 뿐 원본은 사라지지 않습니다.

## 테스트

```bash
cd services/tms-collector
uv run --with pytest --with boto3 pytest -q
```

S3·SSM은 `tests/conftest.py`의 가짜 클라이언트로 대신합니다. CI: `.github/workflows/tms-collector.yml`.
테스트·백필 파일은 Lambda zip에 들어가지 않습니다(`infra/modules/scheduled-collector`의 `excludes`).

## 배포 (스케줄은 끄지 않습니다)

1. `infra/stacks/tms-collection`에서 `terraform plan` → 수집 함수 코드 변경 하나뿐인지 확인합니다.
2. **수집 직후(매시 x2~x5분)에** `terraform apply`하고 배포 시각(UTC)을 적어 둡니다.
3. 다음 실행 로그에 오류가 없고 요약에 `marker`가 있는지, 원문이 바뀐 실행의 폴더에 네 파일이 있는지 확인합니다.
4. 실패하면 변경을 되돌린 커밋으로 다시 apply합니다. 놓치는 실행은 최대 1회이고, 그 슬롯은 다음 실행들이 다시 받습니다.

## 백필 (배포 이전 폴더에 표지 붙이기)

```bash
cd services/tms-collector
uv run --with boto3 python backfill_markers.py --before <배포 시각, 예: 20261110T060000Z>              # 미리보기 (쓰지 않음)
uv run --with boto3 python backfill_markers.py --before <같은 값> --apply --report /tmp/backfill.json  # 실행
uv run --with boto3 python backfill_markers.py --before <같은 값>                                       # 재확인: would_mark=0
```

- 원문·메타가 온전하고 원문 점검을 통과한 폴더에만 표지(`backfilled: true`)를 추가합니다. 실패 폴더는 사유와 함께 출력합니다.
- 없을 때만 생성(`IfNoneMatch="*"`)이라 기존 객체를 덮어쓰지 않고, `_state/latest.json`은 건드리지 않습니다.
- 인자·출력: [`contracts/backfill-cli.md`](../../specs/a-platform/007-ktms-bronze-success-marker/contracts/backfill-cli.md)
