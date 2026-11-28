# Tasks: 에이전트 가드레일 차단 켜기 + 한국어 비속어 단어 보완

**Input**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/)

시험(pytest)은 017과 같이 가짜 응답으로 해석 규칙을 시험한다. 실제 가드레일 시험(`guard_eval.py`)은 사람이 로컬에서 실행한다.

## Phase 1: 해석 규칙 (US1·US2 공통 선행)

- [X] T001 `services/agent-guard/guard_result.py`: `wordPolicy.customWords`·`managedWordLists`를 `Hit(kind="words", name="CUSTOM_WORDS"|목록 type, detail=match)`로 읽고, `KINDS`에 `words` 추가(data-model §3)
- [X] T002 [P] `services/agent-guard/tests/test_guard_result.py`: 단어 정책 해석, 감지만이면 원문 유지, `words` 적용 시 입력·출력 차단 문구, `parse_enforce`가 `words` 허용
- [X] T003 [P] `services/agent-guard/guard_eval.py`: 묶음 `profanity`·`profanity_attached`·`profanity_like_normal`, 기대값 `record`(판정 없이 기록), 비속어 탐지율·적용 목록 기준 차단율 요약
- [X] T004 [P] `services/agent-guard/tests/test_guard_eval.py`: `record` 판정 시험

## Phase 2: 단어 목록 붙이기 — 감지 상태 (US2·US3)

- [X] T005 `infra/stacks/tms-agent-guard/profanity.tf`: 단어 목록(locals)과 넣은 이유·조건부 후보 주석(research R4)
- [X] T006 `infra/stacks/tms-agent-guard/guardrail.tf`: `word_policy_config`(사용자 지정 단어 + 관리형 PROFANITY, 입력·출력 BLOCK)
- [X] T007 `infra/stacks/tms-agent-guard/variables.tf`: `guardrail_enforce` 허용 값에 `words`(기본값은 `none` 유지)
- [X] T008 [P] `services/agent-guard/guard_cases.yaml`: 비속어 14, 붙은 형태 6(record), 겹치는 정상 질문 7
- [X] T009 사람: `terraform plan`(가드레일 in-place, 버전 교체 3 → 4, SSM 버전) → `apply`. 적용 목록은 `none` 그대로(SC-007)

## Phase 3: 실제 가드레일 시험 (US2·US3)

- [X] T010 사람: `guard_eval.py --enforce content,prompt_attack,internal_info,words` 전체 시험 → `eval_results/<날짜>.md`
- [X] T011 시험 결과로 조건부 후보(시발·병신) 결정: `pl01~pl03·pl07` 오탐이면 `profanity.tf`에서 빼고 T009~T010 반복. 결정과 이유를 결과 기록 분석과 research R4에 남김
- [X] T012 성공 기준 확인: 오탐 0(SC-001), 비속어 90%↑(SC-002), 공격·내부 정보 전부(SC-003), 평균 1초 미만(SC-004)

## Phase 4: 차단 켜기 (US1)

- [X] T013 `infra/stacks/tms-agent-guard/variables.tf`: `guardrail_enforce` 기본값 `content,prompt_attack,internal_info,words` (사람 plan(SSM 1개만)·apply는 커밋 뒤)
- [X] T014 [P] `services/agent-guard/README.md`: 시험 기록 표, 현재 적용 목록, 단어 목록 위치·바꾸는 법

## Phase 5: 연결 확인 (US4)

- [X] T015 D에게 [contracts/agent-guard-connection-delta.md](contracts/agent-guard-connection-delta.md) 전달(#66 댓글 초안 → 승인 뒤 게시): 새 `guard_result.py` 복사, `res.blocked` 사용
- [X] T016 D 연결 확인: D 로컬 에이전트에서 "씨발" → CUSTOM_WORDS 차단 문구, "병신이냐?" → INSULTS 차단, 모델 미호출(2026-11-28). 110문장 시험 결과는 research R8
- [ ] T017 Dashboards "에이전트 가드": 차단 기록 `BLOCKED`, 사유 `CUSTOM_WORDS` 확인(SC-005)

## Dependencies

- T001 → T002·T003·T004 → T009(새 해석 규칙 없이 시험하면 단어 정책이 안 보임)
- T005~T008 → T009 → T010 → T011 → T012 → T013
- T015는 T001 이후 언제든, T016·T017은 T013 이후

## 후속 (v6, 2026-11-28)

- [X] T018 D 시험에서 나온 internal_info 오탐 대응: 정의를 좁혀 v6, 시험 `eval_results/2026-11-28.md`. 해결되지 않아 받아들인 오탐으로 기록(research R8)
