# 조사와 결정

- 결정: 자체 OAuth 구현 대신 oidc-client-ts를 번들링한다. state·nonce·PKCE·갱신 로직을 재구현하지 않는다.
- 근거: 기존 S3 로그인 앱도 OIDC UserManager 계열 라이브러리와 Cognito를 사용한다. React로 관제 전체를 바꿀 필요 없이 Vanilla JS로 연결할 수 있다.
- 대안: 축소 React 번들 직접 수정은 소스 재현성이 낮아 제외. 비밀번호 직접 수집 UI는 범위 밖이다.
- callback/logout은 기존 앱과 동일한 `${location.origin}/`. Cognito DescribeUserPoolClient 권한 부족으로 허용 목록은 미확인이다.
- 공식 자료: https://docs.aws.amazon.com/cognito/latest/developerguide/using-pkce-in-authorization-code.html
- 라이브러리: https://authts.github.io/oidc-client-ts/classes/UserManager.html
- UI: 기존 버튼·dialog 유지. 오류는 재시도로 처리하며 자동 이동 반복·가짜 계정 선택은 제공하지 않는다.
