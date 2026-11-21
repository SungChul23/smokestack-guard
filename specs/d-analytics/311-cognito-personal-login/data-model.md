# 데이터 모델

- AuthSnapshot: status=`loading|anonymous|authenticated|error`, user=`null|{sub,name}`, message=사용자용 일반 안내. 토큰을 노출하지 않는다.
- AuthenticatedUser: sub는 비어 있지 않은 문자열, name은 표시 이름/이메일 또는 '로그인 사용자'.
- Preferences: favorites=존재하는 사업장 코드의 중복 없는 문자열 배열. alerts는 기존 임시 설정 형식이며 외부 발송하지 않는다.
- 저장 키: `tms-personal-preferences-v2:<sub>`. sub 변경 시 이전 UI·메모리를 해제하고 새 사용자 설정만 읽는다.
- 상태: 시작→세션 확인→비로그인/로그인. 콜백 실패→error. 만료/로그아웃/다른 탭 로그아웃→anonymous. 갱신 성공→authenticated.
