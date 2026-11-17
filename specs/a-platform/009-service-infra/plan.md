# Implementation Plan: 대시보드·에이전트 서비스 인프라 골격

**Branch**: `53-a-서비스-인프라-골격-구축-네트워크도메인cloudfrontcognitoecrcicd-비용-큰-자원은-꺼둔-채` | **Date**: 2026-11-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/a-platform/009-service-infra/spec.md`

## Summary

대시보드·에이전트가 올라갈 서비스 인프라를 Terraform 스택 5개로 만든다. 도메인(`smokestack-guard.store`)·인증서·화면(CloudFront+S3)·로그인(Cognito)·네트워크·이미지 저장소·배포 길(GitHub OIDC)은 지금 만들어 켜 두고, 시간당 요금이 붙는 NAT·ALB·RDS·EC2·배스천은 변수로 꺼 둔 채 만든다. 꺼 둔 상태 월 $1~2, 개발 구성 하루 약 $5, 시연 구성 하루 약 $8. 팀원은 공용 키로 배스천 SSH 터널을 거쳐 DBeaver로 RDS에 접속하고, D는 `services/dashboard-*` 폴더만 고치면 main 머지 때 그 앱만 배포된다. 결정 근거는 [research.md](research.md).

## Technical Context

**Language/Version**: Terraform `~> 1.15.0` (AWS provider `~> 6.0`), 최소 앱: Python 3.11 + FastAPI, Node 20 + Vite·React, 서버 셸(bash, Amazon Linux 2023)

**Primary Dependencies**: AWS(Route 53, ACM, CloudFront, S3, Cognito, VPC, NAT, ALB, EC2·ASG, ECR, RDS PostgreSQL 16, Secrets Manager, SSM, CloudWatch Logs, Budgets, IAM OIDC), GitHub Actions

**Storage**: RDS PostgreSQL 16 + pgvector(꺼 둔 기본), 화면 S3 버킷, ECR

**Testing**: `terraform fmt -check`·`validate`(에이전트), `plan`(사람), 최소 앱 pytest·eslint/빌드(CI), quickstart 확인 절차(사람)

**Target Platform**: AWS `ap-northeast-2`(+ CloudFront 인증서용 `us-east-1`), 계정 952900391026

**Project Type**: 인프라(IaC) + 배포 파이프라인 + 배포 확인용 최소 웹 앱

**Performance Goals**: 켜기 30분 안 응답(SC-003), main 머지 15분 안 배포(SC-005)

**Constraints**: 크레딧 $200·6개월, 꺼 둔 상태 월 $5 이하, 비밀값 저장소·상태 평문 0건, AI는 apply 금지

**Scale/Scope**: 사용자 수십 명(시연), EC2 최대 5대, 스택 5개, 워크플로 3개

## Constitution Check

*GATE: Phase 0 전 통과, Phase 1 설계 후 재확인 완료.*

| 원칙 | 판정 | 근거 |
|---|---|---|
| I. 수집 연속성 | 통과 | 새 스택만 추가. 원본 버킷·수집 Lambda·스케줄·Silver 잡을 바꾸지 않는다. 수집 공백 위험 없음 |
| II. 비밀값 비공개 | 통과 | DB 비밀번호는 RDS 관리형(상태에 값 없음), 배스천 키는 콘솔에서 만들고 이름만 참조, 알림 이메일은 `TF_VAR_alert_email`, CI는 OIDC(장기 키 없음). IAM 사용자 이름·도메인·계정 ID는 비밀 아님. 액세스 키는 어디에도 쓰지 않는다 |
| III. 코드로 만들고 적용은 사람이 | 통과(예외 2건, 아래 표) | 모든 AWS 자원은 Terraform. 에이전트는 `fmt`·`validate`까지, `plan`·`apply`는 A. IAM 권한과 이유: [data-model.md §5](data-model.md), [contracts/deploy-pipeline.md](contracts/deploy-pipeline.md) |
| IV. 데이터 계약 우선 | 해당 적음 | DB 테이블은 만들지 않는다. 앱과 인프라 사이 약속은 [contracts/app-runtime.md](contracts/app-runtime.md)로 먼저 정한다 |
| V. 같은 조건의 비교 | 해당 없음 | |
| VI. 설명 가능한 결과 | 해당 없음 | |
| 운영 제약: 비용 한 줄 | 통과 | [research.md R16](research.md): 꺼 둠 월 $1~2, 개발 월 환산 약 $146(하루 $5), 시연 약 $250(하루 $8). Budgets 알림 $50·$100·$150 |
| 운영 제약: 외부 패키지 이유 | 통과 | FastAPI·uvicorn(서버), Vite·React(화면): D가 이어 쓸 기본 틀. [research.md R15](research.md) |

## Project Structure

### Documentation (this feature)

```text
specs/a-platform/009-service-infra/
├── spec.md
├── plan.md              # 이 파일
├── research.md          # 결정 R1~R16
├── data-model.md        # 이름, 네트워크, 보안그룹, 생명주기, IAM, SSM 파라미터
├── quickstart.md        # 적용 순서와 확인 절차, DBeaver 접속 안내
├── contracts/
│   ├── app-runtime.md   # 서버 앱이 받는 실행 환경 (A → D)
│   ├── toggles.md       # 켜고 끄는 변수, 운영 구성 3가지
│   └── deploy-pipeline.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
infra/stacks/
├── tms-foundation/      # 호스팅 영역, Budgets, GitHub OIDC 공급자 (지우지 않음)
├── tms-network/         # VPC, 서브넷, IGW, 라우팅, NAT(변수), S3 엔드포인트, 보안그룹 4
├── tms-serving/         # ACM 2(us-east-1 provider 별칭 포함), 화면 S3+CloudFront+함수, 루트·www 레코드, Cognito, 설정 SSM 파라미터
├── tms-database/        # RDS(변수), 비밀 교체, 배스천+bastion. 레코드, IAM 그룹 tms-db-users, DB 설정 SSM 파라미터
│   └── bastion-user-data.sh
└── tms-app/             # ECR 2, 서버 역할, 시작 템플릿 2, ASG 2, ALB(변수)+api. 레코드, 배포 역할, image-tag 파라미터, 로그 그룹
    └── server-user-data.sh   # Docker·스왑 설치, /opt/tms/deploy.sh 생성·실행

