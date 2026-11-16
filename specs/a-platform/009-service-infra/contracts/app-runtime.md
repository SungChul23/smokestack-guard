# 계약: 서버 앱이 받는 실행 환경 (A → D)

D가 `services/dashboard-api/`, `services/dashboard-agent/`에서 앱을 만들 때 지켜야 하는 약속이다. 인프라는 이 약속만 보고 앱을 띄운다.

## 컨테이너

| 항목 | 값 |
|---|---|
| 이미지 | 각 폴더의 `Dockerfile`로 빌드, `linux/amd64` |
| 포트 | 컨테이너 안 **8000**에서 HTTP로 듣는다 (TLS는 ALB가 끝낸다) |
| 상태 확인 | `GET /health` → 200 (DB·Bedrock을 부르지 않는 가벼운 응답) |
| 경로 접두사 | API는 모든 경로를 `/api/` 아래에, 에이전트는 `/agent/` 아래에 둔다. ALB는 접두사를 떼지 않는다 (`/health`만 예외) |
| 로그 | 표준 출력·표준 에러. CloudWatch `/tms/app/api`, `/tms/app/agent`로 간다 (14일) |
| 메모리 | 서버 1대 2GB(+스왑 2GB). 모델을 서버 안에서 돌리지 않는다 (Bedrock은 API로 호출) |
| 재시작 | 컨테이너가 죽으면 Docker가 다시 띄운다 |

## 로그인 (US3)

- `/health`와 `/api/health`·`/api/db-check`·`/agent/health`(운영 확인용)만 공개다. **새 라우트는 모두 로그인 필수**로 만든다: 인자에 `user: CurrentUser`(`app/auth.py`).
- 화면은 `Authorization: Bearer <Access 토큰>`을 붙여 부른다(`services/dashboard-web/src/api.ts`의 `apiGet`).
- 로컬 개발에서 검증을 끄려면 `AUTH_DISABLED=1`. 운영 서버에는 넣지 않는다.

## 환경 변수 (서버가 뜰 때 SSM 파라미터에서 읽어 넣는다)

| 변수 | 출처 SSM 파라미터 | 내용 | 비밀 |
|---|---|---|---|
| `AWS_REGION` | (고정) | `ap-northeast-2` | 아님 |
| `COGNITO_USER_POOL_ID` | `/tms/app/config/cognito-user-pool-id` | JWT 검증용 | 아님 |
| `COGNITO_CLIENT_ID` | `/tms/app/config/cognito-client-id` | JWT `aud`/`client_id` 확인용 | 아님 |
| `DB_HOST` | `/tms/app/config/db-host` | RDS 엔드포인트 (DB가 꺼져 있으면 없음) | 아님 |
| `DB_PORT` | (고정) | `5432` | 아님 |
| `DB_NAME` | (고정) | `tms` | 아님 |
| `DB_SECRET_ARN` | `/tms/app/config/db-secret-arn` | 관리자 계정 비밀의 ARN. **값이 아니라 위치**. 앱이 Secrets Manager에서 읽는다 | 위치만 |
| `APP_ORIGIN` | (고정) | `https://smokestack-guard.store` (CORS 허용 출처) | 아님 |

- DB 비밀번호는 30일마다 바뀐다. 앱은 비밀번호를 시작할 때 한 번만 읽지 말고, 연결 실패(인증 오류) 시 다시 읽는다.
- JWT 검증 공개키는 `https://cognito-idp.ap-northeast-2.amazonaws.com/<풀 ID>/.well-known/jwks.json`(NAT로 나감).

## 서버 역할이 가진 권한 (앱이 쓸 수 있는 것)

- `secretsmanager:GetSecretValue` — DB 비밀 1개
- `ssm:GetParameter(s)` — `/tms/app/*`
- `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream` — 처음엔 모든 모델, D·E가 모델을 정하면 좁힌다
- `athena:*Query*` + 결과 버킷 쓰기 + `tms_silver2` 읽기 — **이번 범위 아님**. 필요해지면 D가 요청하고 A가 추가한다
- CloudWatch Logs 쓰기, SSM 관리형 접속(배포 명령 수신)
