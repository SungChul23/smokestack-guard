# UI 인증 계약

`window.TmsAuth`: `ready`, `getState()`, `subscribe(callback)`, `signIn()`, `signOut()`을 제공한다. 구독은 초기 상태와 변경된 AuthSnapshot을 받는다. 공개 인터페이스에 JWT·refresh token을 반환하지 않는다.

로그인 버튼만 signIn을 호출한다. 진입·즐겨찾기 안내로 자동 인증 이동하지 않는다. 로그아웃은 local OIDC 세션 제거 후 고정 Cognito logout URL로 이동한다. 복귀 URL은 현재 origin의 `/`다.

콜백: code/state를 함께 받으면 라이브러리에 전달한다. 오류·누락·실패 시 URL의 인증 query를 제거하고 일반 오류를 안내한다. 지도는 유지한다.

관측 데이터 계약 변경 없음. 이후 API 인증은 서버에서 access token을 검증해야 한다.
