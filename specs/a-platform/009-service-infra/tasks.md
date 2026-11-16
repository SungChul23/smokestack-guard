---
description: "Task list for 009 service infra skeleton"
---

# Tasks: 대시보드·에이전트 서비스 인프라 골격

**Input**: `specs/a-platform/009-service-infra/` (spec.md, plan.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: 별도 테스트 작업은 두지 않는다(spec이 TDD를 요구하지 않음). 검증은 `terraform fmt -check`·`validate`(에이전트), `plan`·`apply`와 quickstart 확인(A), 최소 앱의 pytest·빌드(CI)로 한다.

**적용 규칙**: AI 에이전트는 `terraform fmt`·`validate`까지만 한다. **[A]** 표시는 사람(A)이 PowerShell에서 `de-ai-22`로 하는 작업이다(`plan`·`apply`, 콘솔 작업, 확인).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 다른 파일, 앞선 미완료 작업에 기대지 않음 → 병렬 가능
- **[Story]**: US1~US5 (spec.md)

---

## Phase 1: Setup

**Purpose**: 새 스택 5개의 뼈대와 리뷰어 설정

- [x] T001 [P] `infra/stacks/tms-foundation/`에 `backend.tf`(키 `stacks/tms-foundation/terraform.tfstate`, AGENTS.md 형식 그대로), `versions.tf`(`~> 1.15.0`, aws `~> 6.0`, region `ap-northeast-2`, default_tags `project=tms, managed_by=terraform, stack=tms-foundation`), 빈 `variables.tf`·`main.tf`·`outputs.tf` 만들기
- [x] T002 [P] `infra/stacks/tms-network/`에 T001과 같은 뼈대(stack=`tms-network`)
- [x] T003 [P] `infra/stacks/tms-serving/`에 T001과 같은 뼈대(stack=`tms-serving`) + `versions.tf`에 `provider "aws" { alias = "us_east_1", region = "us-east-1" }`(같은 default_tags)
- [x] T004 [P] `infra/stacks/tms-database/`에 T001과 같은 뼈대(stack=`tms-database`)
- [x] T005 [P] `infra/stacks/tms-app/`에 T001과 같은 뼈대(stack=`tms-app`)
- [x] T006 [P] `.github/CODEOWNERS`에 `/infra/stacks/tms-foundation/`·`tms-network/`·`tms-serving/`·`tms-database/`·`tms-app/` → `@SungChul23`, `/services/dashboard-api/`·`dashboard-agent/`·`dashboard-web/` → `@jaeyan42 @SungChul23` 추가

---

## Phase 2: Foundational (모든 스토리 전제)

**Purpose**: 도메인 위임과 네트워크. 끝나야 화면·서버·DB를 만들 수 있다.

### tms-foundation (research R1, R12)

- [x] T007 `infra/stacks/tms-foundation/main.tf`에 `aws_route53_zone` `smokestack-guard.store`(`lifecycle { prevent_destroy = true }`), `outputs.tf`에 `name_servers`, `zone_id`
- [x] T008 `infra/stacks/tms-foundation/main.tf`에 `aws_iam_openid_connect_provider` `token.actions.githubusercontent.com`(client_id `sts.amazonaws.com`), output `github_oidc_provider_arn`
- [x] T009 `infra/stacks/tms-foundation/variables.tf`에 `alert_email`(sensitive, 기존 `tms-collection`과 같은 설명 형식), `monthly_budget_usd`(기본 200); `main.tf`에 `aws_budgets_budget`(COST, MONTHLY, `cost_types { include_credit = false }`, 알림: ACTUAL 25%·50%·75%, FORECASTED 100%, 이메일 `var.alert_email`)
- [x] T010 `terraform fmt -recursive`·`validate` (`infra/stacks/tms-foundation/`)
- [ ] T011 [A] `tms-foundation` plan·apply → 출력 NS 4개를 카페24 "다른 네임서버 사용"에 입력 → `nslookup -type=NS smokestack-guard.store 8.8.8.8`에 `awsdns` 4개가 보일 때까지 대기 (quickstart §1)

### tms-network (data-model §2·§3, research R3)

- [x] T012 `infra/stacks/tms-network/main.tf`에 VPC `10.20.0.0/16`(DNS hostnames·support 켬, `Name=tms-vpc`), 서브넷 6개(data-model §2의 이름·AZ·CIDR 그대로, 퍼블릭은 `map_public_ip_on_launch = true`), IGW, 퍼블릭 라우팅 테이블(0.0.0.0/0 → IGW)
- [x] T013 `infra/stacks/tms-network/variables.tf`에 `nat_gateway_count`(number, 기본 0, validation `contains([0,1,2], ...)`); `main.tf`에 EIP+NAT `count = var.nat_gateway_count`(퍼블릭 a, c 순), 앱 라우팅 테이블 AZ별 2개: NAT 2면 자기 AZ, 1이면 둘 다 NAT[0], 0이면 기본 경로 없음; DB 라우팅 테이블 1개(기본 경로 없음); S3 게이트웨이 엔드포인트를 앱·DB 라우팅 테이블에 연결
- [x] T014 `infra/stacks/tms-network/security_groups.tf`에 보안그룹 `tms-alb`·`tms-app`·`tms-bastion`·`tms-db`와 규칙(data-model §3 표 그대로: alb 443·80 ← 0.0.0.0/0, alb → app 8000; app 8000 ← alb, app → 443 0.0.0.0/0, app → db 5432; bastion 22 ← `var.bastion_ssh_cidrs`, bastion → 443 0.0.0.0/0, bastion → db 5432; db 5432 ← app, db 5432 ← bastion). `aws_vpc_security_group_ingress_rule`/`egress_rule`로 규칙마다 description. `variables.tf`에 `bastion_ssh_cidrs`(list(string), 기본 `["0.0.0.0/0"]`)
- [x] T015 `infra/stacks/tms-network/outputs.tf`에 vpc_id, 서브넷 ID(퍼블릭·앱·DB), 보안그룹 ID 4개, `nat_gateway_count`
- [x] T016 `fmt`·`validate` (`infra/stacks/tms-network/`)
- [ ] T017 [A] `tms-network` plan·apply(기본값) → VPC 1, 서브넷 6, 보안그룹 4, NAT 0 확인

**Checkpoint**: 도메인 위임 완료 + 네트워크 존재

---

## Phase 3: User Story 1 - 자기 도메인 https 주소로 화면이 열린다 (P1) 🎯 MVP

**Goal**: `https://smokestack-guard.store`(www, http 포함)에서 빈 React 페이지

**Independent Test**: quickstart §2의 1~4 (SC-001)

- [x] T018 [US1] `infra/stacks/tms-serving/certificates.tf`: `data "aws_route53_zone"`(이름), ACM `us-east-1`(provider 별칭) `smokestack-guard.store` + SAN `www.smokestack-guard.store`, ACM 서울 `api.smokestack-guard.store`, 두 인증서의 DNS 검증 레코드(`for_each` domain_validation_options, `allow_overwrite = true`)와 `aws_acm_certificate_validation`
- [x] T019 [US1] `infra/stacks/tms-serving/web.tf`: S3 버킷 `smokestack-tms-web-952900391026`(퍼블릭 액세스 전부 차단, 버전 관리 끔, SSE-S3), OAC, 버킷 정책(이 배포의 `cloudfront.amazonaws.com`만 `s3:GetObject`)
- [x] T020 [US1] `infra/stacks/tms-serving/web.tf`: 원본 `Cache-Control`을 따르는 캐시 정책(min_ttl 0, default 86400, max 31536000, gzip·brotli), CloudFront Function `tms-www-redirect`(viewer-request, Host가 `www.`이면 `https://smokestack-guard.store` + 경로로 301)
- [x] T021 [US1] `infra/stacks/tms-serving/web.tf`: CloudFront 배포(별칭 루트·www, us-east-1 인증서, `redirect-to-https`, 기본 루트 객체 `index.html`, `custom_error_response` 403·404 → `/index.html` 200, `PriceClass_200`, 함수 연결, IPv6)
- [x] T022 [US1] `infra/stacks/tms-serving/web.tf`: Route 53 A·AAAA 별칭 루트·www → 배포; SSM 파라미터 `/tms/app/config/web-bucket`, `/tms/app/config/web-distribution-id`(String)
- [x] T023 [P] [US1] `services/dashboard-web/`: Vite + React 최소 앱(`package.json`, `vite.config.ts`, `index.html`, `src/main.tsx`, `src/App.tsx`에 "smokestack-guard" 제목만), 빌드 결과물 이름에 해시(Vite 기본), `README.md`에 로컬 실행·빌드 방법과 "D가 이어서 개발" 안내, `.gitignore`(node_modules, dist)
- [x] T024 [US1] `infra/stacks/tms-serving/outputs.tf`: web_bucket, distribution_id, distribution_domain; `fmt`·`validate`
- [ ] T025 [US1] [A] `tms-serving` plan·apply → `services/dashboard-web` 빌드 후 `aws s3 sync dist s3://smokestack-tms-web-952900391026/`(index.html은 `--cache-control no-cache`) → quickstart §2의 4번 확인

**Checkpoint**: 화면 주소 동작 (MVP)

---

## Phase 4: User Story 2 - 꺼 둔 상태로 비용이 거의 없고, 변수만 바꿔 켜고 끈다 (P1)

**Goal**: 기본값 = 시간당 자원 0, 개발 구성으로 켜서 `api.` → 서버 → DB 확인 후 끔

**Independent Test**: quickstart §3, §5(DBeaver 제외), §6 (SC-002, SC-003)

### DB (tms-database, research R9)

- [x] T026 [US2] `infra/stacks/tms-database/variables.tf`: `rds_enabled`(bool, false), `db_multi_az`(bool, false), `db_restore_snapshot_id`(string, ""), `db_instance_class`(기본 `db.t4g.micro`)
- [x] T027 [US2] `infra/stacks/tms-database/main.tf`: data 소스로 DB 서브넷(`tms-db-a/c`)·보안그룹(`tms-db`); `aws_db_subnet_group` `tms-db`(항상); `aws_db_instance` `tms-db`(`count = var.rds_enabled ? 1 : 0`, engine postgres 16 최신 마이너, `db_name = "tms"`, `username = "tms_admin"`, `manage_master_user_password = true`, gp3 20GB, `publicly_accessible = false`, `multi_az = var.db_multi_az`, `backup_retention_period = 1`, `skip_final_snapshot = false`, `final_snapshot_identifier = "tms-db-final-${formatdate("YYYYMMDDhhmm", timestamp())}"` + `lifecycle { ignore_changes = [final_snapshot_identifier, snapshot_identifier] }`, `snapshot_identifier = var.db_restore_snapshot_id != "" ? var.db_restore_snapshot_id : null`, `deletion_protection = false`, `apply_immediately = true`)
- [x] T028 [US2] `infra/stacks/tms-database/main.tf`: 관리형 비밀에 `aws_secretsmanager_secret_rotation`(`rotation_rules { automatically_after_days = 30 }`, 람다 없음, DB와 같은 count). `validate`에서 거부되면 리소스를 빼고 quickstart §5에 `aws secretsmanager rotate-secret --secret-id <arn> --rotation-rules AutomaticallyAfterDays=30` 1회 실행을 적는다 (research R9)
- [x] T029 [US2] `infra/stacks/tms-database/main.tf`: SSM 파라미터 `/tms/app/config/db-host`(엔드포인트 주소), `/tms/app/config/db-secret-arn`(DB와 같은 count); `outputs.tf`에 `db_host`, `db_secret_arn`(없으면 null)
- [x] T030 [US2] `fmt`·`validate` (`infra/stacks/tms-database/`)

### 서버·ALB (tms-app, research R4·R5·R13·R14)

- [x] T031 [P] [US2] `services/dashboard-api/`: FastAPI 최소 앱 `app/main.py`(`GET /health`, `GET /api/health` → `{"status":"ok"}`, `GET /api/db-check` → contracts/app-runtime.md의 `DB_HOST`·`DB_SECRET_ARN`으로 Secrets Manager에서 비밀번호를 읽어 `SELECT 1`, DB 설정이 없으면 503), `pyproject.toml`(fastapi, uvicorn, boto3, psycopg[binary]; dev: pytest, httpx, ruff), `Dockerfile`(python:3.11-slim, 포트 8000, `uvicorn app.main:app --host 0.0.0.0 --port 8000`), `tests/test_health.py`, `README.md`(계약 링크)
- [x] T032 [P] [US2] `services/dashboard-agent/`: 같은 구조, `GET /health`, `GET /agent/health`만(boto3·psycopg 없음)
- [x] T033 [US2] `infra/stacks/tms-app/ecr.tf`: ECR `tms-dashboard-api`, `tms-dashboard-agent`(IMMUTABLE, scan_on_push, 수명 주기 "최근 10개 유지")
- [x] T034 [US2] `infra/stacks/tms-app/main.tf`: 로그 그룹 `/tms/app/api`, `/tms/app/agent`(14일); SSM 파라미터 `/tms/app/api/image-tag`, `/tms/app/agent/image-tag`(String, `none`, `lifecycle { ignore_changes = [value] }`)
- [x] T035 [US2] `infra/stacks/tms-app/iam.tf`: 역할 `tms-app-server` + 인스턴스 프로파일, 정책은 data-model §5 표 그대로(SSM 관리형 정책, ECR pull 두 저장소 + `GetAuthorizationToken`, `ssm:GetParameter(s)` `/tms/app/*`, `secretsmanager:GetSecretValue` 이름 접두사 `rds!db-*`, 두 로그 그룹 쓰기, `bedrock:InvokeModel`·`InvokeModelWithResponseStream`)
- [x] T036 [US2] `infra/stacks/tms-app/server-user-data.sh`(templatefile, 변수 `app`): dnf로 docker 설치·시작, 스왑 2GB, `/opt/tms/deploy.sh` 작성(① `/tms/app/${app}/image-tag` 읽기, `none`이면 종료 ② `/tms/app/config/*` 읽어 contracts/app-runtime.md의 환경 변수 구성, 없는 값은 비움 ③ ECR 로그인 ④ 기존 컨테이너 중지 후 `docker run -d --name ${app} --restart always -p 8000:8000 --log-driver awslogs --log-opt awslogs-group=/tms/app/${app} ...`) 후 실행
- [x] T037 [US2] `infra/stacks/tms-app/main.tf`: AMI는 `data "aws_ssm_parameter"` `/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64`; 시작 템플릿 `tms-api`·`tms-agent`(유형 변수, 프로파일, `tms-app` 보안그룹, IMDSv2 필수, gp3 20GB, user data T036, 인스턴스 태그 `tms:app`)
- [x] T038 [US2] `infra/stacks/tms-app/variables.tf`: `alb_enabled`(false), `api_desired`·`agent_desired`(0, validation 0~2), `api_instance_type`·`agent_instance_type`(`t3.small`); `main.tf`: ASG `tms-api`·`tms-agent`(앱 서브넷 2개, min=max=desired=변수, `health_check_type = "EC2"`, `target_group_arns`는 ALB가 켜졌을 때만), `data "aws_nat_gateways"`(vpc, state available) + ASG `lifecycle { precondition { condition = var.<app>_desired == 0 || length(data.aws_nat_gateways.this.ids) > 0, error_message = "NAT가 없어 서버가 이미지를 받을 수 없다. tms-network에서 nat_gateway_count를 1 이상으로 먼저 적용하라." } }`
- [x] T039 [US2] `infra/stacks/tms-app/alb.tf`(`count = var.alb_enabled ? 1 : 0`): ALB(퍼블릭 서브넷 2, `tms-alb` 보안그룹, idle_timeout 120), 대상 그룹 api·agent(포트 8000, HTTP, 상태 확인 `/health`, deregistration_delay 30), 리스너 80 → 443 리디렉션, 리스너 443(data 소스로 찾은 서울 `api.` 인증서, 기본 404 고정 응답), 규칙 `/api/*` → api, `/agent/*` → agent, Route 53 `api.` A 별칭
- [x] T040 [US2] `infra/stacks/tms-app/outputs.tf`: ECR URL 2, ASG 이름 2, alb_dns(없으면 null); `fmt`·`validate`
- [ ] T041 [US2] [A] `tms-database`(기본값) → `tms-app`(기본값) apply, 시간당 자원 0개 확인 (quickstart §3)
- [ ] T042 [US2] [A] 처음 이미지 1회 수동 올리기(US4 전에 확인할 때): `services/dashboard-api`·`dashboard-agent`를 `docker build --platform linux/amd64` → ECR push(태그 `manual-1`) → `/tms/app/<앱>/image-tag`를 `manual-1`로
- [ ] T043 [US2] [A] 개발 구성으로 켜기 → `api.`의 `/api/health`·`/agent/health`·`/api/db-check` 200 확인 → 꺼 둠으로 되돌리고 RDS 마지막 스냅샷 1개 확인 (quickstart §5·§6)

**Checkpoint**: 켜기·끄기 확인 완료

---

## Phase 5: User Story 3 - 관리자가 만든 계정으로만 로그인 (P2)

**Goal**: 관리형 로그인으로 관리자 생성 계정만 로그인

**Independent Test**: quickstart §2의 5 (SC-004)

- [x] T044 [US3] `infra/stacks/tms-serving/auth.tf`: 사용자 풀 `tms-users`(`admin_create_user_config { allow_admin_create_user_only = true }`, 사용자 이름 = 이메일, 이메일 자동 확인, MFA 끔), 도메인 접두사 `smokestack-guard`, 앱 클라이언트 `tms-web`(비밀 없음, `allowed_oauth_flows = ["code"]`, scopes `openid email profile`, 콜백·로그아웃 `https://smokestack-guard.store/`, `http://localhost:5173/`, `supported_identity_providers = ["COGNITO"]`)
- [x] T045 [US3] `infra/stacks/tms-serving/auth.tf`: SSM 파라미터 `/tms/app/config/cognito-user-pool-id`, `cognito-client-id`, `cognito-domain`; outputs 같은 값; `fmt`·`validate`
- [ ] T046 [US3] [A] `tms-serving` apply → `admin-create-user`로 시험 계정 → 로그인·비밀번호 변경 확인, 가입 거부 확인

---

## Phase 6: User Story 4 - 폴더별 main 머지 배포 (P2)

**Goal**: `services/dashboard-*` 중 바뀐 폴더만 배포

**Independent Test**: quickstart §4 (SC-005)

- [x] T047 [US4] `infra/stacks/tms-app/deploy_role.tf`: data 소스로 OIDC 공급자, 역할 `tms-github-deploy`(신뢰 조건 contracts/deploy-pipeline.md 그대로: `aud = sts.amazonaws.com`, `sub = repo:SungChul23/smokestack-guard:ref:refs/heads/main`), 권한은 contracts/deploy-pipeline.md 목록 그대로(SendCommand는 `ssm:resourceTag/tms:app` 조건, S3·CloudFront는 SSM 파라미터가 아니라 data 소스로 찾은 버킷·배포 ARN); output `github_deploy_role_arn`; `fmt`·`validate`
- [x] T048 [P] [US4] `.github/workflows/dashboard-api.yml`: paths `services/dashboard-api/**` + 자기 파일; `pull_request` → ruff·pytest·`docker build`; `push` main → `permissions: id-token: write, contents: read`, `aws-actions/configure-aws-credentials`(역할 ARN은 워크플로에 상수, 리전 ap-northeast-2) → ECR 로그인 → build·push `:${{ github.sha }}` → `aws ssm put-parameter --overwrite /tms/app/api/image-tag` → `describe-instances`(태그 `tms:app=api`, running) 개수 0이면 종료 → `send-command`(`AWS-RunShellScript`, `/opt/tms/deploy.sh`, 태그 대상) 후 완료 대기·실패 시 실패
- [x] T049 [P] [US4] `.github/workflows/dashboard-agent.yml`: T048과 같고 `agent`
- [x] T050 [P] [US4] `.github/workflows/dashboard-web.yml`: `pull_request` → `npm ci && npm run build`; `push` main → OIDC → build → `aws s3 sync dist s3://<버킷> --delete --exclude index.html --cache-control "max-age=31536000, immutable"` → `index.html`을 `--cache-control no-cache`로 복사 → `create-invalidation --paths /index.html`
- [ ] T051 [US4] [A] `tms-app` apply(배포 역할) → 세 폴더 최소 앱이 든 브랜치를 main에 머지 → quickstart §4 확인

---

## Phase 7: User Story 5 - 팀원이 공용 pem으로 DBeaver 접속 (P3)

**Goal**: DB를 켜면 배스천도 뜨고, 팀원이 DBeaver SSH 터널로 관리자 계정 접속

**Independent Test**: quickstart §5의 DBeaver 항목 (A가 아닌 팀원 한 명)

- [ ] T052 [US5] [A] EC2 콘솔에서 키 쌍 `tms-bastion`(.pem) 생성, 로컬 보관(저장소·공개 채널 금지), 팀원에게 직접 전달
- [x] T053 [US5] `infra/stacks/tms-database/bastion-user-data.sh`(templatefile, 변수 `db_host`): `/etc/ssh/sshd_config.d/90-tms.conf`에 `PasswordAuthentication no`, `X11Forwarding no`, `Match User ec2-user` → `PermitOpen ${db_host}:5432`, `AllowTcpForwarding local`, `ForceCommand /sbin/nologin`, `PermitTTY no` 작성 후 `systemctl restart sshd`
- [x] T054 [US5] `infra/stacks/tms-database/bastion.tf`(`count = var.rds_enabled ? 1 : 0`): 변수 `bastion_key_name`(기본 `tms-bastion`); 역할 `tms-bastion`(SSM 관리형 정책) + 프로파일; 인스턴스 t3.micro(AL2023 x86 SSM AMI, 퍼블릭 서브넷 `tms-public-a`, `tms-bastion` 보안그룹, 공인 IP, IMDSv2, user data T053); Route 53 A `bastion.smokestack-guard.store` → 공인 IP, TTL 60
- [x] T055 [US5] `infra/stacks/tms-database/access.tf`: 변수 `db_user_names`(기본 `["de-ai-05","de-ai-08","de-ai-11","de-ai-14","de-ai-22","tms_mentor"]`), IAM 그룹 `tms-db-users`, `aws_iam_group_membership`, 그룹 정책(DB와 같은 count): 관리형 DB 비밀 1개 `GetSecretValue`·`DescribeSecret`, `rds:DescribeDBInstances`; `fmt`·`validate`
- [x] T056 [US5] `infra/stacks/tms-database/README.md`: 팀원용 접속 안내(준비물: DBeaver, pem; 비밀번호 읽기 명령; DBeaver Main·SSH 탭 값; 셸 접속은 막혀 있음; 비밀번호 30일 교체·DB 재생성 시 비밀번호만 다시 입력; 배스천 주소·DB 주소는 고정)
- [ ] T057 [US5] [A] 개발 구성으로 DB 켜기 → 팀원 한 명이 README대로 접속, `CREATE EXTENSION IF NOT EXISTS vector;` 성공, 키 없는 SSH 거부·키로 셸 시도 시 끊김 확인 → 끄기

---

## Phase 8: Polish & Cross-Cutting

- [x] T058 `terraform fmt -recursive -check` 전체 + 5개 스택 `validate`, `.terraform.lock.hcl` 커밋 대상 확인
- [x] T059 [P] `infra/stacks/README.md`(없으면 생략) 또는 각 스택 상단 주석에 역할·적용 순서(plan "적용 순서와 의존") 한 줄씩
- [ ] T060 `AGENTS.md` 저장소 구조에 새 스택 5개와 `services/dashboard-*` 3개 추가 (#46 머지 뒤, 충돌 확인)
- [ ] T061 `specs/a-platform/009-service-infra/spec.md` Status를 결과에 맞게 갱신, quickstart 확인 결과(날짜) 기록

---

## Dependencies & Execution Order

- **Phase 1** → **Phase 2**(T011 NS 전파가 가장 긴 대기) → 스토리
- **US1**(T018~T025): Phase 2 뒤 바로. ACM 검증에 NS 위임 필요
- **US3**(T044~T046): `tms-serving` 파일만 다름 → US1과 같은 apply로 묶어도 됨
- **US2**(T026~T043): Phase 2 뒤. T039는 T018(서울 인증서) 필요
- **US4**(T047~T051): T033·T034(ECR·image-tag)와 T008(OIDC 공급자), T019·T021(버킷·배포) 필요
- **US5**(T052~T057): T027(DB) 필요. 같은 `tms-database` 스택
- **Polish**: 모든 스토리 뒤. T060은 #46 머지 뒤

## Parallel Example

```text
Phase 1: T001~T006 모두 동시
US2:   T031(api 앱) ∥ T032(agent 앱) ∥ T026~T029(DB)
US4:   T048 ∥ T049 ∥ T050 (워크플로 3개)
US1:   T023(web 앱) ∥ T018~T022(tms-serving)
```

## Implementation Strategy

1. **MVP**: Phase 1 → Phase 2 → US1. 도메인 위임과 https 화면이 가장 오래 걸리고(전파 대기) 나머지의 전제다. T011을 가장 먼저 시작한다.
2. NS 전파를 기다리는 동안 US2·US4의 코드(T026~T040, T047~T050)를 만든다(apply는 뒤에).
3. 꺼 둔 상태로 모두 apply(T041) → 배포 길(US4) → 개발 구성 한 번 켜서 US2·US5 확인 → 끔.
4. 커밋은 작업 단위로 나눈다(스택별, 앱별, 워크플로, 문서).
