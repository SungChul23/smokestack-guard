# dashboard-web

대시보드 화면(React + Vite). 지금은 배포 길을 확인하는 빈 페이지이고, D가 이 폴더에서 이어서 개발한다.

- 주소: https://smokestack-guard.store (CloudFront + 비공개 S3)
- 배포: 이 폴더가 바뀐 커밋이 main에 머지되면 `.github/workflows/dashboard-web.yml`이 빌드해 S3에 올리고 `index.html` 캐시를 비운다. PR에서는 빌드만 한다.
- 캐시: 해시가 붙은 파일은 1년, `index.html`은 캐시하지 않는다. 화면 안 경로(예: `/stacks/123`)는 CloudFront가 `index.html`로 돌려준다.
- 서버 주소: `https://api.smokestack-guard.store` (`/api/*`, `/agent/*`). 로그인은 Cognito 관리형 로그인(값은 `infra/stacks/tms-serving` 출력).

## 네이버 지도

- 지도 윗줄의 `관제 | 일반 | 위성`으로 관제 지도(기본)와 네이버 지도를 바꾼다. 코드는 `src/map/naver/`.
- 네이버 Client ID는 **브라우저 공개용 앱 ID**(Client Secret 아님)라 `src/map/naver/config.ts`에 기본값으로 둔다. 환경 변수 `VITE_NAVER_MAP_KEY_ID`가 있으면 그 값을 쓴다(덮어쓰기용, 배포 설정에 추가할 필요 없음).
- 보호는 키가 아니라 **네이버 클라우드 콘솔의 Web 서비스 URL**이 한다. 인증이 통과하려면 거기에 `http://localhost:5173`과 운영 도메인(`https://smokestack-guard.store`)이 등록돼 있어야 한다. 아니면 지도에 "허용된 도메인인지 확인" 안내가 뜨고 관제 지도를 계속 쓴다.
- SDK는 네이버를 처음 고를 때 한 번만 읽는다. 실패(시간 초과·스크립트 오류·인증)해도 관제 지도는 그대로 쓸 수 있다.

## 로컬

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # dist/
```
