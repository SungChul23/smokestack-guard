# 실행·검증

`D/frontend-export/tms-frontend` 또는 독립 `tms-frontend`에서:

```text
npm ci
npm run build:auth
npm test
npm run dev
```

비로그인으로 관제가 열리는지 확인한다. 로그인 버튼은 Cognito로 이동해야 한다. 실제 복귀는 현재 origin의 `/`가 Cognito callback/logout 허용 URL에 있어야 한다.

허용 주소 설정은 이번 작업에서 변경하지 않는다. 실패 이후에도 지도·차트를 유지한다. 즐겨찾기는 동일 브라우저만 유지한다. 대체 환경 검증은 실제 사용자 인증 시험이 아니다.
