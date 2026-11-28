# Implementation Plan: 에이전트 가드레일 차단 켜기 + 한국어 비속어 단어 보완

**Branch**: `93-a-에이전트-가드레일-차단-켜기-한국어-비속어-단어-보완-018` | **Date**: 2026-11-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/a-platform/018-guardrail-enforce-profanity/spec.md`

## Summary

017의 가드레일(`tms-agent`)에 한국어 비속어 사용자 지정 단어 목록(입력·출력)을 붙이고, 차단 적용 목록의 기본값을 `none`에서 `content,prompt_attack,internal_info,words`로 바꾼다. 순서는 **두 번 apply**다.

1. 단어 목록을 붙인다(새 가드레일 버전, 적용 목록은 `none` 그대로 → 운영 동작 변화 없음). 시험 도구로 `--enforce content,prompt_attack,internal_info,words`를 지정해 차단율·오탐을 본다.
2. 기준을 만족하면 적용 목록 기본값을 바꿔 apply한다(SSM 값만 바뀜, 가드레일 버전 그대로).

응답 해석 규칙(`guard_result.py`)이 단어 정책 결과를 읽도록 고친다. 지금은 단어 정책 결과를 읽지 않아 걸려도 "걸린 것 없음"으로 본다. D는 고친 파일을 다시 복사해 쓴다.

## Technical Context

**Language/Version**: Python 3.12 (시험 도구·해석 규칙), Terraform 1.15.8 + AWS provider 6.74(lock)

**Primary Dependencies**: Amazon Bedrock Guardrails(`ApplyGuardrail`), boto3, pyyaml(시험 도구만)

**Storage**: SSM String 파라미터 3개(017과 같음), 시험 기록 md 파일

**Testing**: pytest(가짜 응답, `services/agent-guard/tests`), `guard_eval.py`(실제 가드레일 호출)

**Target Platform**: AWS ap-northeast-2, 에이전트 서버(EC2)와 개발자 로컬

**Project Type**: 인프라 스택 수정 + 작은 파이썬 모듈 수정

**Performance Goals**: 질문당 검사 지연 평균 1초 미만 유지(017 측정 약 0.3~0.5초)

**Constraints**: 정상 질문 오탐 0. 단어 목록 20개 이하. 운영 에이전트의 차단 동작은 시험 통과 전까지 바뀌지 않음

**Scale/Scope**: 단어 약 15개, 시험 문장 약 30개 추가(017의 70개 + α)

## Constitution Check

| 원칙 | 판정 | 근거 |
|---|---|---|
| I. 수집 연속성 | 통과 | 수집·원본 버킷과 무관 |
| II. 비밀값 비공개 | 통과 | 비밀값 없음. 단어 목록은 공개해도 되는 일반 비속어. 시험 문장에 개인정보 없음 |
| III. 코드로 만들고 적용은 사람이 | 통과 | 단어 목록·적용 목록 모두 Terraform. Claude는 fmt·validate·plan 확인까지, apply는 사람. 새 IAM 권한 없음(017 권한 그대로) |
| IV. 데이터 계약 우선 | 통과 | D와의 약속(해석 규칙, 적용 목록 값, 기록 사유)이 바뀌므로 `contracts/agent-guard-connection-delta.md`로 먼저 정하고 D에게 알린다 |
| V. 정직한 비교 | 통과 | 차단 전·후와 단어 목록 유무를 같은 시험 문장 목록으로 비교하고 기록에 가드레일 버전·적용 목록을 적는다 |
| VI. 설명 가능한 결과 | 통과 | 단어 정책에 걸린 기록은 사유 `words`로 남는다(Dashboards "에이전트 가드") |
| 운영: 비용 | 기록 | 단어 필터는 같은 검사 호출 안에서 처리, 추가 과금 없음(research R2) |

재점검(설계 뒤): 위반 없음. Complexity Tracking 없음.

## Project Structure

### Documentation (this feature)

```text
specs/a-platform/018-guardrail-enforce-profanity/
├── plan.md
├── research.md          # R1~R7
├── data-model.md        # 단어 목록, 적용 목록, 시험 문장 묶음, 기록 사유
├── quickstart.md        # 두 번 apply 순서와 시험 명령
├── contracts/
│   └── agent-guard-connection-delta.md   # D에게: 바뀐 해석 규칙·적용 목록
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
infra/stacks/tms-agent-guard/
├── profanity.tf         # 새: 단어 목록(locals) + 넣은 이유 주석
├── guardrail.tf         # word_policy_config 추가(입력·출력 BLOCK)
└── variables.tf         # guardrail_enforce 기본값·허용 값에 words

services/agent-guard/
├── guard_result.py      # wordPolicy 결과 읽기(kind "words"), ENFORCE_VALUES에 words
├── guard_cases.yaml     # profanity, profanity_like_normal 묶음 추가
├── tests/test_guard_result.py   # 단어 정책 해석 시험
├── eval_results/2026-11-2x.md   # 시험 기록
└── README.md            # 시험 기록 표, 차단 상태 갱신
```

**Structure Decision**: 017의 스택과 서비스 폴더를 그대로 고친다. 새 스택·새 서비스는 없다.

## 적용 순서 (사람이 apply)

| 단계 | 바뀌는 것 | 운영 영향 |
|---|---|---|
| ① 단어 목록 apply | 가드레일 DRAFT 갱신 → 새 버전(v4), SSM `guardrail-version` 3 → 4 | 없음(적용 목록 `none`, 단어 걸림은 감지 기록만) |
| ② 시험 | `guard_eval.py --enforce content,prompt_attack,internal_info,words` | 없음(로컬) |
| ③ 적용 목록 apply | SSM `guardrail-enforce` `none` → `content,prompt_attack,internal_info,words` | 최대 5분 뒤 차단 시작 |
| 되돌리기 | `-var 'guardrail_enforce=none'` apply, 또는 SSM `guardrail-version`을 3으로 | 즉시(다음 설정 읽기) |

## Complexity Tracking

없음.
