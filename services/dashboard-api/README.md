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
