# 로컬 지도 실행 계약

입력은 NavigationCommand 3개 필드뿐이다. 현재 명단·좌표·지도의 존재를 재검사한다. 명령 분류는 기존 공통 analyze/validateCandidate를 사용한다.

`selectSiteForAgent(siteId)`는 필터와 선택 갱신의 좁은 인터페이스다. 없거나 위치 보류인 사업장은 적용하지 않는다. query/statuses를 바꾸면 반환값으로 공개한다.

실행기는 실제 getState().selectedSite와 getMap().getGroups()의 사업장 포함을 확인한다. focusSite의 false는 이미 화면 안에 있는 경우일 수 있으므로 단독 실패 신호로 사용하지 않는다. 적용 후 다른 대상을 선택하면 재시도해 원래 요청으로 끌고 가지 않는다.

입력 변경/닫기/취소는 이후 실행과 안내를 막는다. 이미 적용된 이동은 자동으로 취소하지 않는다. 법령 검색·초과 이력 요청은 이 실행기로 처리하지 않는다.
