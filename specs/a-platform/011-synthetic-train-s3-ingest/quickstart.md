# Quickstart: 합성 적재 배포와 운영

순서: 로컬 테스트 → 참조 통계 업로드 → 배포 → 슬롯 하나 → 바이트 비교 → 정기 켜짐 확인 → 백필 → 7일 관찰.

## 1. 로컬 테스트

```bash
cd k_tms_synthetic_train && python -m pytest -q
```

기대: B 테스트 전체 + `test_lambda_handler.py` 통과(슬롯 고르기, 자정 걸침, `_SUCCESS` 건너뛰기, 실측 경로 거부, 백필 범위, 점검, 버전 불일치 거부).

## 2. 참조 통계 업로드 (B 또는 A, 한 번)

```bash
aws s3 cp data/ref_stats.csv \
  s3://smokestack-tms-raw-952900391026/tms_synthetic_train/_ref_stats/ref-1030-1110.csv \
  --region ap-northeast-2
```

- 파일 안 `stats_version` 열이 `ref-1030-1110`이어야 한다. 덮어쓰지 않는다(바꾸려면 새 버전 이름).
- 실제 굴뚝명이 있으니 다른 곳(저장소, 채팅)에 올리지 않는다.

## 3. 배포 (사용자, PowerShell)

```powershell
cd infra/stacks/tms-synthetic
terraform init
terraform plan    # 추가만: Lambda, 역할·정책, 로그 그룹, 스케줄 2(정기·점검), 스케줄 역할, SQS, 비동기 설정, 알람
terraform apply
```

- 처음 배포 때는 스케줄을 `synthetic_schedule_enabled=false`로 꺼 둔 채 만들고 §4·§5를 확인한 뒤 켰다. 2026-11-17 운영을 시작하며 기본값을 true로 바꿨다. 새 환경에서 처음부터 다시 만들 때는 `$env:TF_VAR_synthetic_schedule_enabled = "false"`로 꺼 두고 같은 순서를 따른다.

## 4. 슬롯 하나 (US1)

contracts §2의 `{"mode":"regular"}` 실행 → 출력 `written`에 `run_ts` 1~6개.

```bash
aws s3 ls --recursive s3://smokestack-tms-raw-952900391026/tms_synthetic_train/ingest_date=$(date -u +%F)/ | tail -8
```

기대: 슬롯마다 파일 4개, `_SUCCESS` 있음.

## 5. 바이트 비교 (SC-002)

B가 로컬에서 같은 날짜를 `generate-day`로 만들고, 같은 `run_ts`의 `snapshot.json.gz`·`snapshot.meta.json`·`manifest.json` SHA-256을 S3 것과 비교한다. 같은 `ref_stats`·`daily.yaml`이어야 한다.

## 6. 정기 켜기

```powershell
$env:TF_VAR_synthetic_schedule_enabled = "true"; terraform apply
```

다음 :10 또는 :40에 폴더가 하나 늘어나는지 본다.

## 7. 백필 (US3)

contracts §2의 `backfill`을 10-30 ~ 어제로 실행(한 번에 안 되면 반으로 나눔). 이어서 `check`를 몇 날짜에 돌려 `missing`이 비었는지 본다(SC-003).

## 8. 관찰과 버전 기록

- 7일 동안 매일 06:00 점검 메일이 없고(빈 슬롯 0), DLQ 알람이 없는지 본다(SC-001).
- 실패 시험(SC-004): 참조 통계 버전을 일부러 틀리게 한 입력으로는 시험할 수 없으므로, 시험용 스케줄 입력에 `{"mode":"backfill","from":"bad"}`를 한 번 넣어 DLQ에 들어가고 알람이 오는지 확인한 뒤 메시지를 지운다.
- 버전 기록표(data-model §5)를 설정·통계를 바꿀 때마다 갱신한다.
