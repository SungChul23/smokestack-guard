# 상태 모델

- QueryRecord: id, parentQueryId, originalQuestion, canonical candidate, field provenance, created, completedAt, sourceRef, executionMode. completed 기록은 실제 execute 성공 및 deliver 성공 이후에만 추가한다. mode=simulation은 항상 시연으로 표시한다.
- Focus: empty / pending / completed / other / failed. completed의 유효 기록만 상속한다. 독립 질문은 pending/other로 전환한다.
- PendingRequest: id, candidate, authority fingerprint, 생성시각, 실행 준비 판정. READY는 completed가 아니다.
- Patch: operation=PATCH, changes는 time 또는 pollutants 한 필드만 허용. 지원하지 않는 필드를 입력 JSON으로 주입할 수 없다.
- InterveningTurn: id, 원문, kind(acknowledgement/response_preference/processing_status), 생성시각, 당시 focusId. 기본 3턴까지 초점을 유지한다. 새 질의·실패·다른 주제는 이 유형으로 분류하지 않는다. 실제 결과나 질의 완료를 새로 만들지 않는다.
- PresentationPreference: 답변 길이·정중한 표현 같은 선호만 기록하고 전달 어댑터에 제공한다. 조회 대상·기간·물질·집계 조건은 변경하지 않는다.
- Canonical time: point 또는 range. 어제/오늘은 KST 하루 [시작,종료), 전날은 기존 하루 range 기준. 원문 상대 표현도 별도로 남긴다.
