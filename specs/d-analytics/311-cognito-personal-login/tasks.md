# 작업 목록: 선택형 Cognito 로그인

## 준비

- [x] T001 `D/frontend-export/tms-frontend/package.json`에 OIDC·번들 도구를 고정하고 기존 S3 설정을 `public/assets/cognito-public-config.js`에 반영한다.

## US1 — 선택형 로그인

- [x] T002 [US1] `src/auth-session.mjs`, `src/cognito-auth.js`, `scripts/build-auth.cjs`에서 자동 이동 없는 세션 초기화·PKCE·콜백·일반 오류 안내를 구현한다.
- [x] T003 [US1] `public/index.html`, `public/ui/auth-status.css`에 인증 번들을 연결하되 비로그인 관제 동작을 유지한다.

## US2 — 개인 설정

- [x] T004 [US2] `public/ui/console-user-preferences.js`에서 담당자 A/B 임시 로그인을 제거하고 실제 sub별 저장·사용자 전환·즐겨찾기 기능을 연결한다. 저장 키는 `tms-personal-preferences-v2:<sub>`이며 favorites는 유효한 중복 없는 코드 배열이다.

## US3 — 종료·만료

- [x] T005 [US3] `src/auth-session.mjs`에 만료·갱신 실패·다른 탭 변경·로그아웃 처리를 연결하고 관제를 유지한다.

## 검증·마무리

- [x] T006 `tests/auth-session.test.mjs`와 `D/frontend-export/audit-cognito.cjs`로 실패·취소·만료·두 사용자 격리 및 기존 16항목 회귀를 검증한다.
- [x] T007 `README.md`, `AUTH_INTEGRATION_KO.md`에 설정·빌드·제약을 기록하고 검증한 파일을 독립 `../tms-frontend` 로컬 폴더에 반영한다. AWS 배포는 하지 않는다.

## 의존성과 구현 전략

T001→T002→T003→T004→T005→T006→T007 순서. US1이 최소 범위다. 세션과 개인 설정이 연결되므로 이번에는 병렬 작업 없이 수행한다. 실제 Cognito 사용자 인증은 허용 주소 확인 뒤 별도 수동 검증이며, 이번 대체 환경 검증과 구분한다.

## 완료 근거

- 명세 품질 확인 7/7, 단위 검증 18/18.
- 실제 OIDC 라이브러리 + 가상 인증 응답 브라우저 검증 19/19. 잘못된 state·nonce 거절, 만료·사용자별 저장·로그아웃을 확인했다.
- 독립 폴더에서 기존 화면 회귀 16/16, JS·로컬 요청 오류 0.
- `D/frontend-export/cognito-browser-final.json`, `browser-cognito-final-independent.json`에 기록했다.
- 실제 사용자 인증·S3 배포·Cognito 설정 변경·Git push는 하지 않았다.
