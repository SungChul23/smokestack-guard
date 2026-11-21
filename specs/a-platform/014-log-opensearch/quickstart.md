# Quickstart: 서비스 로그 수집·분석 적용·확인

AWS 명령과 Terraform은 A가 실행한다.

## 1. 로그 양 확인 (비용 재계산, R7)

```bash
aws logs describe-log-groups --region ap-northeast-2 \
  --query "logGroups[?starts_with(logGroupName,'/tms/app/') || starts_with(logGroupName,'/aws/lambda/tms-')].[logGroupName,storedBytes,retentionInDays]" --output table
```
저장 바이트 ÷ 보관 일수 ≈ 하루 양. 합이 하루 100MB를 크게 넘으면 plan의 디스크·보관을 다시 본다.

## 2. 엔진 버전 확인

```bash
aws opensearch list-versions --region ap-northeast-2 --query "Versions[?starts_with(@,'OpenSearch_2')]" --output text
```
가장 높은 2.x를 `engine_version` 변수 기본값과 맞춘다.

## 3. Terraform

```powershell
cd infra/stacks/tms-log-search; terraform init; terraform plan; terraform apply   # 도메인 생성 15~30분
```
생기는 것: 도메인 `tms-logs`, 자격 증명 풀·역할, Firehose 3개, 라우터 Lambda, 실패분 버킷, 구독 필터 9개(서버 2·Lambda 6·Glue 1), EventBridge 규칙 1개.

## 4. Cognito 앱 클라이언트에 Google 더하기 (R2 수동 단계)

```bash
POOL=$(aws ssm get-parameter --name /tms/app/config/cognito-user-pool-id --query Parameter.Value --output text)
aws cognito-idp list-user-pool-clients --user-pool-id $POOL --query "UserPoolClients[?starts_with(ClientName,'AWSElasticsearch')].ClientId" --output text
# 그 클라이언트의 현재 설정을 읽어 SupportedIdentityProviders에 Google을 더한다(명령은 tasks에서)
```

## 5. 초기 설정 (인덱스 템플릿·ISM·역할 매핑·알림·대시보드)

```bash
cd services/log-search
python setup_opensearch.py --dry-run     # 적용할 것만 출력
python setup_opensearch.py               # 멱등. 도메인을 다시 만들면 다시 실행
```

## 6. 확인 시나리오

| # | 할 일 | 기대 |
|---|---|---|
| 1 | 화면에서 로그인·몇 페이지 이동 | 5분 안에 `logs-app-*`에 요청 기록, `activity-*`에 `session` (SC-001) |
| 2 | 다음 10분 수집 실행 | `logs-pipeline-*`에 `tms-collector` 요약 줄 |
| 3 | Dashboards 주소 → Google 로그인(`members`) | `운영 상태`·`사용 현황` 대시보드가 채워짐 (SC-003, SC-009) |
| 4 | `members`가 아닌 계정 | Dashboards 접근 거부 |
| 5 | 인증 없이 도메인 주소 호출 | 403 (FR-012) |
| 6 | 서버에서 오류 10번(시험 경로) | 10분 안에 운영 메일 (SC-004) |
| 7 | `activity-*` 검색: 이메일·코드 문자열 | 0건 (FR-021) |
| 8 | 하루 뒤 누락률 리포트 | 이전과 같음 (SC-008) |

## 7. 끄기 (시연 뒤)

```powershell
cd infra/stacks/tms-log-search; $env:TF_VAR_opensearch_enabled="false"; terraform apply
```
도메인·Firehose·구독 필터가 지워진다. CloudWatch 원본, 실패분 버킷, 서비스는 그대로.
