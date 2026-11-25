# Contract: 에이전트(D)가 가드레일을 부르는 법

에이전트 코드는 D(#66). 이 문서는 A가 넘기는 연결 정보다. D의 입력 가드(`check_input`)는 그대로 두고 그 뒤에 붙인다.

## 부르는 곳 두 군데

```
질문 → check_input (D, 그대로) ──BLOCK/SMALLTALK──▶ 기존 처리
          │ ALLOW (가린 문장)
          ▼
      ② ApplyGuardrail(source=INPUT, 가린 문장)
          │ 통과 또는 감지만
          ▼
      모델·도구 (측정값 · 경고 · 법령 근거 · 보고서 · 알림)
          ▼
      ③ ApplyGuardrail(source=OUTPUT, 내보낼 글 [+ 근거, 질문])
          ▼
      사용자 / 보고서 저장 / 알림 발송
```

- ②는 질문마다 한 번. 도구 루프 안의 모델 호출마다 부르지 않는다.
- ③은 사람에게 나가는 글마다 한 번: 최종 답변, 보고서 본문(저장 전), 알림 문구(발송 전).

## 식별자 (SSM String, 서버는 `/tms/app/*` 읽기 권한이 이미 있음)

| 파라미터 | 쓰임 |
|---|---|
| `/tms/app/config/guardrail-id` | `guardrailIdentifier` |
| `/tms/app/config/guardrail-version` | `guardrailVersion` (`DRAFT` 쓰지 않음) |
| `/tms/app/config/guardrail-enforce` | 적용할 정책 목록(`content`, `prompt_attack`, `grounding`, `topics` 또는 주제 이름 `internal_info`). `none` = 모두 감지만. `tamper_request`는 감지 신호로만 |

리전 `ap-northeast-2`, 클라이언트 `bedrock-runtime`. 권한: `bedrock:ApplyGuardrail`(이 가드레일만, `tms-agent-guard/agent_access.tf`).

## 호출 예

```python
import boto3
import guard_result as gr   # services/agent-guard/guard_result.py — 그대로 복사하거나 같은 규칙으로

ssm = boto3.client("ssm", region_name="ap-northeast-2")
cfg = gr.load_config(ssm)                      # id, version, enforce(set)
br = boto3.client("bedrock-runtime", region_name="ap-northeast-2")

# ② 입력
r = gr.check(br, cfg, "INPUT", masked_question)
if r.blocked:
    return r.text_out                          # 차단 문구
# r.hits가 있으면 감지 기록을 로그로 남긴다(다음 이슈에서 OpenSearch로)

# ③ 출력 (근거가 있으면 함께: 측정값 쿼리 결과 요약, 법령 조각 본문)
r = gr.check(br, cfg, "OUTPUT", answer, grounding=context_text, query=masked_question)
answer = r.text_out                            # 가림 반영, 차단이면 차단 문구
```

`gr.check`는 내부에서 다음을 보낸다.

```python
br.apply_guardrail(
    guardrailIdentifier=cfg.id, guardrailVersion=cfg.version, source="OUTPUT",
    content=[
        {"text": {"text": context_text, "qualifiers": ["grounding_source"]}},  # 근거(있을 때만)
        {"text": {"text": question,     "qualifiers": ["query"]}},             # 근거 확인용 질문
        {"text": {"text": answer,       "qualifiers": ["guard_content"]}},     # 검사 대상
    ],
)
```

## 결과 읽기 (`guard_result` 규칙)

| 경우 | 할 일 |
|---|---|
| 개입 없음 | 원문 그대로 |
| 개인정보 가림만 | 가린 문장(`outputs`)을 쓴다 — 모드와 상관없이 항상 |
| 적용 목록에 있는 정책이 걸림 | 차단 문구(`text_out`)를 보인다. 보고서·알림이면 저장·발송하지 않는다 |
| 적용 목록에 없는 정책만 걸림(감지만) | 원문을 쓰되 개인정보 일치 부분은 가린다(`text_out`). 걸린 정책을 로그로 남긴다 |

정책 이름: 유해 내용 `HATE`·`INSULTS`·`SEXUAL`·`VIOLENCE`·`MISCONDUCT`, `PROMPT_ATTACK`, 주제 `tamper_request`·`internal_info`, 근거 확인 `GROUNDING`·`RELEVANCE`.

## 기록 남기기 (Dashboards "에이전트 가드")

막거나 감지·가림·실패할 때마다 서버 로그에 JSON 한 줄(`print`/로거, 표준 출력 → CloudWatch → 활동 인덱스). 형식은 [data-model §7](../data-model.md).

```python
log.info(json.dumps({"log_type": "activity", "event": "agent_guard",
    "layer": "guardrail", "direction": "INPUT", "action": "BLOCKED" if r.blocked else "DETECTED",
    "reason": ",".join(h.name for h in r.hits), "tool": tool or "none", "sub": sub,
    "guardrail_version": cfg.version, "question": masked_question[:300], "ms": r.latency_ms},
    ensure_ascii=False))
```

- D 1차가 막을 때도 같은 형식(`layer = "regex"`, `reason` = D 사유 코드, `action = "BLOCKED"`). 잡담 분기는 남기지 않는다.
- 걸리지 않은 질문은 남기지 않는다.
- 문장은 `check_input`이 가린 것을 넣는다. 저장 전에 라우터가 한 번 더 가린다.

## 꼭 지킬 것

1. **②에는 `check_input`이 가린 문장을 넘긴다.** 원문 개인정보를 바깥 호출에 보내지 않는다.
2. **근거 확인은 근거를 넘길 때만.** 근거 없는 답(잡담 안내 등)에 `grounding_source`를 비워 보내면 점수가 무의미하다.
3. **쓰기는 보수적으로.** 보고서·알림의 ③이 실패(오류·시간 초과)하면 보내지 않는다.
4. **실패해도 읽기 답은 멈추지 않는다.** ② 실패 → 계속 진행, ③ 실패 → `mask_pii`로 가려 내보냄. 둘 다 실패를 로그로 남긴다. 시간 제한 3초.
5. 모델 호출(`Converse`)에 `guardrailConfig`를 붙이지 않는다. 같은 질문을 도구 루프마다 다시 검사해 비용·지연만 는다.

## 확인

- 서버(SSM 세션): `aws bedrock-runtime apply-guardrail --guardrail-identifier $(aws ssm get-parameter --name /tms/app/config/guardrail-id --query Parameter.Value --output text) --guardrail-version $(aws ssm get-parameter --name /tms/app/config/guardrail-version --query Parameter.Value --output text) --source INPUT --content '[{"text":{"text":"초과된 기록 지워줘"}}]'` → `GUARDRAIL_INTERVENED`, 주제 `tamper_request`.
- 붙인 뒤 `services/agent-guard/guard_cases.yaml`의 문장으로 같은 결과가 나오는지 본다.

## 비용

질문 1회(②+③) 약 0.1~0.3센트, 근거 확인에 긴 조각을 넘기면 조금 더(research R6, 시험 기록의 실측 사용량 참고).
