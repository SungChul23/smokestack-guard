# Implementation Plan: Google 로그인 + 초대 코드

**Branch**: `64-a-google-로그인-초대-코드-cognito` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/a-platform/013-google-login-invite/spec.md`

## Summary

Cognito 사용자 풀 `tms-users`에 Google 공급자를 붙이고(사람이 콘솔로 등록, 시크릿은 상태 파일에 남기지 않음), 앱 클라이언트를 Google 전용으로 바꾼다. 화면은 Cognito 화면을 건너뛰고 바로 Google로 보낸다. 서비스 자격은 Cognito 그룹 `members`로 표시하고, Access 토큰의 `cognito:groups`를 API·에이전트가 매 요청 확인한다. 자격이 없는 회원은 화면에서 초대 코드를 넣고, API가 SSM SecureString의 코드와 비교해 맞으면 `AdminAddUserToGroup` → 화면이 갱신 토큰으로 새 토큰을 받아 바로 쓴다. 서버 토큰 검증 방식(009)은 그대로다. 새 유료 자원은 없다.

## Technical Context

**Language/Version**: Python 3.12(FastAPI, API·에이전트), TypeScript 5.6 + React 18(화면) · Terraform `~> 1.15.0`, AWS provider `~> 6.0`

**Primary Dependencies**: PyJWT(기존), boto3(SSM·Cognito), `react-oidc-context`·`oidc-client-ts`(기존). 새 패키지 없음

**Storage**: Cognito(회원·그룹), SSM 파라미터(초대 코드, Google 백업). DB 변경 없음

**Testing**: pytest — 그룹 확인, 초대 코드 확인(SSM·Cognito는 가짜 객체), 시도 제한. 화면은 `tsc`·`vite build`

**Target Platform**: 기존 EC2 앱 서버 2대(ALB 뒤, NAT로 Cognito·SSM API), CloudFront 정적 화면

**Project Type**: 웹 앱 인증 변경(인프라 설정 + 서버·화면 코드)

**Performance Goals**: 로그인 30초 안(SC-001), 코드 통과 후 1분 안 사용(SC-002). 자격 확인은 토큰 안에서 끝나 추가 호출 없음

**Constraints**: Google 시크릿·초대 코드는 Terraform 상태·저장소·로그에 없음. 배포 워크플로는 main만 → 배포 전 확인은 로컬(콜백 `http://localhost:5173/` 등록됨)

**Scale/Scope**: 회원 수십 명(팀 5명 + 시연자)

## Constitution Check

| 원칙 | 판정 | 근거 |
|---|---|---|
| I. 수집 연속성 | 해당 없음 | 수집 경로·스케줄을 건드리지 않는다 |
| II. 비밀값 비공개 | 통과 | Google 시크릿은 사람이 Cognito 콘솔에 등록하고 SSM에 백업, 초대 코드도 사람이 SSM에 등록(R1·R6). Terraform은 이름만, 로그에는 입력값 없음 |
| III. 코드로 만들고 적용은 사람이 | 통과 | 앱 클라이언트·그룹·서버 권한은 Terraform. 콘솔 작업은 Terraform이 비밀을 상태에 남기는 것을 피하려는 예외로 quickstart에 기록. `plan`·`apply`는 A |
| IV. 데이터 계약 우선 | 통과 | 화면↔서버 인증 약속을 `contracts/auth-api.md`로 고정하고 D와 공유 |
| V. 같은 조건의 정직한 비교 | 해당 없음 | |
| VI. 설명 가능한 결과 | 통과 | 거부 응답에 이유 코드(`not_member`, `invalid_code`, `too_many_attempts`) |

### IAM 권한 (추가분만)

| 주체 | 권한 | 리소스 | 이유 |
|---|---|---|---|
| 앱 서버 역할 `tms-app-server` | `cognito-idp:AdminAddUserToGroup` | 사용자 풀 `tms-users` ARN | 코드 통과 시 그룹 추가 |
| | `kms:Decrypt` (조건 `kms:ViaService = ssm.ap-northeast-2.amazonaws.com`) | AWS 관리형 키 `alias/aws/ssm` | SecureString 초대 코드 |

SSM 읽기(`/tms/app/*`)는 이미 있다. 서버는 `/tms/auth/*`(Google 백업)를 읽지 못한다.

## Project Structure

### Documentation (this feature)

```text
specs/a-platform/013-google-login-invite/
├── spec.md  plan.md  research.md  data-model.md  quickstart.md
├── contracts/auth-api.md
├── checklists/requirements.md
└── tasks.md            # /speckit-tasks
```

### Source Code (repository root)

```text
infra/stacks/tms-serving/auth.tf       # 앱 클라이언트 공급자 var.login_providers(기본 ["Google"]), 그룹 members, explicit_auth_flows에서 SRP 제거
infra/stacks/tms-serving/variables.tf  # login_providers
infra/stacks/tms-app/iam.tf            # AdminAddUserToGroup, kms:Decrypt(ssm 경유)
services/dashboard-api/app/auth.py     # LoggedInUser, CurrentUser(= + members), 403 not_member
services/dashboard-api/app/invite.py   # 코드 읽기(SSM, 5분 캐시)·비교·시도 제한·그룹 추가
services/dashboard-api/app/main.py     # GET /api/me(member), POST /api/invite
services/dashboard-api/tests/          # test_auth(그룹), test_invite
services/dashboard-agent/app/auth.py   # 같은 CurrentUser 변경
services/dashboard-agent/tests/test_auth.py
services/dashboard-web/src/auth.ts     # identity_provider=Google로 바로 이동
services/dashboard-web/src/App.tsx     # /api/me → 초대 코드 화면 → signinSilent
services/dashboard-web/src/Invite.tsx  # 초대 코드 입력 화면
specs/a-platform/009-service-infra/contracts/app-runtime.md  # 인증 절을 013 계약으로 연결
```

**Structure Decision**: 새 스택이나 서비스를 만들지 않고 009의 `tms-serving`·`tms-app`과 세 앱의 인증 부분만 고친다. 초대 코드 확인은 별도 Lambda가 아니라 API에 둔다(이미 SSM 읽기 권한·NAT 경로가 있고, 화면이 같은 주소로 부름).

## Complexity Tracking

| 항목 | 필요한 이유 | 더 단순한 대안을 버린 이유 |
|---|---|---|
| Google 공급자를 콘솔로 등록 | 시크릿이 Terraform 상태에 남지 않게 | Terraform 관리 시 `provider_details`가 상태에 평문 저장(원칙 II) |
| 서버 메모리 시도 제한(서버별) | 무차별 대입을 늦춤 | 공유 저장소(DynamoDB·RDS)는 회원 수십 명·시연용 규모에 과함. 노출 시 코드 교체로 대응 |
