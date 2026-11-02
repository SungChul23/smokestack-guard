# AGENTS.md — smokestack-guard 팀 공통 규칙

이 파일은 이 저장소에서 작업하는 모든 사람과 AI 에이전트(Claude Code, Codex 등)가 따르는 규칙이다.
Claude Code는 `.claude/CLAUDE.md`를 통해, Codex는 이 파일을 직접 읽는다. **규칙은 이 파일에서만 고친다.**
답변과 문서는 한국어로 작성한다.

## 프로젝트 개요

- 굴뚝 TMS 데이터 파이프라인 및 AI 사전 경고 시스템 (부트캠프 기업연계 최종 프로젝트, 팀 5명)
- 한국환경공단 굴뚝자동측정기기(CleanSYS) 공개 API를 주기적으로 수집해 원본을 S3에 보존한다.
- **놓친 데이터는 다시 받을 수 없다.** 공개 API에 과거 조회 기능이 없으므로 수집 공백을 만드는 변경은 가장 위험한 변경이다.
- 프로젝트 원칙은 `.specify/memory/constitution.md`에 있다. 이 파일의 규칙과 원칙이 충돌하면 원칙이 우선한다.

## 팀 역할

| 담당 | GitHub | 역할 | 한 줄 미션 | 부담당 | spec 번호 대역 |
|---|---|---|---|---|---|
| A | `SungChul23` | 플랫폼·AWS·통합 | 모두가 같은 환경에서, AWS든 대체 경로든 끊김 없이 돌게 한다 | B | 001–100 |
| B | `olchangiagi` | 수집·Bronze (+Kafka) | 놓친 데이터는 다시 못 받는다 — 누락을 1% 이하로 | C | 101–200 |
| C | `gjfeel4512` | 데이터 계약·Silver·Iceberg | 모두가 같은 약속(계약)으로 데이터를 읽고 쓰게 한다 | A | 201–300 |
| D | `jaeyan42` | 분석·화면·RAG | 결과를 보이게, 설명되게 한다 | E | 301–400 |
| E | `doeun-1202` | 판정·AI 경고·MLOps | 규칙과 모델을 같은 조건에서 정직하게 비교한다 | D | 401–500 |

- 담당 폴더별 리뷰어는 `.github/CODEOWNERS`에 있다. 새 작업 폴더를 만들면 담당자가 그 파일에 한 줄 추가한다.

## Spec Kit 작업 절차

