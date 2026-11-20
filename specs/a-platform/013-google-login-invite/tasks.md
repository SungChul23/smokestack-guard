# Tasks: Google 로그인 + 초대 코드

**Input**: `specs/a-platform/013-google-login-invite/` (spec, plan, research, data-model, contracts/auth-api.md, quickstart)

**표시**
- [P]: 다른 파일이라 같이 해도 됨
- [US1]~[US3]: spec의 사용자 스토리
- 🧑: 사람(A)이 콘솔·Terraform으로 하는 일. 📨: 다른 담당과 공유

테스트는 spec의 인수 시나리오가 서버 동작(거부·통과·제한)이라 함께 만든다.

## Phase 1: Setup (사람, 코드 전)

- [X] T001 🧑 Google Cloud: 동의 화면(외부, `openid email profile`, 프로덕션 게시, 승인 도메인), 웹 OAuth 클라이언트(원본·리디렉션 = Cognito 도메인) (quickstart §1).
- [X] T002 🧑 Cognito 콘솔: `tms-users`에 공급자 **Google** 등록(클라이언트 ID·시크릿, 범위, 속성 매핑 `email`·`email_verified`·`name`) (quickstart §2, research R1).
- [X] T003 🧑 SSM: `/tms/auth/google-oauth-client-id`(String), `/tms/auth/google-oauth-client-secret`(SecureString), `/tms/app/secret/invite-code`(SecureString, `alias/aws/ssm`) (data-model).

## Phase 2: Foundational (모든 스토리의 전제)

- [X] T004 `infra/stacks/tms-serving/variables.tf`: `login_providers`(list(string), 기본 `["Google"]`, 설명에 "콘솔에서 등록한 공급자 이름. 시크릿은 Terraform에 넣지 않음").
- [X] T005 `infra/stacks/tms-serving/auth.tf`: 앱 클라이언트 `supported_identity_providers = var.login_providers`, `explicit_auth_flows = ["ALLOW_REFRESH_TOKEN_AUTH"]`(비밀번호 로그인 흐름 제거), 그룹 `aws_cognito_user_group.members`(설명: 초대 코드 통과), 파일 머리 주석을 013 기준으로. `allow_admin_create_user_only = true` 유지 (research R2).
- [X] T006 [P] `infra/stacks/tms-app/iam.tf`: `data "aws_ssm_parameter" "cognito_user_pool_id"`(`/tms/app/config/cognito-user-pool-id`) → 정책에 `AddMemberGroup`(`cognito-idp:AdminAddUserToGroup`, 풀 ARN), `DecryptAppSecrets`(`kms:Decrypt`, `alias/aws/ssm` 키, 조건 `kms:ViaService = ssm.ap-northeast-2.amazonaws.com`) (research R7).
- [X] T007 `terraform fmt -recursive`, `tms-serving`·`tms-app` `validate`.

## Phase 3: US1 - Google 로그인·로그아웃 (P1) 🎯

**목표**: 대시보드를 열면 바로 Google, 처음 오면 회원 생성, 로그아웃 동작 그대로.
**독립 확인**: quickstart §5 시나리오 1·5, 이메일·비밀번호 로그인 불가(SC-004).

- [X] T008 [US1] `services/dashboard-web/src/auth.ts`: `LOGIN_PROVIDER = "Google"`, `signinArgs = { extraQueryParams: { identity_provider: LOGIN_PROVIDER } }` 내보내기 (research R5).
- [X] T009 [US1] `services/dashboard-web/src/App.tsx`: 모든 `signinRedirect()`에 `signinArgs`를 넘긴다. 로그인 오류 화면의 "다시 로그인"도 같게.

## Phase 4: US2 - 초대 코드 (P1)

**목표**: 자격 없는 회원은 코드 화면, 맞으면 바로 사용, 서버는 자격 없는 요청 거부.
**독립 확인**: quickstart §5 시나리오 2·3·4·6, SC-002·SC-003.

### 서버 (API)

- [X] T010 [P] [US2] `services/dashboard-api/tests/test_auth.py`: `require_member` — `cognito:groups`에 `members` 있으면 통과, 없거나 클레임이 없으면 403 `{"code": "not_member"}`, `AUTH_DISABLED=1`이면 통과. 기존 서명·만료 테스트 유지.
- [X] T011 [US2] `services/dashboard-api/app/auth.py`: `is_member(claims)`, `require_member`, `LoggedInUser`(로그인만), `CurrentUser`(로그인 + `members`). 403 본문은 `{"detail": "초대 코드가 필요하다", "code": "not_member"}` (contracts §5, research R8). 머리 주석에 013 계약 링크.
- [X] T012 [P] [US2] `services/dashboard-api/tests/test_invite.py`: 가짜 SSM·Cognito로 — 맞는 코드 → `AdminAddUserToGroup(members)` 호출·200, 앞뒤 공백·NFC(자모 분리 입력)도 통과, 틀린 코드 400 `invalid_code`, 10분에 6번째 틀림 429 `too_many_attempts`(10분 뒤 다시 허용), SSM 값 없음 503 `not_configured`(통과 없음), 이미 `members`여도 200, 로그에 입력값 없음(caplog) (FR-008·FR-016).
- [X] T013 [US2] `services/dashboard-api/app/invite.py`: `InviteChecker` — SSM `get_parameter(WithDecryption=True)` 5분 캐시(경로는 환경 변수 `INVITE_CODE_PARAM`, 기본 `/tms/app/secret/invite-code`), `normalize`(strip + NFC), `hmac.compare_digest`(UTF-8 바이트), 회원별 10분 5번 시도 제한(메모리), `add_to_members(sub)` (사용자 풀 ID는 `COGNITO_USER_POOL_ID`, username은 토큰의 `username`) (research R6).
- [X] T014 [US2] `services/dashboard-api/app/main.py`: `GET /api/me` → `{"sub", "member"}`(`LoggedInUser`), `POST /api/invite` → contracts §4 응답, 로그는 `sub`·결과만. 모듈 주석의 라우트 규칙을 013 기준으로.

