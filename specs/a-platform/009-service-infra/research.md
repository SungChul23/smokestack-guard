# Research: 서비스 인프라 골격 (009)

spec의 기본값과 열린 항목을 구현 결정으로 바꾼 기록이다. 형식: 결정 / 이유 / 버린 대안.

## R1. 스택 나누기와 적용 순서

- **결정**: 5개 스택. `tms-foundation` → (카페24 NS 변경, 전파 대기) → `tms-network` → `tms-serving` → `tms-database` → `tms-app`.

  | 스택 | 담는 것 | 지우는가 |
  |---|---|---|
  | `tms-foundation` | Route 53 호스팅 영역, AWS Budgets, GitHub OIDC 공급자(계정에 1개) | 지우지 않는다 |
  | `tms-network` | VPC, 서브넷 6, IGW, 라우팅, NAT(0~2), S3 게이트웨이 엔드포인트, **보안그룹 4개 전부** | 거의 안 지움. NAT만 변수로 켜고 끔 |
  | `tms-serving` | ACM 2개(us-east-1, 서울), 화면 S3 + CloudFront + 루트·www 레코드, Cognito | 안 지움 |
  | `tms-database` | RDS, 비밀번호 교체, 배스천 + `bastion.` 레코드, DB 비밀 읽기 IAM 그룹, DB 설정 SSM 파라미터 | `rds_enabled`로 켜고 끔 |
  | `tms-app` | ECR 2, 서버 IAM 역할, 시작 템플릿, ASG 2, ALB + `api.` 레코드, 배포 역할, 앱 SSM 파라미터, 로그 그룹 | ALB·ASG 대수를 변수로 켜고 끔 |

- **이유**: spec의 `tms-dns`는 "지우지 않는 작은 스택"이 목적이었다. 같은 성격(계정에 하나, 오래 둠)인 Budgets와 GitHub OIDC 공급자를 같이 두면 스택 수를 늘리지 않는다. 이름은 하는 일 기준(AGENTS.md)으로 `tms-foundation`. 보안그룹은 서로를 출발지로 참조하므로 한 스택(`tms-network`)에 모은다. 켜고 끄는 단위(DB+배스천, ALB+서버)를 각각 한 스택에 두어 적용 범위를 좁힌다.
- **버린 대안**: 스택 1개(켜고 끌 때마다 전부 plan, 실수 범위 큼). `tms-dns`만 따로 + Budgets를 다른 스택에(지우는 스택에 두면 알림도 사라짐).

## R2. 스택 사이 값 전달

- **결정**: `terraform_remote_state`를 쓰지 않고 data 소스로 찾는다(이름·태그). VPC·서브넷·보안그룹은 `Name` 태그, 호스팅 영역은 도메인 이름, 인증서는 도메인 이름, DB 설정은 SSM 파라미터.
- **이유**: 기존 스택(`tms-eda`, `tms-silver`)이 `data "aws_s3_bucket"`으로 원본 버킷을 찾는 방식과 같다. 상태 파일 구조에 묶이지 않는다.
- **버린 대안**: 원격 상태(스택 출력 이름을 바꾸면 깨짐, 읽기 권한이 상태 버킷 전체로 넓어짐).

## R3. NAT와 라우팅

- **결정**: 앱 서브넷 라우팅 테이블을 AZ마다 하나 둔다. `nat_gateway_count`가 2면 각자 자기 AZ NAT, 1이면 둘 다 AZ-a NAT, 0이면 기본 경로 없음. DB 서브넷은 기본 경로 없음. S3 게이트웨이 엔드포인트는 앱·DB 라우팅 테이블에 붙인다.
- **이유**: spec FR-004. 개발 구성에서 NAT 1개로 비용을 절반으로 줄인다.
- **보호 장치**: `tms-app`의 ASG에 precondition: 원하는 대수 > 0인데 VPC에 사용 가능한 NAT가 0개면 plan이 실패하며 이유를 출력한다(spec 예외 "NAT 없이 서버만 켜기").

## R4. 인스턴스 유형과 무료 플랜

