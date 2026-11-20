# Research: Google 로그인 + 초대 코드

## R1. Google 연결은 사람이 Cognito 콘솔에 등록한다

- **Decision**: Google 로그인 공급자(클라이언트 ID·시크릿, 속성 매핑)는 A가 Cognito 콘솔에서 등록한다. Terraform은 앱 클라이언트의 `supported_identity_providers = ["Google"]`로 **이름만** 참조한다. 시크릿 백업은 SSM SecureString `/tms/auth/google-oauth-client-secret`(클라이언트 ID는 String `/tms/auth/google-oauth-client-id`), 사람이 콘솔로 등록한다.
- **Rationale**: `aws_cognito_identity_provider`는 `provider_details.client_secret`을 상태 파일에 평문으로 저장한다. 값을 SSM에서 읽어 넘겨도 마찬가지다(원칙 II, AGENTS.md 비밀값 규칙). 수집 API 키와 같은 방식이다. 백업 경로는 `/tms/app/` 밖이라 앱 서버 역할이 읽지 못한다.
- **Alternatives**: Terraform으로 관리 + 상태 암호화(규칙 위반), Secrets Manager(월 $0.4, 이 값은 교체가 드묾 → SSM 표준 등급으로 충분).
- **순서 제약**: 공급자 `Google`이 없으면 앱 클라이언트 apply가 실패한다. 콘솔 등록 → `tms-serving` apply.

## R2. "관리자만 계정 생성" 설정은 그대로 둔다

- **Decision**: `allow_admin_create_user_only = true`를 유지한다.
- **Rationale**: 이 설정은 자체 가입(SignUp API, 관리형 로그인의 가입 버튼)만 막고, 외부 공급자로 처음 로그인한 사용자는 막지 않는다(Google 첫 로그인 = Cognito 회원 생성). 이메일·비밀번호 가입을 계속 막는 효과가 있다. 공식 문서에 외부 공급자 경우가 명시되어 있지 않아 quickstart §3에서 실제로 확인한다. 막힌다면 `false`로 바꾸고 앱 클라이언트를 Google 전용으로 두어 이메일 가입 경로를 없앤다.
- **Alternatives**: 가입 전 Lambda로 허용 목록 검사(사용자 결정: 누구나 가입, 자격은 초대 코드).

## R3. 서비스 자격 = Cognito 그룹 `members`, Access 토큰의 `cognito:groups`로 확인

- **Decision**: Terraform으로 그룹 `members`를 만든다. 서버는 Access 토큰의 `cognito:groups`에 `members`가 있는지 본다. 초대 코드가 맞으면 API가 `AdminAddUserToGroup`을 부른다.
- **Rationale**: Cognito Access 토큰에는 그룹 클레임이 들어 있어 매 요청 DB·API 조회가 필요 없다. 회원 정보를 한곳(Cognito)에 둔다. 자격 빼기는 `AdminRemoveUserFromGroup` 한 줄이다.
- **Alternatives**: 사용자 정의 속성(`custom:member`, Access 토큰에 기본으로 안 실림), RDS `app` 표(매 요청 조회, DB가 인증 경로에 끼어듦).

## R4. 코드 통과 직후 토큰 갱신 = 갱신 토큰(refresh) 교환

- **Decision**: 화면은 코드 통과 응답을 받으면 `signinSilent()`(oidc-client-ts, 갱신 토큰 교환)로 새 Access 토큰을 받는다.
- **Rationale**: 갱신 토큰으로 받은 새 토큰은 그 시점의 그룹으로 다시 만들어진다(커뮤니티 사례 확인, 공식 명시 없음 → quickstart §5에서 확인). 실패하면 `signinRedirect()`로 다시 로그인(Google 세션이 살아 있어 화면 전환만 한 번).
- **자격을 뺀 경우**: 이미 받은 Access 토큰은 만료(1시간)까지 유효하다. 다음 갱신부터 거부된다(US3-2). 즉시 막아야 하면 `AdminUserGlobalSignOut`을 함께 실행한다.

## R5. Cognito 화면을 건너뛰고 바로 Google로

