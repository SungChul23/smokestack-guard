# 대화 세션 계약

입구 start(question, context, morph)는 입력 가드레일을 적용하고 후속 PATCH를 독립 분류보다 먼저 처리한다. 모호/초점 불일치는 CLARIFY, 독립 요청은 기존 분류기에 전달한다. 규칙으로 처리할 수 없는 원문은 기존 LLM 후보 경로를 유지한다.

execute(requestId, context)는 주입된 신뢰 실행기와 전달 콜백이 있어야 동작한다. 같은 활성 준비 요청·TTL·권한·자료 지문을 재확인한다. 실행 결과는 executed=true/status=success/sourceRef, 전달은 delivered=true여야 한다. 실패를 성공으로 바꾸는 사용자 입력 API는 제공하지 않는다.

공개 진단은 getConversationState()로 복사본을 반환한다. 원문/부모/변경 출처/실행모드를 보존하며 실제 결과 본문은 대화 이력에 임의 복사하지 않는다.

서버 인증·실제 DB 스키마·조회 API는 별도 계약이다. 모듈을 브라우저에 묶은 테스트는 인증 경계가 아니다.
