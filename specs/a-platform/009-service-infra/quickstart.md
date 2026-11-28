# Quickstart: 서비스 인프라 골격 (009)

A가 PowerShell에서 `de-ai-22`로 실행한다(AGENTS.md: Terraform은 사람이 적용). 각 스택 폴더에서 `terraform init` → `plan` → `apply`.

## 0. 준비 (한 번)

- 이메일 알림: `$env:TF_VAR_alert_email = "<A 이메일>"` (기존 규칙과 같음).
- 배스천 키 쌍: EC2 콘솔 → 키 페어 → 생성, 이름 `tms-bastion`, 형식 `.pem`. 파일은 로컬에만 두고 팀원에게 직접 전달한다. 저장소·공개 채널에 올리지 않는다.
- Bedrock 모델 접근 신청(콘솔, 범위 밖이지만 에이전트 시험 전에 필요).

## 1. 기반 → 도메인 위임

1. `infra/stacks/tms-foundation` apply. 출력 `name_servers` 4개를 확인한다.
2. 카페24 → 도메인 관리 → 네임서버 변경 → "다른 네임서버 사용"에 4개 입력.
3. 전파 확인(몇 시간~하루):
   ```powershell
   nslookup -type=NS smokestack-guard.store 8.8.8.8
   ```
   `awsdns`가 들어간 4개가 나오면 다음 단계.
4. Budgets 확인 메일이 오면 구독 확인은 필요 없음(Budgets는 바로 보냄). 결제 콘솔 → Budgets에서 예산 1개 확인.

## 2. 네트워크 → 화면·로그인

1. `tms-network` apply (NAT 0). 확인: VPC 1, 서브넷 6, 보안그룹 4, NAT 0.
2. `tms-serving` apply. ACM 검증 때문에 수 분 걸린다.
3. 화면은 별도 저장소 smokestack-guard-web-v2의 main push가 올린다(#94, 2026-11-28 이전은 `services/dashboard-web`).
4. 확인 (SC-001):
   - `https://smokestack-guard.store` → 빈 React 페이지, 경고 없음
   - `https://www.smokestack-guard.store`, `http://smokestack-guard.store` → 루트 https로 이동
   - `https://smokestack-guard.store/stacks/123` 새로고침 → 같은 페이지
5. Cognito 시험 계정 (SC-004):
   ```powershell
   aws cognito-idp admin-create-user --user-pool-id <풀 ID> --username <이메일>
   ```
   관리형 로그인 화면에서 임시 비밀번호로 로그인 → 새 비밀번호 요구 → 로그인 성공. 가입 링크가 없거나 가입이 거부되는지 확인.

## 3. 앱 기반 (꺼 둔 상태)

1. `tms-database` apply (`rds_enabled=false`): IAM 그룹 `tms-db-users`만 생긴다.
2. `tms-app` apply (기본값): ECR 2, ASG 2(대수 0), 배포 역할, SSM 파라미터.
3. 비용 확인 (SC-002): EC2·NAT·ALB·RDS가 0개인지 콘솔에서 확인. Cost Explorer는 하루 뒤 반영.

## 4. 배포 길 확인 (US4)

1. 최소 앱이 든 커밋을 main에 머지 → 세 워크플로가 각각 돈다.
2. 확인: ECR에 커밋 SHA 태그 이미지, `/tms/app/api/image-tag` 값이 그 SHA. 서버 0대라 배포 단계는 "대상 없음"으로 성공.
3. `services/dashboard-api`만 바꾼 PR → `dashboard-api` 워크플로만 돌고 배포 단계 없음.

## 5. 개발 구성으로 켜서 끝까지 확인 (SC-003, US5)

```powershell
cd infra/stacks/tms-network;  terraform apply -var nat_gateway_count=1
cd ../tms-database;           terraform apply -var rds_enabled=true
cd ../tms-app;                terraform apply -var alb_enabled=true -var api_desired=1 -var agent_desired=1
```

- `https://api.smokestack-guard.store/api/health`, `/agent/health` → 200 (30분 안).
- 서버 → DB: SSM 세션으로 API 서버에 들어가 `/health`가 아닌 DB 확인 경로(최소 앱의 `/api/db-check`)로 연결 확인.
- DBeaver (팀원 한 명이 직접):
  - 새 연결 → PostgreSQL
  - Main: Host = 출력 `db_host`, Port 5432, Database `tms`, Username `tms_admin`, Password = 아래 명령 결과
    ```powershell
    aws secretsmanager get-secret-value --secret-id <출력 db_secret_arn> --query SecretString --output text
    ```
  - SSH 탭: Use SSH Tunnel, Host `bastion.smokestack-guard.store`, Port 22, User `ec2-user`, 인증 Public Key, 키 파일 `tms-bastion.pem`
  - 연결 → `CREATE EXTENSION IF NOT EXISTS vector;` 성공
- 거부 확인: 키 없이 `ssh ec2-user@bastion.smokestack-guard.store` → 거부. 키로 셸 접속 시도 → 바로 끊김(터널 전용).

## 6. 다시 끄기

```powershell
cd infra/stacks/tms-app;      terraform apply      # 기본값 = 꺼 둠
cd ../tms-database;           terraform apply      # 마지막 스냅샷 남기고 삭제
cd ../tms-network;            terraform apply
```

확인: EC2·NAT·ALB·RDS 0개, RDS 스냅샷 1개 남음.

## 7. 시연 구성 (나중)

`nat_gateway_count=2`, `rds_enabled=true db_multi_az=true`, `alb_enabled=true api_desired=2 agent_desired=2`. 한쪽 AZ 서버를 멈춰도 `api.` 응답 확인 (SC-007).
