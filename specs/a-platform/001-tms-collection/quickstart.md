# Quickstart: TMS 원본 수집 인프라 배포·검증

`apply`는 사람이 실행한다. 아래 AWS CLI 명령은 모두 읽기 전용이다.

## 0. 사전 조건

- AWS 자격 증명: 팀 계정 `952900391026`의 IAM 사용자/역할 (루트 금지)
- Terraform 1.15.x (`.terraform-version`)
- SSM Parameter Store에 `/tms/collector/api-key` (표준, SecureString)를 콘솔로 등록
- 상태 버킷이 없을 때만: `infra/bootstrap`에서 `terraform init && terraform apply` (최초 1회)

## 1. 배포

```bash
cd infra/stacks/tms-collection
export TF_VAR_alert_email='<알림 받을 메일>'   # 파일에 쓰지 않는다
terraform init
terraform fmt -recursive -check ../../ && terraform validate
terraform plan -out=tfplan      # 결과를 검토한다
terraform apply tfplan          # 사람이 실행
```

- 배포 직후 SNS 구독 확인 메일의 **Confirm subscription**을 누른다. 누르지 않으면 경보 메일이 오지 않는다.

## 2. 검증 시나리오

| # | 확인 | 방법 | 기대 결과 | spec |
|---|---|---|---|---|
| V1 | 첫 수집 | 다음 10분 정각 이후 `aws s3 ls s3://smokestack-tms-raw-952900391026/tms_cleansys/ --recursive \| tail` | `snapshot.json.gz`, `snapshot.meta.json`, `_state/latest.json` 생성 | US1-1, US1-2 |
| V2 | 원문 동일성 | 스냅샷을 받아 `gunzip` 후 `sha256sum` | 메타의 `sha256_raw`와 같음 | US1-4 |
| V3 | 갱신 없음 구분 | 30분 동안 `_state/latest.json`을 10분마다 확인 | `last_checked_at`은 매번 바뀌고, `last_changed_at`은 약 30분마다 바뀜 | US1-3, US2-1 |
| V4 | 점검 결과 | 메타의 `inspect` | `ok: true`, `total_count == item_count` | FR-009 |
| V5 | 로그 | CloudWatch `/aws/lambda/tms-collector` | 요약 JSON만 있고, 응답 본문·키 없음 | FR-012, SC-005 |
| V6 | 실패 경보 | (선택) 테스트 시간대에 SSM 값을 잘못된 키로 바꿔 한 회차 실패시킨 뒤 원복 | 15분 안에 경보 메일, 정상화 후 OK 메일 | US3-1, US3-3 |
| V7 | 재현성 | 다른 환경에서 저장소를 받아 `terraform init && terraform plan` | `No changes.` | US4-1, SC-004 |

V6은 그 회차의 데이터를 잃으므로, 꼭 필요할 때만 B와 합의한 시간에 한다.

## 3. 일상 운영 확인

```bash
aws s3 cp s3://smokestack-tms-raw-952900391026/tms_cleansys/_state/latest.json - | jq
```

판단 기준은 [data-model.md](data-model.md)의 "판단 기준" 표를 따른다.
