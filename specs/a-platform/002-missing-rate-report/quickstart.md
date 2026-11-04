# Quickstart: 누락률 리포트 배포·검증

`apply`는 사람이 실행한다.

## 0. 사전 조건

- 001 스택이 배포되어 원본이 쌓이고 있을 것
- SNS 이메일 구독이 확인(Confirm)된 상태일 것

## 1. 배포 전 관문: 수집기 변경 없음 확인

```bash
cd infra/stacks/tms-collection
export TF_VAR_alert_email='<알림 받을 메일>'
terraform init
terraform fmt -recursive -check ../../ && terraform validate
terraform plan -out=tfplan
terraform show -no-color tfplan | grep -E '^\s+# module\.collector' || echo "module.collector 변경 없음"
```

- **`module.collector`에 변경이 하나라도 있으면 apply하지 않는다.** (원칙 I)
- 기대 결과: `module.missing_rate`의 리소스만 추가 (Lambda, 역할 2, 정책 2, 로그 그룹, 스케줄, 알람, event invoke config)

## 2. 배포

```bash
terraform apply tfplan   # 사람이 실행
```

## 3. 검증 시나리오

| # | 확인 | 방법 | 기대 결과 | spec |
|---|---|---|---|---|
| V1 | 백필 동작 | [invoke-event.md](contracts/invoke-event.md)의 수동 호출로 001 배포일 ~ 어제 계산 | 날짜마다 `reports/missing_rate/date=…/report.json` 생성, 메일 없음 | US2-1, US3-1, US3-2 |
| V2 | 리포트 형식 | 리포트 하나를 [report.schema.json](contracts/report.schema.json)과 대조 | 필드 모두 존재 | US2-2 |
| V3 | 알려진 누락 일치 | 001 배포 당일(배포 전 시간대는 수집 없음) 리포트 확인 | 배포 전 슬롯이 정확히 누락 목록에 있음 | SC-002 |
| V4 | 누락 없는 날 | 정상 운영된 날 리포트 | `missing_count: 0` | SC-003 |
| V5 | 자동 실행 | 다음 날 09:00 이후 로그 그룹 `/aws/lambda/tms-missing-rate` | 요약 로그 1건, 리포트 생성 | US1-1, SC-001 |
| V6 | 누락 알림 | 누락이 있는 날짜에 자동 실행 경로를 시험하려면, Lambda 콘솔에서 `{}`로 테스트 호출 (어제 누락이 있을 때만 메일) | [alert-message.md](contracts/alert-message.md) 형식 메일 | US1-2 |
| V7 | 원본 불변 | 배포 전후 `aws s3 ls …/tms_cleansys/ --recursive \| wc -l` 비교 (수집 증가분 제외) | 리포트 작업으로 생긴 객체 없음 | SC-006 |
| V8 | 권한 분리 | IAM 콘솔에서 `tms-missing-rate-lambda` 정책 확인 | SSM·KMS 없음, PutObject는 `reports/missing_rate/*`만 | FR-013 |

## 4. 일상 운영

```bash
aws s3 cp s3://smokestack-tms-raw-952900391026/reports/missing_rate/date=$(date -d yesterday +%F)/report.json - | jq '.slots'
```
