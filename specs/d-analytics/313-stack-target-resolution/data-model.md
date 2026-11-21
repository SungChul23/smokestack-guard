# 데이터 모델: 굴뚝 대상 해석

[명세](spec.md) · [계약](contracts/stack-resolution.md)
필드 이름은 초안이다. 공식 사업장·굴뚝 키는 담당 C가 정하므로(원칙 IV), 그 계약이 확정되면 키 필드를 맞춘다.

## StackCandidate — 검색 색인의 한 사업장

| 필드 | 설명 |
|---|---|
| businessName | 카탈로그의 사업장 원표기 그대로(`㈜`·괄호 포함). 카드 표시용 |
| searchName | 법인 표기(㈜·(주)·주식회사·(유)·(사)·(재)·(합))·공백·부호를 뺀 소문자 이름. 괄호 안 내용은 넣지 않는다 |
| searchAliases | 음차 변환표로 만든 보조 표기(SK↔에스케이, LG↔엘지, GS↔지에스 등)와 초성 문자열 |
| province | 시·도 |
| city | 주소의 앞 두 토큰(시·군) |
| addressText | 주소 전체(검색 색인용)와 카드 표시용 짧은 주소 |
| siteIds | 사이트 식별자 목록(이름 하나가 여러 사이트에 걸치면 둘 이상) |
| stackCodes | 이 사업장의 굴뚝 번호 집합 |
| stackIds | 번호별 굴뚝 식별자 |
| collision | 충돌 이름 표시: `NONE`, `LEGAL_FORM_ONLY`(법인 표기만 다름), `MULTI_SITE`(사이트 여러 곳), `SUB_SITE`(괄호로만 구분) |
| vector | 이름+주소 임베딩(선택, 없을 수 있음) |

충돌 표시는 색인 생성 때 계산한다. `collision != NONE`이면 점수와 무관하게 자동 선택하지 않는다.

## ResolutionAttempt — 해석 시도 기록 (원칙 VI)

| 필드 | 설명 |
|---|---|
| attemptId | 요청 식별자. 부모 요청과 연결한다(307·312와 같은 방식) |
| text | 해석에 쓴 원문 굴뚝 말(질문 전체가 아니라 굴뚝 언급 부분과 전체 질문 둘 다 보관) |
| context | 입력 맥락: 화면 선택 굴뚝, 직전 완료 조회 굴뚝, 즐겨찾기 |
| stackNumbers | 질문에서 뽑은 굴뚝 번호들(없으면 빈 목록) |
| candidates | 순위 목록: businessName, stackId(번호가 있을 때), score(글자·임베딩·혼합), reasons |
| margin | 1·2위 혼합 점수 차 |
| outcome | `AUTO` · `CARD` · `NONE` |
| path | `SELECTED_CONTEXT` · `QUESTION_EXPLICIT` · `ALIAS` · `AUTO_SCORE` · `CARD_CHOICE` · `REGION_RETRY` · `MAP_SELECT` · `RETYPED` · `ABANDONED` |
| degraded | 임베딩을 못 써서 글자 검색만 쓴 경우 true |
| chosenStackId | 최종으로 쓰인 굴뚝. 없으면 null |

## StackAlias — 확인된 별칭

| 필드 | 설명 |
|---|---|
| normalizedPhrase | 굴뚝 언급을 정리한 값(법인 표기·공백·부호 제거, 번호 제외) |
| stackId 또는 businessName | 사용자가 카드에서 고른 대상. 번호는 사용 시 질문에서 받는다 |
| scope | `USER` 또는 `SHARED` (결정 Q1) |
| confirmedAt, confirmCount, distinctUsers | 확인 시각과 횟수 |
| status | `ACTIVE` · `PROPOSED`(공유 승격 후보, 사람 승인 대기) · `REVOKED` |

규칙: 충돌 이름의 별칭은 있어도 카드를 거친다.

## 상태 전이

`질문 수신 → 후보 풀 정리(전체 굴뚝에서 시작, 번호가 있으면 번호로 줄이고 선택 맥락은 우선순위로만 쓴다) → 점수 계산 → (AUTO | CARD | NONE)`
- `CARD` → 사용자 선택 → `AUTO` 취급으로 진행 + 별칭 기록.
- `CARD`/`NONE` → "이 중에 없음" → 지역 질문 → 후보 재검색 1회 → `CARD` 또는 `MAP_SELECT`/`RETYPED`.
- 같은 질문에서 카드는 두 번까지만(첫 카드, 지역 재검색 카드). 세 번째는 지도 선택 안내.
