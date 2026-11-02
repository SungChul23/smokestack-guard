# CLAUDE.md — smokestack-guard

이 파일은 Claude Code가 이 저장소에서 작업할 때 따르는 규칙이다. 답변과 문서는 한국어로 작성한다.

## 프로젝트 개요

- 굴뚝 TMS 데이터 파이프라인 및 AI 사전 경고 시스템 (부트캠프 기업연계 최종 프로젝트, 팀 5명)
- 한국환경공단 굴뚝자동측정기기(CleanSYS) 공개 API를 주기적으로 수집해 원본을 S3에 보존한다.
- **놓친 데이터는 다시 받을 수 없다.** 공개 API에 과거 조회 기능이 없으므로 수집 공백을 만드는 변경은 가장 위험한 변경이다.

## AWS 환경

- 팀 계정: `952900391026` / 리전: `ap-northeast-2` (서울)
- 루트 사용자로 작업하지 않는다. 모든 작업은 IAM 사용자/역할 기준이다.
- 계정 ID, 리전, 버킷 이름은 비밀이 아니다. API 키·액세스 키·비밀번호는 비밀이다.

## 저장소 구조

```
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
- **`terraform apply`와 `terraform destroy`는 직접 실행하지 않는다.** `plan` 결과를 보여주고 사용자가 실행한다.

## 비밀값 규칙 (저장소가 Public이다)

- API 키는 SSM Parameter Store **표준 등급, SecureString**에 사용자가 콘솔로 직접 등록한다. (예: `/tms/collector/api-key`)
- Terraform은 파라미터 **이름**만 참조한다. `aws_ssm_parameter`로 값을 넣지 않는다. (상태 파일에 평문으로 남기 때문)
- 코드, tfvars, 예시 파일, 커밋 메시지, 로그 어디에도 실제 키 값을 쓰지 않는다.
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

- Claude Code는 사용자가 요청하면 `git add`와 `git commit`을 실행할 수 있다. 작성자는 `SungChul23 <kimsam0923@naver.com>`을 쓴다.
- `git push`, `git checkout`/`git switch`, `git branch`, `git merge`, `git rebase`, `git reset`, `git stash`, `git clean`, `git restore`는 금지.
- 허용: `git status`, `git diff`, `git log` 같은 읽기 명령.
- 커밋 메시지는 `feat:`, `fix:`, `chore:` 같은 유형 뒤에 한국어로 무엇을 왜 바꿨는지 쓴다. push는 사용자가 직접 한다.
- 작업 환경: Claude Code는 WSL에서만 실행한다. 사용자는 Git 작업을 PowerShell에서 한다.
- `main`은 보호됨: PR 필수, 승인 1명, Squash merge만 허용.
- 브랜치: `<유형>/<범위>-<내용>` (예: `infra/tms-collection-terraform`, `feat/collector-ssm-key`, `fix/collector-hash-state`)

## 하지 말 것

- 수집 스케줄을 끄거나 주기를 바꾸는 변경을 사용자 확인 없이 하지 않는다.
- 원본 버킷의 객체를 삭제·덮어쓰는 코드나 수명 주기 규칙을 사용자 확인 없이 추가하지 않는다.
- 비밀값을 출력하거나 파일에 쓰지 않는다.

0. 저장소 루트에 .gitignore 생성:
   .terraform/, *.tfstate, *.tfstate.*, *.tfvars (단 !*.tfvars.example),
   crash.log, .env, .claude/settings.local.json, CLAUDE.local.md,
   services/**/*.zip, __pycache__/, .DS_Store