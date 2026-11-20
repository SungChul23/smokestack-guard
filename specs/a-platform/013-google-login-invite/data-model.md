# Data Model: Google 로그인 + 초대 코드

새 DB 표는 없다. 상태는 모두 Cognito와 SSM에 있다.

## Cognito 사용자 풀 `tms-users` (009, 수정)

| 항목 | 지금 | 바뀐 뒤 | 누가 |
|---|---|---|---|
| 로그인 공급자 | `COGNITO`(이메일·비밀번호) | **`Google`만** | 공급자 등록은 사람(콘솔), 앱 클라이언트 설정은 Terraform |
| 관리자만 계정 생성 | true | true (외부 공급자 첫 로그인은 막지 않음, R2) | Terraform |
| 그룹 | 없음 | **`members`** | Terraform |
| 회원 | 이메일 계정 몇 개 | Google 회원. 기존 이메일 회원 삭제 | Google 첫 로그인 / 사람 |

### 회원 (Google에서 온 회원)

| 속성 | 값 | 출처 |
|---|---|---|
| `sub` | Cognito 회원 식별자(UUID). 앱이 회원을 구분하는 키 | Cognito |
| username | `google_<Google 계정 번호>` | Cognito 자동 |
| `email` | Google 이메일 | 속성 매핑 `email` → `email` |
| `email_verified` | true | 속성 매핑 `email_verified` → `email_verified` |
| `name` | Google 표시 이름 | 속성 매핑 `name` → `name` |
| 그룹 | 코드 통과 뒤 `members` | API |

### Access 토큰 (서버가 받는 것)

| 클레임 | 서버가 보는 것 |
|---|---|
| `iss`, 서명, `exp`, `token_use=access`, `client_id` | 지금과 같은 검증(009) |
| `cognito:groups` | **`members` 포함 여부** (없으면 클레임 자체가 없을 수 있음) |
| `sub` | 회원 식별(로그, 시도 제한, 앞으로 `app` 표의 키) |

Access 토큰에는 이메일이 없다. 화면은 ID 토큰의 `email`을 쓴다(지금과 같음).

## SSM 파라미터 (모두 사람이 콘솔로 등록, Terraform은 이름만)

| 이름 | 종류 | 값 | 읽는 주체 |
|---|---|---|---|
| `/tms/app/secret/invite-code` | SecureString | 초대 코드(A가 정한 문구, 한글 가능) | 앱 서버(API) |
| `/tms/auth/google-oauth-client-id` | String | Google 클라이언트 ID | 사람(백업) |
| `/tms/auth/google-oauth-client-secret` | SecureString | Google 클라이언트 시크릿 | 사람(백업). 서버는 못 읽음 |

## 회원 상태 흐름

```
(없음) ──Google 첫 로그인──▶ 회원(자격 없음) ──맞는 초대 코드──▶ 회원(members)
                                   ▲                                 │
                                   └──── 사람이 자격 뺌(그룹 제거) ◀──┘
회원(자격 없음)·회원(members) ──사람이 삭제──▶ (없음)
```

## 시도 제한 (서버 메모리)

| 키 | 값 | 수명 |
|---|---|---|
| 회원 `sub` | 최근 틀린 시도 시각 목록 | 10분 창, 5번 넘으면 429. 서버 재시작 시 초기화 |