- **결정**: 서버 `t3.small`(x86, API·에이전트 각각 변수), 배스천 `t3.micro`, DB `db.t4g.micro`.
- **이유**: 2025-07-15 이후 계정의 무료 플랜 대상에 t3.micro·t3.small이 있다(크레딧 차감). 새 무료 플랜에서 nano를 못 쓴다는 보고가 있어 배스천은 micro. x86이면 이미지를 ARM으로 따로 빌드하지 않아도 된다. 에이전트는 Bedrock을 API로만 부르므로 2GB + 스왑 2GB로 시작하고, 부족하면 변수만 `t3.medium`으로.
- **버린 대안**: t4g(ARM): 더 싸지만 이미지 다중 아키텍처 빌드와 일부 파이썬 패키지 문제.

## R5. 서버가 뜨는 방식

- **결정**: Amazon Linux 2023(최신 AMI는 공개 SSM 파라미터로 찾음) + 사용자 데이터:
  1. Docker 설치, 스왑 2GB.
  2. `/tms/app/<앱>/image-tag` 파라미터를 읽어 값이 `none`이면 아무것도 띄우지 않고 끝낸다.
  3. ECR 로그인 → 이미지 pull → 컨테이너 실행(포트 8000, 재시작 정책 always, 로그는 CloudWatch `awslogs` 드라이버).
  4. 같은 일을 하는 `/opt/tms/deploy.sh`를 남겨 배포 때 재사용한다.
  - 환경 변수는 SSM 파라미터 경로 `/tms/app/config/*`에서 읽어 넣는다(계약: [contracts/app-runtime.md](contracts/app-runtime.md)).
- **ASG 상태 확인**: `EC2`(인스턴스 상태)만 쓴다. ALB 상태 확인은 라우팅에만 쓴다.
- **이유**: 이미지가 아직 없거나(`none`) 앱이 잠깐 죽었을 때 ALB 상태 확인으로 ASG가 인스턴스를 계속 갈아 끼우는 반복을 막는다. 대수가 작아(1~2) 자동 교체보다 안정이 중요하다.
- **버린 대안**: ECS(Fargate/EC2): 더 관리형이지만 팀이 정한 "EC2 + ASG" 구성과 다르고 학습 범위가 늘어난다.

## R6. 배포 (CI/CD)

- **결정**:
  - 워크플로 3개: `dashboard-api.yml`, `dashboard-agent.yml`, `dashboard-web.yml`. 각자 `paths: services/dashboard-<앱>/**` + 자기 워크플로 파일.
  - `pull_request`: 테스트·빌드만. `push` to `main`: OIDC로 배포 역할을 받아 배포.
  - api·agent: `docker build`(linux/amd64) → ECR push(태그 = 커밋 SHA) → SSM 파라미터 `/tms/app/<앱>/image-tag` 갱신 → 태그 `tms:app=<앱>`인 실행 중 인스턴스 수를 세어 0이면 종료, 아니면 `ssm send-command`(`AWS-RunShellScript`, `/opt/tms/deploy.sh`) 후 결과 대기.
  - web: `npm ci && npm run build` → `aws s3 sync`(해시 파일 `Cache-Control: max-age=31536000, immutable`, `index.html`은 `no-cache`) → `index.html`만 CloudFront 무효화.
  - 배포 역할 신뢰 조건: `token.actions.githubusercontent.com:sub = repo:SungChul23/smokestack-guard:ref:refs/heads/main`, `aud = sts.amazonaws.com`.
- **이유**: spec FR-015·016, US4. 서버 0대일 때도 실패하지 않고 태그만 기록한다.
- **버린 대안**: CodeDeploy(설정이 많음), 서버가 주기적으로 새 태그를 확인(배포가 느리고 실패를 CI에서 못 봄).

## R7. 화면(CloudFront)

- **결정**: 배포 1개에 별칭 `smokestack-guard.store`, `www.smokestack-guard.store`. OAC로 S3 비공개 읽기. 기본 루트 객체 `index.html`. `403/404 → /index.html 200`(화면 안 경로 새로고침). `www` → 루트 301은 CloudFront Function(viewer-request). `http` → `https` 리디렉션. 캐시 정책은 원본 `Cache-Control`을 따르는 사용자 정의 정책(최소 TTL 0). 가격 등급 `PriceClass_200`(한국 포함, 가장 비싼 지역 제외).
- **이유**: spec FR-007·008.
- **버린 대안**: S3 정적 웹사이트 호스팅(버킷이 공개돼야 함), `www`용 별도 배포(배포·인증서가 늘어남).

