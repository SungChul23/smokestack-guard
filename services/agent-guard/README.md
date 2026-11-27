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
- 감지만/차단은 SSM `/tms/app/config/guardrail-enforce`로 정한다. 지금은 `content,prompt_attack,internal_info,words`(018부터 차단), `tamper_request`·`grounding`은 감지만. 개인정보 가림은 항상.
- 한국어 비속어 단어 목록: `infra/stacks/tms-agent-guard/profanity.tf`(30개 이하, 띄어쓰기 단위로 통째로 같은 단어만 잡음). 바꾸면 새 가드레일 버전 → 시험(`--only profanity,profanity_attached,profanity_like_normal`) → 기록.
- D의 입력 가드 코드는 저장소에 넣지 않는다. 두 겹 비교는 `--regex-guard <로컬 경로>`.
- 시험 문장의 개인정보는 가짜 값만 쓴다.

## 차단으로 바꾸기 (운영 감지를 본 뒤)

1. Dashboards "에이전트 가드" → "감지만 된 기록"에서 정책별로 오탐이 없는지 본다.
2. 오탐 없는 정책만 적용 목록에 넣는다: `variables.tf`의 `guardrail_enforce` 기본값을 바꿔 커밋하고 apply(급할 때는 `-var 'guardrail_enforce=…'`) (`infra/stacks/tms-agent-guard`). `tamper_request`는 넣지 않는다(research R3a).
3. 가드레일 버전은 바뀌지 않고 SSM 값만 바뀐다. 에이전트는 다음 설정 읽기 때(최대 5분) 반영한다.
4. 되돌리기: 같은 명령으로 목록에서 빼거나 `none`.
5. 시험 도구로 미리 볼 때: `guard_eval.py --enforce prompt_attack,content` — 판정(오탐·놓침)은 같고 내보낼 문장(`text_out`)만 바뀐다.

## 시험 기록

| 파일 | 버전 | 요약 |
|---|---|---|
| `eval_results/2026-11-25.md` | 1 | 오탐 2·놓침 5, 모두 `tamper_request` |
| `eval_results/2026-11-25-2.md` | 2 | 주제 정의를 바꿨으나 오탐 3·놓침 8 — 되돌림 |
| `eval_results/2026-11-25-3.md` | 3 | v1 문구. `tamper_request` 외 오탐 0, 공격·내부 정보 14/14 |
| `eval_results/2026-11-27.md` | 4 | 018 단어 18개. 비속어 12/14, 붙은 형태 못 잡음 확인 |
| `eval_results/2026-11-27-2.md` | 5 (확정) | 단어 28개. 비속어 20/20, 공격·내부 정보 14/14, 받아들인 오탐 1("시발 운행") → 차단 켬 |

명령 순서: [quickstart](../../specs/a-platform/017-agent-guardrail/quickstart.md)

```bash
uv venv -p 3.12 .venv && uv pip install -p .venv -r requirements.txt
.venv/bin/python -m pytest -q
```