services/
├── dashboard-api/       # 최소 FastAPI (/health, /api/health, /api/db-check) + Dockerfile + tests
├── dashboard-agent/     # 최소 FastAPI (/health, /agent/health) + Dockerfile + tests
└── dashboard-web/       # Vite + React 빈 페이지

.github/workflows/
├── dashboard-api.yml
├── dashboard-agent.yml
└── dashboard-web.yml

.github/CODEOWNERS        # dashboard-* → D(+A), 새 스택 → A
AGENTS.md                 # 저장소 구조에 새 스택·폴더 추가 (#46 머지 뒤 마지막에)
```

**Structure Decision**: 기존 규칙(스택 = 독립 apply 단위, 폴더 이름은 하는 일 기준)을 따른다. 재사용할 모듈이 없어 `infra/modules/`는 늘리지 않는다. 스택마다 `backend.tf`(키 `stacks/<스택>/terraform.tfstate`), `versions.tf`(default_tags `stack = <스택>`), `variables.tf`, `main.tf`(필요하면 주제별 `.tf`), `outputs.tf`, `.terraform.lock.hcl`.

## 적용 순서와 의존

```
tms-foundation ──(출력 NS 4개 → 사람이 카페24 입력 → 전파 확인)──▶ tms-serving (ACM 검증에 필요)
tms-network ───▶ tms-database (서브넷·보안그룹)
            └──▶ tms-app (서브넷·보안그룹, NAT 수 확인)
tms-serving ───▶ tms-app (서울 인증서, 설정 파라미터)
tms-database ──▶ tms-app (DB 설정 파라미터가 있으면 읽음, 없어도 동작)
```

## 위험과 대응

| 위험 | 대응 |
|---|---|
| NS 전파 전에 `tms-serving` 적용 → ACM 대기 | quickstart 1단계에서 `nslookup` 확인 뒤 진행 |
| 켜 둔 것을 잊음 | Budgets 알림(크레딧 제외 금액 기준), 개발·시연 구성은 하루 단위로 켜고 끔 |
| 공용 키 유출 | 배스천은 DB 포트 터널만 허용(셸 불가), DB 비밀번호 별도, 키 교체 = 새 키 쌍 + 배스천 재생성 |
| 22번 전체 허용 스캔 | 비밀번호 로그인 끔, 키 인증만. 필요하면 `bastion_ssh_cidrs`로 좁힘 |
| `include_credit` 기본값 | Budgets에 `include_credit = false` 명시 |
| 관리형 비밀 회전 규칙을 provider가 못 바꿈 | quickstart에 CLI 1회 대안 (R9) |
| #46과 충돌 | `.specify/feature.json`, `AGENTS.md`만 겹침. AGENTS.md는 마지막 작업으로 미룸 |

## Complexity Tracking

| 예외 | 필요한 이유 | 더 단순한 대안을 버린 이유 |
|---|---|---|
| 배스천 키 쌍을 콘솔에서 생성 (원칙 III) | Terraform으로 키를 만들면 개인 키가 상태 파일에 평문으로 남는다(원칙 II 위반) | `tls_private_key`(상태에 개인 키), 공개 키만 Terraform에 넣기(키 생성·보관을 결국 사람이 해야 해 같음) |
| 카페24 네임서버 변경은 사람이 콘솔에서 (원칙 III) | 도메인 등록 기관이 AWS 밖이라 Terraform 범위가 아님 | Route 53에서 도메인 구매(비쌈, 사용자가 이미 구매) |
