# 정보와 상태

- NavigationCommand: 정확히 tool=`control_view`, action=`select_business`, siteId=등록된 6자리 문자열. 다른 필드 금지.
- PendingRequest: ID·원문·명단 fingerprint·생성시각·후보 ID 집합. TTL=300000ms.
- ApplyReceipt: 적용 여부, 사업장 코드, 완화한 필터(query/statuses), 이미 표시 여부.
- Result: status=success/partial/error/cancelled, executed, applied, site, reason. success는 선택/지도 표시 확인 후만.

상태: 입력→명령 준비/후보 확인/결과 없음→실행 직전 검사→선택/지도 갱신→표시 확인→성공 또는 일부 적용/오류/취소. 취소를 원복으로 표현하지 않는다.
