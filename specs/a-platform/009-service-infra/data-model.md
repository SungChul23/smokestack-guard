# Data Model: 서비스 인프라 골격 (009)

이 기능은 데이터 테이블을 만들지 않는다. 여기서는 "자원과 그 관계", "이름 규칙", "접근 규칙", "권한"을 모델로 적는다.

## 1. 이름 규칙

| 대상 | 이름 |
|---|---|
| 도메인 | 화면 `smokestack-guard.store`, `www.smokestack-guard.store` · 서버 `api.smokestack-guard.store` · 배스천 `bastion.smokestack-guard.store` |
| VPC·서브넷 `Name` 태그 | `tms-vpc`, `tms-public-a/c`, `tms-app-a/c`, `tms-db-a/c` |
| 보안그룹 | `tms-alb`, `tms-app`, `tms-bastion`, `tms-db` |
| 화면 버킷 | `smokestack-tms-web-952900391026` |
| ECR | `tms-dashboard-api`, `tms-dashboard-agent` |
| ASG | `tms-api`, `tms-agent` (인스턴스 태그 `tms:app = api / agent`) |
| RDS | 식별자 `tms-db`, DB 이름 `tms`, 관리자 `tms_admin` |
| IAM | 역할 `tms-app-server`, `tms-bastion`, `tms-github-deploy` · 그룹 `tms-db-users` |
| SSM 파라미터 | `/tms/app/<api·agent>/image-tag`, `/tms/app/config/*` |
| 로그 그룹 | `/tms/app/api`, `/tms/app/agent` |

## 2. 네트워크

| 서브넷 | AZ | CIDR | 라우팅 (0.0.0.0/0) |
|---|---|---|---|
| `tms-public-a` | ap-northeast-2a | 10.20.0.0/24 | IGW |
| `tms-public-c` | ap-northeast-2c | 10.20.1.0/24 | IGW |
| `tms-app-a` | ap-northeast-2a | 10.20.10.0/24 | NAT-a (NAT 0개면 없음) |
| `tms-app-c` | ap-northeast-2c | 10.20.11.0/24 | NAT-c, NAT 1개면 NAT-a |
| `tms-db-a` | ap-northeast-2a | 10.20.20.0/24 | 없음 |
| `tms-db-c` | ap-northeast-2c | 10.20.21.0/24 | 없음 |

VPC `10.20.0.0/16`. S3 게이트웨이 엔드포인트는 앱·DB 라우팅 테이블에 붙는다.

## 3. 보안그룹 (모두 `tms-network`)

| 보안그룹 | 들어옴 | 나감 |
|---|---|---|
| `tms-alb` | 443, 80 ← 0.0.0.0/0 | 8000 → `tms-app` |
| `tms-app` | 8000 ← `tms-alb` | 443 → 0.0.0.0/0 (NAT 경유 AWS API·Bedrock), 5432 → `tms-db` |
| `tms-bastion` | 22 ← `bastion_ssh_cidrs` (기본 0.0.0.0/0) | 443 → 0.0.0.0/0 (SSM·패키지), 5432 → `tms-db` |
| `tms-db` | 5432 ← `tms-app`, 5432 ← `tms-bastion` | 없음 |

`bastion_ssh_cidrs`는 보안그룹과 함께 `tms-network`의 변수다.

## 4. 자원 생명주기 (켜고 끄기)

```
tms-foundation  [항상]   호스팅 영역 · Budgets · GitHub OIDC 공급자
tms-network     [항상]   VPC · 서브넷 · IGW · 라우팅 · S3 엔드포인트 · 보안그룹
                [변수]   NAT 0~2 (+ 탄력적 IP)
tms-serving     [항상]   ACM 2 · 화면 S3 · CloudFront · 루트·www 레코드 · Cognito
tms-database    [항상]   DB 서브넷 그룹 · IAM 그룹 tms-db-users
                [rds_enabled] RDS · 비밀 교체 규칙 · 배스천 · bastion. 레코드 · 비밀 읽기 정책 · /tms/app/config/db-*
tms-app         [항상]   ECR 2 · 서버 역할 · 시작 템플릿 2 · ASG 2(대수 0) · 배포 역할 · 앱 SSM 파라미터 · 로그 그룹
                [alb_enabled] ALB · 대상 그룹 2 · 리스너 · api. 레코드
                [*_desired]   EC2 인스턴스
```

## 5. IAM 권한 (원칙 III: 부여 이유)

| 주체 | 권한 | 이유 |
|---|---|---|
| `tms-app-server` (EC2 역할) | `AmazonSSMManagedInstanceCore` | 배포 명령 수신, A의 세션 접속 |
| | ECR pull (두 저장소) + `GetAuthorizationToken` | 이미지 받기 |
| | `ssm:GetParameter(s)` on `/tms/app/*` | 이미지 태그·설정 읽기 |
| | `secretsmanager:GetSecretValue` on DB 비밀 | DB 접속 |
| | `logs:CreateLogStream`, `PutLogEvents` on 두 로그 그룹 | 컨테이너 로그 |
| | `bedrock:InvokeModel*` | 에이전트 LLM 호출 |
| `tms-bastion` (EC2 역할) | `AmazonSSMManagedInstanceCore` | A의 관리 접속 |
| `tms-github-deploy` (OIDC 역할) | [contracts/deploy-pipeline.md](contracts/deploy-pipeline.md) | main 배포 |
| `tms-db-users` (IAM 그룹) | DB 비밀 1개 `GetSecretValue`·`DescribeSecret`, `rds:DescribeDBInstances` | 팀원이 DBeaver 비밀번호·주소 확인 |

## 6. SSM 파라미터 (모두 String, 비밀 아님)

| 이름 | 만드는 스택 | 값 |
|---|---|---|
| `/tms/app/api/image-tag`, `/tms/app/agent/image-tag` | `tms-app` (처음 `none`) | 배포가 갱신 |
| `/tms/app/config/cognito-user-pool-id`, `cognito-client-id`, `cognito-domain` | `tms-serving` | Cognito 값 |
| `/tms/app/config/web-bucket`, `web-distribution-id` | `tms-serving` | 화면 배포 대상 |
| `/tms/app/config/db-host`, `db-secret-arn` | `tms-database` (DB 켜졌을 때만) | DB 위치 |
