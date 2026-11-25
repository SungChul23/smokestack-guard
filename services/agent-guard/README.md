# agent-guard

에이전트 입력·출력을 2차로 검사하는 Bedrock 가드레일의 응답 해석 규칙과 시험 도구다. 설계: [specs/a-platform/017-agent-guardrail](../../specs/a-platform/017-agent-guardrail/spec.md)

```
질문 → ① D 정규식 check_input (#66, 그대로) → ② 가드레일 입력 검사
     → 모델·도구 → ③ 가드레일 출력 검사 → 사용자 · 보고서 · 알림
     걸린 것 → 활동 기록 한 줄(event=agent_guard) → OpenSearch → Dashboards "에이전트 가드"
```

| 파일 | 하는 일 |
|---|---|
| `guard_result.py` | `ApplyGuardrail` 호출과 응답 해석(걸린 정책, 감지만/차단, 개인정보 가림). 에이전트(D)도 같은 규칙 — [연결 문서](../../specs/a-platform/017-agent-guardrail/contracts/agent-guard-connection.md) |
| `guard_cases.yaml` | 시험 문장(통과해야 할 것, 막혀야 할 것, 가려야 할 것) |
| `guard_eval.py` | 시험 문장을 가드레일 단독으로 검사 → 표·오탐·놓침·요약 → `eval_results/<날짜>.md` |

- 가드레일·SSM 설정·서버 권한은 `infra/stacks/tms-agent-guard`(Terraform).
- 감지만/차단은 SSM `/tms/app/config/guardrail-enforce`로 정한다. 처음은 `none`(모두 감지만). 개인정보 가림은 항상.
- D의 입력 가드 코드는 저장소에 넣지 않는다. 두 겹 비교는 `--regex-guard <로컬 경로>`.
- 시험 문장의 개인정보는 가짜 값만 쓴다.

명령 순서: [quickstart](../../specs/a-platform/017-agent-guardrail/quickstart.md)

```bash
uv venv -p 3.12 .venv && uv pip install -p .venv -r requirements.txt
.venv/bin/python -m pytest -q
```