이 저장소는 [Spec Kit](https://github.com/github/spec-kit) `v1.2.5`를 쓴다. 설치는 A가 한 번 했고, 팀원은 `git pull`만 하면 된다.

| 단계 | Claude Code | Codex | 결과 |
|---|---|---|---|
| 무엇을·왜 | `/speckit-specify` | `$speckit-specify` | `specs/NNN-이름/spec.md` |
| (선택) 모호한 점 정리 | `/speckit-clarify` | `$speckit-clarify` | spec.md 보강 |
| 어떻게 | `/speckit-plan` | `$speckit-plan` | `plan.md` (+ 원칙 점검) |
| 작업 목록 | `/speckit-tasks` | `$speckit-tasks` | `tasks.md` |
| 구현 | `/speckit-implement` | `$speckit-implement` | 코드 |

- **언제 쓰나:** 새 기능, 새 스택, 데이터 계약 변경처럼 리뷰가 필요한 작업. 오타·설정값·작은 버그 수정은 spec 없이 바로 한다.
- **번호는 자기 대역에서만 쓴다.** `specify`를 실행할 때 AI 에이전트는 `specs/`에서 해당 담당 대역의 가장 큰 번호를 찾아 다음 번호로 `SPECIFY_FEATURE_DIRECTORY=specs/<번호>-<짧은-이름>`을 지정한다. 기본 동작(저장소 전체에서 가장 큰 번호 + 1)을 쓰지 않는다. 담당을 모르면 먼저 사용자에게 묻는다.
- **브랜치는 사람이 만든다.** Spec Kit의 git 확장은 설치하지 않았다. spec 폴더와 브랜치는 서로 독립이며, 브랜치는 PR 단위로 아래 Git 규칙의 이름 형식을 따른다. 작은 spec 여러 개를 한 브랜치에 넣어도 된다.
- **PR에는 spec·plan·tasks와 코드를 함께 올린다.** 리뷰어는 `spec.md`부터 읽는다.
- `/speckit-implement`를 포함한 모든 Spec Kit 명령은 이 파일의 금지 사항을 그대로 따른다. (예: `terraform apply` 금지)
- **Spec Kit이 설치한 파일은 직접 고치지 않는다:** `.specify/scripts/`, `.specify/templates/`, `.specify/workflows/`, `.specify/integrations/`, `.claude/skills/speckit-*`, `.agents/skills/speckit-*`. 업그레이드하면 덮어써진다. 바꿔야 하면 A에게 요청한다.
- Spec Kit 스크립트는 `python3`로 실행된다 (Python 3.11 이상). Windows에서 Codex를 쓰면 WSL 안에서 실행하거나 `python3` 명령이 동작하는지 먼저 확인한다.

## AWS 환경

- 팀 계정: `952900391026` / 리전: `ap-northeast-2` (서울)
- 루트 사용자로 작업하지 않는다. 모든 작업은 IAM 사용자/역할 기준이다.
- 계정 ID, 리전, 버킷 이름은 비밀이 아니다. API 키·액세스 키·비밀번호는 비밀이다.

## 저장소 구조

```
AGENTS.md                 # 팀 공통 규칙 (이 파일)
.specify/                 # Spec Kit: 원칙(memory/constitution.md), 양식, 스크립트
specs/                    # 기능별 spec·plan·tasks (번호 대역은 팀 역할 표 참고)
infra/
├── bootstrap/            # Terraform 상태용 S3 버킷 (로컬 상태, 최초 1회)
├── stacks/
│   └── tms-collection/   # TMS 수집: 원본 버킷 + 수집 Lambda + 스케줄 + 알림
└── modules/
    ├── raw-archive/          # 원본 보존 버킷
    └── scheduled-collector/  # 주기 실행 수집기 (Lambda + 역할 + 스케줄 + 로그 + 알람)
services/
└── tms-collector/        # 수집 Lambda 코드 (Python, 외부 패키지 없음)
```

- **폴더 이름은 기술명이 아니라 하는 일 기준으로 짓는다.** (`lambda/`, `s3/` 금지 → `tms-collection/`, `raw-archive/`)
- 스택 = 업무 단위로 독립 apply 되는 묶음. 모듈 = 재사용되는 역할 단위.

## Terraform 규칙

- 버전: `required_version = "~> 1.15.0"`, AWS provider `~> 6.0`. 루트에 `.terraform-version` (`1.15.8`).
- `.terraform.lock.hcl`은 커밋한다.
- **backend 설정은 각 스택의 `backend.tf`에 하드코딩한다.** `-backend-config` 파일, `*.backend.hcl` 파일은 만들지 않는다. 팀원이 파일을 주고받지 않고 `terraform init`만으로 동작해야 한다.
  ```hcl
  terraform {
    backend "s3" {
      bucket       = "smokestack-tfstate-952900391026"
      key          = "stacks/<스택이름>/terraform.tfstate"
      region       = "ap-northeast-2"
      use_lockfile = true
      encrypt      = true
    }
  }
  ```
- provider에 `default_tags` (`project = "tms"`, `managed_by = "terraform"`, `stack = "<스택이름>"`)를 둔다.
- 변수에는 `description`과 `type`을 쓴다. 비밀이 될 수 있는 변수는 `sensitive = true`.
- 작업 후 `terraform fmt -recursive`와 `terraform validate`를 실행한다.
- **AI 에이전트는 `terraform apply`, `destroy`, `import`, `state`를 실행하지 않는다.** `plan` 결과를 보여주고 사람이 실행한다.

## 비밀값 규칙 (저장소가 Public이다)

- API 키는 SSM Parameter Store **표준 등급, SecureString**에 사람이 콘솔로 직접 등록한다. (예: `/tms/collector/api-key`)
- Terraform은 파라미터 **이름**만 참조한다. `aws_ssm_parameter`로 값을 넣지 않는다. (상태 파일에 평문으로 남기 때문)
- 코드, tfvars, 예시 파일, spec 문서, 커밋 메시지, 로그 어디에도 실제 키 값을 쓰지 않는다.
- `.gitignore`: `.terraform/`, `*.tfstate`, `*.tfstate.*`, `*.tfvars` (단 `*.tfvars.example` 은 커밋), `crash.log`, `.env`

## 수집 Lambda 규칙

- 10분마다 실행, 공개 API 전체 스냅샷을 받아 S3에 gzip 원문 + 메타 파일로 저장한다.
- 응답 SHA-256 해시를 `tms_cleansys/_state/latest.json`에 기록하고, 이전 해시와 다를 때만 원문을 저장한다. 실행 시각은 매번 기록해 "갱신 없음"과 "수집 중단"을 구분한다.
- 원본 경로: `tms_cleansys/ingest_date=YYYY-MM-DD/hour=HH/run_ts=YYYYMMDDTHHMMSSZ/snapshot.json.gz` (+ `snapshot.meta.json`)
- 상태 파일: `tms_cleansys/_state/latest.json` (`sha256_raw`, `last_changed_at`, `last_checked_at`, `raw_key`)
- `reserved_concurrent_executions`는 쓰지 않는다. 계정 동시 실행 한도가 10이면 설정할 수 없다. 한도 상향 후 상태 파일 경합 방지를 위해 `1`로 설정한다.
- API 키는 환경 변수로 받은 SSM 파라미터 **이름**으로 읽고, **핸들러 밖 전역 변수에 캐시**한다.
- 로그에는 **요약만** 남긴다: 수집 건수, 해시 변경 여부, 저장 경로, 소요 시간. API 응답 본문은 로그에 찍지 않는다.
- 로그 그룹은 Terraform으로 만들고 보존 기간 14일.
- Lambda 실행 역할은 최소 권한: 기본 로그 권한 + 원본 버킷 `s3:GetObject`/`s3:PutObject` + SSM 파라미터 1개 `ssm:GetParameter` + `alias/aws/ssm` 복호화.
- 외부 패키지를 추가하지 않는다 (표준 라이브러리 + boto3).

## 스케줄·알림 규칙

- EventBridge Scheduler: `cron(0/10 * * * ? *)` (매시 00분부터 10분 단위), 시간대 `Asia/Seoul`, 유연한 시간 창 OFF, 전용 호출 역할.
- Lambda `Errors` 알람 → SNS 토픽 → 이메일 구독 (이메일 주소는 tfvars에 쓰지 않고 `TF_VAR_alert_email` 환경 변수로 전달).

## Git 규칙

- AI 에이전트는 사용자가 요청하면 `git add`와 `git commit`을 실행할 수 있다. 작성자는 각자 본인 git 설정을 쓴다.
- AI 에이전트는 `git push`, `git checkout`/`git switch`, `git branch`, `git merge`, `git rebase`, `git reset`, `git stash`, `git clean`, `git restore`를 실행하지 않는다. 브랜치 작업과 push는 사람이 한다.
- 허용: `git status`, `git diff`, `git log` 같은 읽기 명령.
- 커밋은 작업 단위로 나눈다. 커밋 메시지는 `feat:`, `fix:`, `chore:`, `docs:` 같은 유형 뒤에 한국어로 무엇을 왜 바꿨는지 쓴다.
- `main`은 보호됨: PR 필수, 승인 1명. Merge commit / Squash / Rebase 세 방식 모두 허용되어 있다. 작업 단위 커밋을 남기려면 Merge commit 또는 Rebase로 합친다.
- 브랜치: `<유형>/<범위>-<내용>` (예: `infra/tms-collection-terraform`, `feat/collector-ssm-key`, `fix/collector-hash-state`)

## 하지 말 것

- 수집 스케줄을 끄거나 주기를 바꾸는 변경을 사용자 확인 없이 하지 않는다.
- 원본 버킷의 객체를 삭제·덮어쓰는 코드나 수명 주기 규칙을 사용자 확인 없이 추가하지 않는다.
- 비밀값을 출력하거나 파일에 쓰지 않는다.
