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
