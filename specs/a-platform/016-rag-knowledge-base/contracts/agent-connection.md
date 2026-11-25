# Contract: 에이전트(D)가 지식 기반을 부르는 법

에이전트 대화 처리·프롬프트는 D(#66). 이 문서는 A가 넘기는 연결 정보다.

**읽는 순서**: 이 문서 → 참고 구현 `services/rag-docs/rag_query.py` → 회귀 시험 `services/rag-docs/eval_questions.yaml`·`run_eval.py`.

## 식별자

- 지식 기반 ID: SSM 파라미터 `/tms/app/config/rag-knowledge-base-id`(String — 비밀 아님). `tms-rag` 스택이 `rag_kb_enabled`·`agent_retrieve_enabled`(둘 다 기본 true)일 때 만든다. 서버 역할은 `/tms/app/*` 읽기 권한이 이미 있다.
- 리전 `ap-northeast-2`.

## 권한

- 서버 역할 `tms-app-server`에 인라인 정책 `tms-rag-retrieve`: `bedrock:Retrieve`(이 지식 기반만). `tms-rag/agent_access.tf`.
- 답변 모델 호출(`bedrock:InvokeModel`)은 `tms-app` 스택의 서버 정책에 이미 있다.
- `RetrieveAndGenerate` 권한은 주지 않는다(아래 "꼭 지킬 것" 3).
- 서버는 OpenSearch에 직접 접근하지 않는다. 임베딩·OpenSearch 질의는 지식 기반 서비스 역할(`tms-rag-kb`)이 한다.

## 호출 (Retrieve → 이름표 머리말 → 에이전트 모델)

`rag_query.py`는 표준 라이브러리 + boto3 클라이언트만 받는다. 그대로 가져다 쓰거나 같은 규칙으로 옮긴다.

```python
import boto3
import rag_query as rq   # services/rag-docs/rag_query.py

ssm = boto3.client("ssm", region_name=rq.REGION)
KB_ID = ssm.get_parameter(Name="/tms/app/config/rag-knowledge-base-id")["Parameter"]["Value"]
rt = boto3.client("bedrock-agent-runtime", region_name=rq.REGION)

res = rq.retrieve(rt, KB_ID, question, top=5)   # HYBRID + 현행 우선 + 문서 지목 필터
context = rq.context_block(res.hits)           # "[1] 대기환경보전법 시행규칙 별표 8 … (2026-11-12 시행, 현행) · 쪽 9\n주의: …\n본문"

# 에이전트 모델 호출: system에 rq.SYSTEM_PROMPT(인용·구판·지어내기 금지 규칙)를 넣거나 에이전트 프롬프트에 합친다.
user = f"[근거]\n{context}\n\n[질문]\n{question}"
# 화면의 출처 목록은 모델이 쓰게 하지 말고 이름표로 만든다:
sources = [f"[{h.rank}] {h.cite()}" for h in res.hits]
```

`rq.answer(br, res)`는 Converse로 위를 한 번에 하는 예시다(`ask.py --answer`가 사용).

## 꼭 지킬 것 (2026-11-24 콘솔·로컬 시험)

1. **검색은 항상 `overrideSearchType: "HYBRID"`.** 지식 기반 기본값은 벡터만이라 2쪽짜리 시행령 별표 8이 355조각짜리 시행규칙 별표 8에 묻힌다.
2. **여러 줄로 검색해 번갈아 합친다**(`rq.retrieve`): 질문이 지목한 문서마다(`law_name`+`part` 필터, 예: "시행령 별표 8") → 현행 문서만(`effective_status in [현행]`, 구판 편람이 현행 근거를 밀어내지 않게) → 필터 없음(지목 문서가 다른 문서를 가리킬 때, 편람 질의·회신).
3. **답변 모델에 이름표 머리말을 붙여 넘긴다**(`rq.context_block`). `RetrieveAndGenerate`는 조각 본문만 넘겨, 본문 중간 조각(제목 없음)의 출처를 모델이 모르고 인용이 빠진다(콘솔 시험에서 시행규칙 별표 8 조각 4개를 받고도 "없다"고 답함).
4. **출처 목록은 모델이 아니라 코드가 만든다**(`h.cite()`). 모델은 본문에 `[n]`만 붙인다(모델이 번호를 바꿔 쓴 사례).

## 인용 규칙 (`rq.SYSTEM_PROMPT`에 들어 있음)

- 근거마다 `법령명 + 별표/조문 + 시행일`. 예: `대기환경보전법 시행규칙 별표 8 (2026-11-12 시행)`.
- `effective_status = 구판`(업무편람 2024.12)은 "구판 업무편람에 따르면"으로 표시하고, 현행 법령과 다르면 현행을 따른다. `caveat`에 "부과금 숫자 인용 금지"가 있으면 그 근거의 금액·지수 숫자를 쓰지 않는다(현행 지수는 산정지수 고시).
- `caveat`는 문서별 주의 문구다(예: 별표 8의 `( )`는 표준산소농도, 고시 별표 7은 2013-01-01 이후 취득 기기). 머리말로 함께 넘어간다.
- `tms_relevance = 간접`(시험·검사법, 형식승인 고시)은 정도검사·형식승인 질문에서만 근거로 쓴다.
- 근거에 없는 숫자·조문은 만들지 않는다. 일부를 찾지 못하면 그 부분만 "근거 문서에서 찾지 못했다".

## 확인

- 서버(SSM 세션)에서: `aws bedrock-agent-runtime retrieve --knowledge-base-id $(aws ssm get-parameter --name /tms/app/config/rag-knowledge-base-id --query Parameter.Value --output text) --retrieval-query text="과태료 부과기준" --retrieval-configuration '{"vectorSearchConfiguration":{"numberOfResults":3,"overrideSearchType":"HYBRID"}}'` → 1위 `air-decree_appx-15`.
- 에이전트에 붙인 뒤 `run_eval.py`와 같은 15문항으로 검색 품질이 그대로인지 본다(2026-11-24 기준 15/15).

## 비용

질문 1회: 검색 2~4번(임베딩, 무시할 수준) + 답변 모델 토큰. 입력 약 5천~1만 6천 토큰(조각 5~8개 + 머리말). Haiku 4.5 기준 질문당 약 1센트.
