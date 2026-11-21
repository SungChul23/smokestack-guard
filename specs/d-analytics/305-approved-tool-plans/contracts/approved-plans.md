# 승인 조합 계약 v1

| recipeId | 단계 | 공유 조건 | 의존성 |
|---|---|---|---|
| single | 기존 허용 단일 도구 | 해당 없음 | 없음 |
| dual_pollutants | aggregate_values × 2 | entity/time/operation | 없음, 물질은 NOx와 SOx 각각 하나 |
| dual_statistics | aggregate_values × 2 | entity/time/pollutants | 없음, mean과 max 각각 하나 |
| warning_documents | warning_evidence → search_documents | 공유 없음 | s2는 s1 성공 뒤 실행 예정 |
| paired_visibility | control_view × 2 | 공유 없음 | s2는 s1 성공 뒤 실행 예정, 서로 다른 물질만 |

현재 single에서 허용된 기간/물질/동작 규칙을 재사용한다. 복합 내부 필드가 조건 검증을 통과해도 recipe와 맞지 않으면 차단한다. 전체 원문의 부정·배제·범위 밖·금지 요청을 분할해서 우회하지 않는다. kg 총량은 농도 대신 계산하지 않고 missingData를 안내한다.

도구 계획은 SQL/API/명령 실행 권한을 포함하지 않는다. LLM 모양 해석안은 검증할 계획 자료이며 원문에서 확정된 조건을 덮어쓰지 못하고 최종 사용자 확인이 필요하다. 문서 topic/lawAsOf는 조회 입력이며 시설별 법적 적용 확정이 아니다.

부분 실패: 독립 집계 하나 실패 시 다른 성공을 partial로 표시한다. 경고 성공/문서 없음은 partial, 경고 실패면 문서 단계는 blocked_dependency로 구분한다. 빈 검색을 읽기 실패로 바꾸거나 실패를 재추정해 성공이라 안내하지 않는다. 이 규칙은 테스트 결과 대조기이며 실제 실행기는 후속 연결이다.
