# Quickstart: Google 로그인 + 초대 코드 적용·확인

모든 AWS·GCP 작업은 A가 한다. 비밀값은 채팅·저장소·터미널 기록에 남기지 않는다.

## 1. Google Cloud (완료: 2026-11-20)

- OAuth 동의 화면: 외부, 범위 `openid`·`email`·`profile`, 프로덕션 게시, 승인된 도메인 `amazoncognito.com`·`smokestack-guard.store`
- OAuth 클라이언트(웹): JavaScript 원본 `https://smokestack-guard.auth.ap-northeast-2.amazoncognito.com`, 리디렉션 URI `https://smokestack-guard.auth.ap-northeast-2.amazoncognito.com/oauth2/idpresponse`

## 2. 비밀값 등록 (콘솔)

1. Cognito 콘솔 → 사용자 풀 `tms-users` → 소셜 및 외부 공급자 → 추가 → **Google**
   - 클라이언트 ID·시크릿 입력, 승인 범위 `openid email profile`
   - 속성 매핑: `email`→`email`, `email_verified`→`email_verified`, `name`→`name`
2. Systems Manager → 파라미터 스토어(표준 등급)
   - `/tms/auth/google-oauth-client-id` (String)
   - `/tms/auth/google-oauth-client-secret` (SecureString)
   - `/tms/app/secret/invite-code` (SecureString, KMS 키 `alias/aws/ssm`). 값은 A가 정한 문구(한글 가능)

## 3. Terraform (PowerShell)

```powershell
cd infra/stacks/tms-serving; terraform plan   # 앱 클라이언트 공급자 COGNITO → Google(수정), 그룹 members(추가)
terraform apply
cd ../tms-app; terraform plan                 # 서버 역할 정책 수정(AdminAddUserToGroup, kms:Decrypt)
terraform apply
```
- 공급자 `Google`이 없으면 `tms-serving` apply가 실패한다(§2 먼저).
- 확인(R2): 새 Google 계정으로 관리형 로그인에서 Google 로그인 → 회원이 생기는지. 막히면 `allow_admin_create_user_only`를 바꾼다.

## 4. 로컬 확인 (배포 전)

API를 실제 Cognito 설정으로 로컬에서 띄우고(`COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`, AWS 자격 증명), 화면을 `npm run dev`(`http://localhost:5173/`, 콜백 주소에 이미 등록됨)로 연다.

## 5. 시나리오 확인

| # | 할 일 | 기대 |
|---|---|---|
| 1 | 주소 열기 | Cognito 화면 없이 Google 계정 선택(FR-002) |
| 2 | 처음 로그인 | 초대 코드 화면(US2-1) |
| 3 | 틀린 코드 6번 | 5번까지 400, 6번째 429(FR-008) |
| 4 | 맞는 코드 | 다시 로그인 없이 대시보드(SC-002, R4) |
| 5 | 로그아웃 → 로그인 | 코드 다시 안 물음(US2-5) |
| 6 | 자격 없는 토큰으로 API·에이전트 직접 호출 | 403 `not_member`(SC-003) |
| 7 | 코드 교체 후 새 계정에 옛 코드 | 거부, 새 코드 통과(SC-006, 캐시 5분) |
| 8 | `admin-remove-user-from-group` 후 1시간 안 토큰 갱신 | 다시 초대 코드 화면(US3-2) |
| 9 | 비밀값 검색 | 저장소·`terraform state pull`·로그에서 0건(SC-005) |

## 6. 배포·정리

1. PR 머지 → API·에이전트·화면 배포 워크플로(main).
2. 기존 이메일 회원 삭제:
   ```bash
   aws cognito-idp list-users --user-pool-id <풀 ID> --query "Users[?UserStatus!='EXTERNAL_PROVIDER'].Username" --output text
   aws cognito-idp admin-delete-user --user-pool-id <풀 ID> --username <위 이름>
   ```
3. 팀원 안내(Slack): 주소, Google로 로그인, 초대 코드는 DM으로.

## 7. 운영 명령 (A)

```bash
POOL=$(aws ssm get-parameter --name /tms/app/config/cognito-user-pool-id --query Parameter.Value --output text)

# 회원 목록 (Google 회원 username은 google_…)
aws cognito-idp list-users --user-pool-id $POOL --query "Users[].[Username, Attributes[?Name=='email'].Value | [0]]" --output text
aws cognito-idp list-users-in-group --user-pool-id $POOL --group-name members --query "Users[].Username" --output text

# 자격 빼기 (다음 토큰 갱신부터 거부). 바로 막으려면 전체 로그아웃도
aws cognito-idp admin-remove-user-from-group --user-pool-id $POOL --username <google_…> --group-name members
aws cognito-idp admin-user-global-sign-out --user-pool-id $POOL --username <google_…>
```

- 초대 코드 교체: SSM 콘솔에서 `/tms/app/secret/invite-code` 값만 수정한다. 5분 안에 반영되고, 이미 통과한 회원은 그대로다.
- 시연 전: 이 대화·메모 등에 코드가 적힌 적이 있으면 새 값으로 바꾼다.