### 서버 (에이전트)

- [X] T015 [P] [US2] `services/dashboard-agent/app/auth.py`: API와 같은 `is_member`·`require_member`·`LoggedInUser`·`CurrentUser` 변경.
- [X] T016 [P] [US2] `services/dashboard-agent/tests/test_auth.py`: T010과 같은 그룹 확인 테스트.

### 화면

- [X] T017 [P] [US2] `services/dashboard-web/src/api.ts`: `apiPost(token, path, body)`, 오류 응답의 `code`를 담는 `ApiError`.
- [X] T018 [US2] `services/dashboard-web/src/Invite.tsx`: 코드 입력·제출, `invalid_code`·`too_many_attempts`·`not_configured` 문구, 성공 시 `onJoined()`.
- [X] T019 [US2] `services/dashboard-web/src/App.tsx`: 로그인 뒤 `/api/me` → `member: false`면 `<Invite>`; 통과 시 `auth.signinSilent()` → 실패하면 `signinRedirect(signinArgs)` → 다시 `/api/me`; 다른 호출에서 403 `not_member`면 `<Invite>` (contracts §1, research R4).

## Phase 5: US3 - 운영 (P2)

- [X] T020 [US3] quickstart §6에 운영 명령 추가: 코드 교체(SSM 값 수정, 5분 안 반영), 자격 빼기(`admin-remove-user-from-group` + 즉시 막을 때 `admin-user-global-sign-out`), 회원 목록.
- [X] T021 [P] [US3] `specs/a-platform/009-service-infra/contracts/app-runtime.md`: 인증 절에 "013부터 `CurrentUser` = 로그인 + members, 화면은 Google 바로 이동" 한 줄과 013 계약 링크.
- [X] T022 [P] [US3] `services/dashboard-api/README.md`·`services/dashboard-agent/README.md`(있으면): 라우트 3종(공개·로그인만·기본)과 로컬 `AUTH_DISABLED`.

## Phase 6: 적용·확인 (사람)

- [ ] T023 🧑 `tms-serving` plan·apply(앱 클라이언트 수정, 그룹 추가) → 관리형 로그인으로 새 Google 계정 회원 생성 확인(research R2).
- [ ] T024 🧑 `tms-app` plan·apply(서버 역할 정책 수정만).
- [ ] T025 🧑 로컬 확인(quickstart §4·§5 시나리오 1~8): API를 실제 Cognito 설정으로, 화면 `npm run dev`.
- [ ] T026 🧑 비밀값 검색(SC-005): `git grep`, `terraform state pull`(두 스택), 서버 로그.
- [ ] T027 🧑 PR 머지 → 배포 → 운영 주소에서 시나리오 1·2·4·6 재확인.
- [ ] T028 🧑 기존 이메일 회원 삭제(quickstart §6), 팀원 안내(초대 코드는 DM) 📨.

## Phase 7: Polish

- [ ] T029 [P] 📨 D 공유: `contracts/auth-api.md`(새 라우트는 `CurrentUser`, `not_member` 처리, `/api/me`), 초대 코드 화면은 D 디자인에 맞춰 바꿔도 됨.
- [ ] T030 spec Status 갱신, 이슈 #64 체크.

## Dependencies & Execution Order

- T001~T003(사람) → T004~T007. T002가 없으면 T023이 실패한다.
- US1(T008·T009)과 US2 서버(T010~T016)는 서로 독립. US2 화면(T017~T019)은 T008·T014 뒤.
- 적용(T023~T028)은 코드가 모두 준비된 뒤. API를 자격 검사 버전으로 배포할 때 화면도 같이 배포해야 기존 회원이 막히지 않는다(T027).

## Parallel Example

```
T006 (tms-app IAM) | T010 (API 그룹 테스트) | T012 (초대 코드 테스트) | T015·T016 (에이전트) | T017 (api.ts)
```

## Implementation Strategy

1. Setup·Foundational(인프라 코드) → US1·US2를 함께 구현(Google을 열면 초대 코드 없이는 누구나 쓰게 되므로 함께 배포).
2. 로컬에서 실제 Cognito로 확인한 뒤 PR.
3. US3 운영 문서는 같은 PR에.
