# Contract: 로그인·자격 확인 (화면 ↔ API·에이전트 서버)

D가 대시보드·에이전트 라우트를 만들 때 지키는 약속이다. 009 `contracts/app-runtime.md`의 인증 부분을 바꾼다.

## 1. 화면 로그인

- 로그인하지 않았으면 `signinRedirect({ extraQueryParams: { identity_provider: "Google" } })`로 바로 Google에 보낸다.
- 로그인 뒤 `GET /api/me`로 자격을 확인한다. `member: false`면 대시보드 대신 초대 코드 화면을 보여 준다.
- 초대 코드 통과(`200`) 뒤 `signinSilent()`로 새 토큰을 받고 다시 `/api/me`를 부른다. 실패하면 `signinRedirect()`.
- 서버 호출이 `403`이고 `detail.code == "not_member"`면 초대 코드 화면으로 보낸다(`api.ts`의 `ApiError.code`).
- 로그아웃은 지금과 같다(`removeUser` → Cognito `/logout`).

## 2. 서버 라우트 종류

| 종류 | 의존성 | 쓰는 곳 |
|---|---|---|
| 공개 | 없음 | `/health`, `/api/health`, `/api/db-check` |
| 로그인만 | `LoggedInUser` | `GET /api/me`, `POST /api/invite` |
| **로그인 + 자격(기본)** | `CurrentUser` | 그 밖의 모든 API·에이전트 라우트 |

`CurrentUser`의 의미가 "로그인 + `members`"로 바뀐다. D는 새 라우트에 지금처럼 `user: CurrentUser`를 붙이면 된다.

## 3. `GET /api/me` (API)

요청: `Authorization: Bearer <Access 토큰>`

```json
200 {"sub": "1a2b…", "member": true}
```
- `member`는 토큰의 `cognito:groups`에 `members`가 있는지다.
- 토큰이 없거나 틀리면 `401`(지금과 같음).

## 4. `POST /api/invite` (API)

오류 본문은 FastAPI 형식 `{"detail": {"code": ..., "message": ...}}`이다.

```json
요청 {"code": "<사용자가 입력한 값>"}
200  {"member": true}                                                     // 통과, 그룹에 추가됨(이미 members여도 200)
400  {"detail": {"code": "invalid_code", "message": "초대 코드가 맞지 않는다"}}
429  {"detail": {"code": "too_many_attempts", "message": "잠시 뒤 다시 시도"}}   // 10분에 5번 넘게 틀림
503  {"detail": {"code": "not_configured", "message": "초대 코드 설정이 없다"}}  // SSM 값을 못 읽음 → 통과 없음
```
- 입력 앞뒤 공백은 무시하고 유니코드 NFC로 맞춘 뒤 비교한다(상수 시간).
- 로그에는 `sub`와 결과(`ok`·`invalid`·`limited`)만 남기고 입력값은 남기지 않는다(FR-016).

## 5. 자격 없는 요청

`CurrentUser` 라우트에 `members`가 없는 토큰이 오면:
```json
403 {"detail": {"code": "not_member", "message": "초대 코드가 필요하다"}}
```

## 6. 로컬 개발

`AUTH_DISABLED=1`이면 로그인·자격 확인을 모두 건너뛰고 `{"sub": "local-dev", "member": true}`로 본다. 운영 서버에는 넣지 않는다.