- **Decision**: `signinRedirect({ extraQueryParams: { identity_provider: "Google" } })`.
- **Rationale**: Cognito 권한 부여 엔드포인트는 `identity_provider` 인자를 받으면 관리형 로그인 화면 없이 그 공급자로 보낸다(FR-002).

## R6. 초대 코드 저장·확인

- **Decision**:
  - 값: SSM SecureString `/tms/app/secret/invite-code`, 사람이 정해 등록·교체. 한글 문구 가능(사용자 결정 2026-11-20: 시연자가 입력하기 쉽게).
  - 서버는 요청 때 읽고 5분 캐시(교체가 5분 안에 반영). 환경 변수로 넣지 않는다(user-data는 `/tms/app/config/`만 환경 변수로 넣음).
  - 입력·정답 모두 앞뒤 공백 제거 + 유니코드 NFC 정규화(맥 등에서 한글이 자모로 나뉘어 오는 경우) 뒤 UTF-8 바이트를 `hmac.compare_digest`로 비교.
  - 틀린 시도 제한: 서버 메모리에서 회원(sub)별 10분에 5번(FR-008). 넘으면 429.
- **Rationale**: 앱 서버 역할이 이미 `/tms/app/*` 읽기 권한을 가진다(SecureString 복호화 권한만 추가). 짧은 문구는 추측될 수 있지만, 대상이 공개 홍보하지 않는 시연용 서비스이고 시도 제한과 즉시 교체로 위험을 낮춘다. 위험은 에이전트 호출 비용이며, 사용자별 호출 제한은 공개할 때 추가한다(범위 밖).
- **Alternatives**: Secrets Manager(비용, 회전 기능 불필요), DynamoDB·RDS로 시도 횟수 공유(이 규모에 과함).

## R7. 서버 권한 추가 (`tms-app` 역할)

| 권한 | 리소스 | 이유 |
|---|---|---|
| `cognito-idp:AdminAddUserToGroup` | 사용자 풀 `tms-users` | 코드 통과 시 그룹 추가 |
| `kms:Decrypt` (조건 `kms:ViaService = ssm.ap-northeast-2.amazonaws.com`) | `alias/aws/ssm` 키 | SecureString 초대 코드 복호화 |

- 사용자 풀 ID는 `tms-serving`이 쓴 SSM `/tms/app/config/cognito-user-pool-id`에서 읽어 ARN을 만든다(스택 사이 원격 상태 참조 없이, 009와 같은 방식).
- 서버는 NAT로 Cognito API에 나간다(JWKS와 같은 길).

## R8. 그룹 확인 위치

- **Decision**: API·에이전트의 `app/auth.py`에 `require_member`(= `require_user` + `members` 확인)를 두고, 기존 `CurrentUser`가 이것을 쓰게 바꾼다. 초대 코드 확인 경로와 `/api/me`는 로그인만 요구하는 `LoggedInUser`를 쓴다.
- **Rationale**: 새 라우트가 기본으로 자격 검사를 받는다(D가 따로 신경 쓰지 않아도 됨). 두 앱의 `auth.py`는 지금도 같은 내용을 따로 가진다(009).
- 로컬 개발 `AUTH_DISABLED=1`이면 그룹 확인도 건너뛴다.

## R9. 기존 회원 정리

- **Decision**: 전환 뒤 A가 `list-users`로 공급자가 `Cognito`인 회원을 찾아 `admin-delete-user`. 팀원에게 Slack으로 새 로그인 안내.
- **Rationale**: 앱 데이터가 없어 연결(AdminLinkProviderForUser)할 이유가 없다.

## R10. 비용

Cognito 사용자 풀은 월 활성 사용자 1만 명까지 무료(Lite/Essentials 무료 구간), 외부 공급자 로그인 포함. 그룹·SSM 표준 파라미터 무료. 추가 비용 0(SC-007).

## 참고

- [Configuring policies for user creation](https://docs.aws.eu/cognito/latest/developerguide/user-pool-settings-admin-create-user-policy.html)
- [Add Google sign-in to Amazon Cognito with an email allowlist](https://realcloudnative.pages.dev/add-google-sign-in-to-amazon-cognito-with-an-email-allowlist/)
- [Understanding user pool JWTs](https://docs.aws.amazon.com/en_us/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-with-identity-providers.html)
- [Refresh tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-refresh-token.html)
