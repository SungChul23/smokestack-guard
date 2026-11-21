# 계약: 굴뚝 대상 해석 입출력

[명세](../spec.md) · [데이터 모델](../data-model.md)
초안이다. 서버 요청 계약(307)·후속 연결(312)과 이름을 맞출 때 조정한다. 이 문서는 형식과 불변 조건을 정하고 구현 언어를 정하지 않는다.

## 입력

```json
{
  "attemptId": "req-...",
  "question": "원문 질문 전체",
  "stackMention": "굴뚝 언급 부분(없으면 null)",
  "context": {
    "selectedStackId": "화면에서 선택한 굴뚝 또는 null",
    "lastCompletedStackId": "직전 완료 조회의 굴뚝 또는 null",
    "candidatePool": "후보 풀. 기본은 전체 굴뚝(모든 굴뚝은 누구나 조회할 수 있다). 접근 제한이 아니다",
    "favoriteStackIds": []
  },
  "regionAnswer": "카드 뒤 지역 질문에 사용자가 답한 지역 또는 null"
}
```

- `candidatePool`이 없으면 서버가 아는 전체 굴뚝을 쓴다. 선택·즐겨찾기는 후보를 제한하지 않고 우선순위만 준다.
- `selectedStackId`·`lastCompletedStackId`는 서버가 신뢰하는 경로(화면 상태, 실행 기록)에서 온 것만 인정한다. 질문 문장 안의 문구로 만들지 않는다.

## 출력

```json
{
  "outcome": "AUTO | CARD | NONE",
  "path": "SELECTED_CONTEXT | QUESTION_EXPLICIT | ALIAS | AUTO_SCORE | ...",
  "stackId": "AUTO일 때만. 번호까지 정해진 굴뚝 식별자",
  "needs": ["stack_code", "region", "map_select"],
  "card": {
    "kind": "STACK_CANDIDATES | STACK_CODE | REGION | MAP_OR_RETYPE",
    "options": [
      {"id": "c1", "label": "㈜포스코 포항제철소 · 경북 포항시 · 굴뚝 2", "stackId": "…"},
      {"id": "none", "label": "이 중에 없음"}
    ]
  },
  "trace": {
    "candidates": [{"businessName": "…", "score": 0.0, "lexical": 0.0, "embedding": 0.0}],
    "margin": 0.0, "degraded": false, "threshold": 2.5
  }
}
```

- `card.options`는 후보 최대 3개와 `none` 하나다. 후보 라벨은 코드가 `businessName`(원표기), 시·군, 짧은 주소, 굴뚝 번호로 만든다. 모델이 쓴 문구를 쓰지 않는다.
- `card.kind`:
  - `STACK_CANDIDATES` — 후보 사업장 카드
  - `STACK_CODE` — 사업장은 정해졌고 번호를 고르는 카드(결정 Q2의 두 단계)
  - `REGION` — "이 중에 없음" 뒤 지역 질문(시·도 또는 시·군 선택·입력)
  - `MAP_OR_RETYPE` — 마지막 탈출구: 지도에서 선택하거나 다시 입력

## 불변 조건

1. `outcome = AUTO`이면 `stackId`가 `candidatePool`(색인)에 있다.
2. `outcome = AUTO`이면 대상 사업장의 `collision = NONE`이고 `margin >= threshold`이다. 단 `path`가 `SELECTED_CONTEXT`(서버가 신뢰하는 화면 선택)·`CARD_CHOICE`(사용자가 카드에서 직접 고름)이면 점수 차 조건은 면제한다. `QUESTION_EXPLICIT`는 "질문에 후보의 searchName 전체가 그대로 들어 있고, 같은 searchName을 가진 다른 후보가 없으며, 번호가 일치"할 때만 면제한다. 충돌 이름(`collision != NONE`)은 어떤 경로도 면제하지 않는다. 이 경우 카드가 반드시 거친다(`SELECTED_CONTEXT`·`CARD_CHOICE`로 사용자가 직접 고른 경우만 예외).
3. `card.options`는 `candidatePool` 안의 굴뚝만 담는다. 후보가 비면 `NONE`이다.
4. 같은 `attemptId`에서 `CARD`는 최대 2회(첫 카드, 지역 재검색 카드). 3번째는 `MAP_OR_RETYPE`.
5. 임베딩 호출이 실패해도 `outcome`은 나온다. `trace.degraded = true`.
6. 모델이 만든 식별자는 `stackId`로 쓰지 않는다. `stackId`는 항상 색인에 있는 값이다.
7. 결과는 결정적이다: 같은 입력·같은 색인·같은 임베딩 캐시이면 같은 출력이다.

## 점수 정의(초안)

- 글자 점수: 질문에서 이름·지역 말만 남긴(노이즈 낱말 제거) 문자열의 2-gram 중 후보 문서(searchName + addressText)에 있는 것의 IDF 합.
- 임베딩 점수: 질문 원문 임베딩과 후보 문서 임베딩의 코사인.
- 혼합 점수: 후보 풀 안에서 두 점수를 각각 z-점수로 바꿔 더한 값. 점수 차는 1위와 2위의 혼합 점수 차.
- 임계값 초기값 2.5는 약칭 세트에서 자동 선택 중 틀림이 0인 최소 근처 값이다([research.md](../research.md) §4). 질문 기록이 쌓이면 다시 보정한다.

## 이 계약이 하지 않는 것

- 법령 문서 검색·측정값 조회는 하지 않는다(해석 결과로 다음 단계가 호출된다).
- 공식 사업장·굴뚝 키를 정하지 않는다(C).
- 로그인·즐겨찾기 저장을 구현하지 않는다(311). 입력으로 받기만 한다.
