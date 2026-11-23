# Contract: 에이전트(D)가 지식 기반을 부르는 법

에이전트 대화 처리·프롬프트는 D(#66). 이 문서는 A가 넘기는 연결 정보다.

## 식별자

- 지식 기반 ID: SSM 파라미터 `/tms/app/config/rag-knowledge-base-id`(표준, 일반 문자열 — 비밀 아님). `tms-rag` 스택이 `rag_kb_enabled=true`일 때 만든다.
- 리전 `ap-northeast-2`.

## 권한

- 서버 역할 `tms-app-server`에 `bedrock:Retrieve`(이 지식 기반만). 답변 생성까지 맡기면 `bedrock:RetrieveAndGenerate` + 답변 모델 `bedrock:InvokeModel`. 스위치 `agent_retrieve_enabled`.
- 서버는 OpenSearch에 직접 접근하지 않는다.

## 호출 (권장: Retrieve 후 에이전트가 답변 생성)

```python
import boto3
rt = boto3.client("bedrock-agent-runtime", region_name="ap-northeast-2")
resp = rt.retrieve(
    knowledgeBaseId=KB_ID,
    retrievalQuery={"text": question},
    retrievalConfiguration={"vectorSearchConfiguration": {
        "numberOfResults": 5,
        "overrideSearchType": "HYBRID",
        "filter": {"in": {"key": "effective_status", "value": ["현행", "구판"]}},
    }},
)
for r in resp["retrievalResults"]:
    text = r["content"]["text"]
    meta = r["metadata"]          # law_name, title_ko, part, effective_date, effective_status, caveat, …
    where = r["location"]["s3Location"]["uri"]
    score = r["score"]
```

## 인용 규칙 (프롬프트에 넣을 것)

- 근거마다 `법령명 + 조문/별표 + 시행일`을 붙인다. 예: `대기환경보전법 시행규칙 별표 8 (2026-11-12 시행)`.
- `effective_status = 구판`(업무편람 2024.12)은 "구판 업무편람에 따르면"으로 표시하고, `caveat`에 "부과금 숫자 인용 금지"가 있으면 금액·지수 숫자를 쓰지 않는다(현행 지수는 산정지수 고시).
- `tms_relevance = 간접`(시험·검사법, 형식승인 고시)은 정도검사·형식승인 질문에서만 근거로 쓴다.
- 근거 조각에 없는 숫자·조문은 만들지 않는다. 찾지 못하면 "근거 문서에서 찾지 못했다"고 답한다.

## 비용

질문 1회: 임베딩(무시할 수준) + 답변 모델 토큰. 조각 5개 × 약 300~1,500토큰이 입력에 들어간다.