## R8. 로그인(Cognito)

- **결정**: 사용자 풀(`allow_admin_create_user_only = true`, 이메일을 사용자 이름으로, 비밀번호 정책 기본), 공개 앱 클라이언트(클라이언트 비밀 없음, Authorization code + PKCE), 관리형 로그인용 접두사 도메인 `smokestack-guard`(`*.auth.ap-northeast-2.amazoncognito.com`). 콜백·로그아웃 URL: `https://smokestack-guard.store/`, `http://localhost:5173/`.
- **이유**: spec FR-009·010. 사용자 지정 로그인 도메인(`auth.smokestack-guard.store`)은 인증서·레코드가 더 필요해 범위 밖.
- **버린 대안**: 셀프 가입 + 승인(외부인 가입 시도 자체를 막는 게 목적).

## R9. DB(RDS PostgreSQL)

- **결정**: PostgreSQL 16 최신 마이너(pgvector 지원), `db.t4g.micro`, gp3 20GB, 퍼블릭 접근 꺼짐, DB 서브넷 그룹(두 AZ), `multi_az = var.db_multi_az`.
  - 비밀번호: `manage_master_user_password = true`(RDS가 Secrets Manager에 만들고 Terraform 상태에 값이 남지 않음). 교체 주기 30일은 `aws_secretsmanager_secret_rotation`(람다 없이 `rotation_rules`만)으로 관리형 비밀에 건다. provider가 관리형 비밀의 회전 규칙 변경을 받지 않으면, quickstart에 `aws secretsmanager rotate-secret --rotation-rules AutomaticallyAfterDays=30` 1회 실행으로 대신한다(구현 때 `validate`/`plan`으로 확인).
  - 끌 때: `skip_final_snapshot = false`, 마지막 스냅샷 이름에 생성 시각을 넣고(`ignore_changes`로 고정) 다음 삭제와 이름이 겹치지 않게 한다. `deletion_protection = false`(변수로 지워야 하므로). 다시 켤 때 `db_restore_snapshot_id` 변수가 있으면 그 스냅샷에서 만든다.
  - 백업 보존 1일(자동 백업 저장 비용 최소).
- **이유**: spec FR-017~019, FR-026.
- **버린 대안**: RDS 중지(최대 7일 뒤 자동으로 다시 켜짐), Aurora Serverless v2(최소 용량 요금이 micro보다 비쌈).

## R10. 배스천

- **결정**: `t3.micro`, Amazon Linux 2023, 퍼블릭 서브넷, 공인 IP, 키 쌍 이름 `var.bastion_key_name`(A가 콘솔에서 생성), SSM 관리형 정책(A의 관리 접속용). Route 53 A 레코드 `bastion.smokestack-guard.store` → 공인 IP(TTL 60). `rds_enabled`와 같은 `count`.
  - 사용자 데이터로 `sshd_config` 보강: `PasswordAuthentication no`, `Match User ec2-user` 아래 `PermitOpen <RDS 엔드포인트>:5432`, `ForceCommand /sbin/nologin`, `X11Forwarding no`.
  - 즉 공용 키로는 **DB 포트 터널만** 된다. 셸은 열리지 않는다. A의 셸 작업은 SSM 세션으로 한다.
- **이유**: spec FR-020·024·025, 22번 전체 허용(0.0.0.0/0)을 받아들인 대신 키가 새도 할 수 있는 일을 DB 터널 하나로 줄인다. DBeaver의 SSH 터널은 셸 없이 포트 포워딩만 쓰므로 동작한다.
- **버린 대안**: SSM 포트 포워딩(팀원이 CLI·플러그인을 설치하고 매번 명령 실행, 사용자 결정으로 제외), 고정 탄력적 IP(이름 레코드로 충분하고 IP 비용은 같음).

## R11. 팀원 DB 비밀번호 읽기

