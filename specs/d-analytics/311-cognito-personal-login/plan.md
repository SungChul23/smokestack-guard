# 구현 계획: 선택형 Cognito 로그인

**작성일**: 2026-11-16 · **명세**: [spec.md](spec.md) · 브랜치 변경 없음.

## 요약

로그인 없이 관제를 유지한다. 기존 로그인 버튼에서 Cognito Authorization Code + PKCE 로그인을 시작하고 복귀 시 세션을 복원한다. 담당자 A/B 임시 인증은 제거한다. 즐겨찾기·임시 알림 설정은 실제 sub별 브라우저 저장으로 연결한다.

## 기술 환경

- HTML/CSS/JavaScript 정적 프론트, Node 20 이상 개발 서버.
- oidc-client-ts 3.5.0: state·nonce·PKCE·콜백·갱신을 라이브러리로 처리한다. esbuild 0.28.2: CDN 없이 브라우저에서 쓰도록 번들링한다. 운영은 public/ 정적 파일만 필요하다.
- 토큰은 기존 배포와 같은 OIDC localStorage 저장소, OAuth 임시 state는 sessionStorage에 저장한다. 비밀 클라이언트 키는 없다.
- 개인 설정은 `tms-personal-preferences-v2:<sub>` 키로 분리한다. 서버 저장·알림 발송은 연결하지 않는다.
- Node 내장 테스트 + CDP 브라우저 검증. 대체 환경 검증과 실제 인증 시험을 구분한다.

## 원칙 점검

- 수집·Bronze·Silver·모델·스케줄 변경 없음, 수집 공백 위험 없음.
- 공개 ID와 엔드포인트만 코드에 포함. 토큰·비밀번호·개인 이메일 로그 금지.
- AWS 리소스 생성·변경·배포 없음, 신규 AWS 비용 없음.
- 측정값 계약 유지. UI 인증은 API 권한 검증의 대체가 아니며 서버에서 토큰을 별도로 검증해야 한다.
- 명세 품질 확인 7/7. 허용 주소 미확인은 배포 검증 한계로 기록한다.

## 구조

작업본 `D/frontend-export/tms-frontend/`에서 개발 후 독립 로컬 `../tms-frontend/`에 명시 파일만 반영한다.

```text
src/auth-session.mjs             # 상태 전이·콜백·로그인/로그아웃
src/cognito-auth.js              # oidc-client-ts 어댑터
scripts/build-auth.cjs           # 정적 번들 생성
tests/auth-session.test.mjs      # 실패/만료/전환 검증
public/assets/cognito-public-config.js
public/ui/cognito-auth.js        # 번들
public/ui/console-user-preferences.js
public/ui/auth-status.css
```

## 단계 및 완료 조건

설정·세션 → 개인 기능 → 대체 환경·브라우저 회귀 → 독립 폴더 반영 순서다. 실제 로그인은 허용 callback 확인 후 수동 검증으로 남긴다. S3 기존 배포본은 보존한다.
