# dashboard-web

대시보드 화면(React + Vite). 지금은 배포 길을 확인하는 빈 페이지이고, D가 이 폴더에서 이어서 개발한다.

- 주소: https://smokestack-guard.store (CloudFront + 비공개 S3)
- 배포: 이 폴더가 바뀐 커밋이 main에 머지되면 `.github/workflows/dashboard-web.yml`이 빌드해 S3에 올리고 `index.html` 캐시를 비운다. PR에서는 빌드만 한다.
- 캐시: 해시가 붙은 파일은 1년, `index.html`은 캐시하지 않는다. 화면 안 경로(예: `/stacks/123`)는 CloudFront가 `index.html`로 돌려준다.
- 서버 주소: `https://api.smokestack-guard.store` (`/api/*`, `/agent/*`). 로그인은 Cognito 관리형 로그인(값은 `infra/stacks/tms-serving` 출력).

## 로컬

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # dist/
```