- **결정**: IAM 그룹 `tms-db-users`, 구성원 `var.db_user_names`(기본값: `de-ai-05`, `de-ai-08`, `de-ai-11`, `de-ai-14`, `de-ai-22`, `tms_mentor`). 정책: 관리형 DB 비밀 1개에 `secretsmanager:GetSecretValue`·`DescribeSecret`, 그리고 `rds:DescribeDBInstances`(엔드포인트 확인). 그룹은 DB와 무관하게 늘 있고, DB가 꺼져 있으면 정책 대상 비밀이 없다(정책은 `count`로 DB와 함께).
- **이유**: spec FR-026. 사용자 이름은 비밀이 아니다.

## R12. 비용 알림(Budgets)

- **결정**: 월 비용 예산 1개(한도 $200). 실제 비용 25%·50%·75%($50·$100·$150)와 예상 비용 100%에서 이메일(`TF_VAR_alert_email`, 기존 규칙). **`include_credit = false`**.
- **이유**: 기본 설정은 크레딧을 비용에서 빼서 실제 사용액이 0처럼 보인다. 크레딧을 빼기 전 사용액으로 알려야 의미가 있다. 예산 2개까지 무료.

## R13. 이미지 저장소·로그

- **결정**: ECR `tms-dashboard-api`, `tms-dashboard-agent`: 태그 변경 불가, 푸시 시 스캔, 수명 주기 "최근 10개만". 로그 그룹 `/tms/app/api`, `/tms/app/agent` 보존 14일(기존 규칙과 같음).

## R14. ALB

- **결정**: `alb_enabled`로 `count`. 퍼블릭 서브넷 2개. 80 → 443 리디렉션, 443(서울 ACM) 기본 동작 404 고정 응답, 규칙 `/api/*` → API 대상 그룹, `/agent/*` → 에이전트 대상 그룹. 대상 그룹 포트 8000, 상태 확인 `/health`, 등록 해제 지연 30초. 에이전트 응답이 길 수 있어 유휴 시간 제한 120초. `api.` A 별칭 레코드도 같은 `count`.
- **경로**: 접두사(`/api`, `/agent`)를 떼지 않고 그대로 서버에 보낸다. 앱은 그 접두사 아래에 경로를 둔다(계약).

## R15. 최소 앱

- **결정**: A가 세 폴더에 배포 확인용 최소 앱을 둔다.
  - `services/dashboard-api/`: FastAPI, `/health`, `/api/health`, `/api/db-check`(DB에 `SELECT 1`, 연결 확인용), Dockerfile.
  - `services/dashboard-agent/`: FastAPI, `/health`, `/agent/health`, Dockerfile.
  - `services/dashboard-web/`: Vite + React 빈 페이지.
- **외부 패키지 이유**(원칙 운영 제약): FastAPI·uvicorn은 서버 앱 기본, Vite·React는 화면 기본. D가 같은 폴더에서 이어 쓴다. 수집 Lambda와 무관.

## R16. 비용 (서울, 월 730시간, 크레딧 차감 전)

| 자원 | 꺼 둠 | 개발 | 시연 |
|---|---|---|---|
| Route 53 영역 | $0.50 | $0.50 | $0.50 |
| ECR·S3·CloudFront·로그·SSM 파라미터 | < $1 | < $1 | < $1 |
| NAT ($0.059/h + 공인 IP) | 0 | 1개 약 $47 | 2개 약 $94 |
| ALB (+ 공인 IP 2) | 0 | 약 $25 | 약 $25 |
| EC2 t3.small | 0 | 2대 약 $38 | 4대 약 $76 |
| RDS db.t4g.micro + 20GB | 0 | 단일 약 $20 | Multi-AZ 약 $40 |
| 배스천 t3.micro + 공인 IP | 0 | 약 $14 | 약 $14 |
| Secrets Manager | 0 | $0.40 | $0.40 |
| **합계(월로 환산)** | **약 $1~2** | **약 $146** | **약 $250** |

- 개발·시연 구성은 **하루 단위**로 켜고 끄는 것을 전제로 한다(개발 하루 약 $5, 시연 하루 약 $8). 데이터 전송·LLM 호출 제외.
- 공인 IPv4는 개당 시간 $0.005(월 $3.65).
