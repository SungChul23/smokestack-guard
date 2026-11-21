# dashboard-api

대시보드 API 서버. 지금은 배포 길을 확인하는 최소 앱이고, D가 이 폴더에서 이어서 개발한다.

- 실행 환경 약속(포트, `/health`, `/api/` 접두사, 환경 변수): [contracts/app-runtime.md](../../specs/a-platform/009-service-infra/contracts/app-runtime.md)
- 배포: 이 폴더가 바뀐 커밋이 main에 머지되면 `.github/workflows/dashboard-api.yml`이 이미지를 만들어 켜진 서버에 배포한다. PR에서는 테스트·빌드만 한다.

## 로컬

```bash
pip install -e ".[dev]"
ruff check . && pytest -q
uvicorn app.main:app --reload --port 8000
```

## 로그인·자격 (013)

| 라우트 종류 | 붙이는 것 | 예 |
|---|---|---|
| 공개 | 없음 | `/health` |
| 로그인만 | `user: LoggedInUser` | `/api/me`, `/api/invite` |
| **기본** | `user: CurrentUser` (로그인 + 그룹 `members`) | 그 밖의 모든 라우트 |

자격이 없으면 `403 {"detail": {"code": "not_member", …}}`. 로컬 개발은 `AUTH_DISABLED=1`(로그인·자격 모두 건너뜀, 운영 서버에는 넣지 않음).
약속: `specs/a-platform/013-google-login-invite/contracts/auth-api.md`

## 화면용 읽기 라우트·즐겨찾기 (D, spec 318)

모두 로그인한 회원만(`CurrentUser`). 응답 모양은 `services/dashboard-web/src/data/model.ts`와 같다.

| 라우트 | 내용 |
|---|---|
| `GET /api/sites` | 사업장 목록(굴뚝 포함, 키 `"{사업장}:{굴뚝번호}"`). 10분 캐시 |
| `GET /api/day` | 최신 시각 기준 30분 48칸의 굴뚝별 NOx·SOx 원문(숫자 문자열 또는 상태 문구)과 기준값. 적재가 30분마다라 최신 시각이 같으면 캐시. gzip 응답 |
| `GET/PUT/DELETE /api/favorites[/{대상}]` | Cognito sub 기준 즐겨찾기(`app.user_favorite`) |

- DB 계정은 기본 `tms_app`(IAM 인증). 서버 역할에 `rds-db:connect`가 필요하다. 권한이 열리기 전 임시 확인은 `DB_USER=tms_admin`(관리자 비밀 방식).
- DB가 꺼져 있으면 `503 {"detail":{"code":"db_unavailable"}}`, 관측이 아직 없으면 `404 no_data`.
