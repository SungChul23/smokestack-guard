# Implementation Plan: 에이전트 가드레일 2차 검사 (생성·ID 전달)

**Branch**: `86-a-에이전트-가드레일-bedrock-guardrails-2차-검사-생성id-전달` | **Date**: 2026-11-25 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/a-platform/017-agent-guardrail/spec.md`

## Summary

**Amazon Bedrock Guardrails** 가드레일 `tms-agent` 하나를 새 스택 `infra/stacks/tms-agent-guard`의 Terraform으로 만든다. 입력·출력 기준을 한 가드레일에 둔다: 유해 내용(불법 행위는 낮음), 프롬프트 공격(입력), 거부 주제 2개(조작 요청·내부 정보), 출력 개인정보 가림(이메일·전화·주민번호·한국 전화 정규식), 근거 확인(0.5/0.5). 한국어 탐지를 위해 **Standard 등급 + 교차 리전 프로필**을 쓴다(research R2).

에이전트 서버는 SSM String 파라미터에서 ID·버전·**적용 모드**를 읽어 `ApplyGuardrail`을 입력(D 정규식 통과 직후)·출력(내보내기 직전)에서 부른다. 감지만/차단은 가드레일 정책이 아니라 **호출하는 쪽 모드 값**으로 정한다(research R3: provider가 주제·근거 확인의 "감지만" 동작을 아직 지원하지 않음). 서버 역할에는 이 가드레일의 `ApplyGuardrail`만 준다.

1차·2차가 막거나 감지한 것은 에이전트가 활동 기록 한 줄(`event = agent_guard`, 가린 질문 앞 300자 포함)로 남기고, 기존 014 라우터가 `activity-*` 인덱스로 보낸다. 라우터는 저장 전에 질문 문장과 한 줄 전체의 개인정보를 한 번 더 가린다. Dashboards에 "에이전트 가드" 화면을 더한다(research R10·R11).

로컬 시험 도구 `services/agent-guard/guard_eval.py`가 시험 문장 목록(`guard_cases.yaml`)을 가드레일 단독으로 검사해 오탐·놓침·지연·사용량 표를 `eval_results/<날짜>.md`로 남긴다. D의 입력 가드 파일 경로를 주면 ①정규식과 ②가드레일을 나란히 비교한다(D 코드는 저장소에 넣지 않음).

## Technical Context

**Language/Version**: Python 3.12(로컬 시험 도구), Terraform ~> 1.15.0, AWS provider ~> 6.0(잠금 6.73.0 — `aws_bedrock_guardrail`의 `tier_config`·`cross_region_config`·필터별 `input_action`/`output_action` 지원 확인)
**Primary Dependencies**: boto3(`bedrock-runtime` ApplyGuardrail, `ssm`), pyyaml(시험 문장), pytest·ruff(개발)
**Storage**: 없음(시험 결과는 저장소의 md 파일)
**Testing**: pytest(결과 해석·채점·표 만들기를 가짜 응답으로), ruff, `terraform fmt`·`validate`·`plan`(사람이 apply), 실제 가드레일 시험(사람 또는 허락 뒤 Claude가 실행, 문장 수십 개 몇 센트)
**Target Platform**: A의 PC(WSL), AWS 서울 리전(가드레일 처리는 교차 리전 프로필의 APAC 리전들)
**Project Type**: 인프라 스택 + 로컬 CLI 시험 도구 + D에게 넘길 연결 계약
**Performance Goals**: 검사 한 번 평균 1초 미만(SC-004)
**Constraints**: 정상 질문 오탐 0(SC-001), 질문당 가드레일 비용 1센트 미만, D 코드 수정·복사 없음, 서버 권한은 이 가드레일 검사만
**Scale/Scope**: 가드레일 1개, 시험 문장 약 60개, 에이전트 질문 하루 수백 건 이하, 가드 기록 하루 수십 건(활동 인덱스 용량 영향 거의 없음)

## Constitution Check

| 원칙 | 판정 | 근거 |
|---|---|---|
| I. 수집 연속성 | 통과 | 수집·원본 버킷과 무관. 새 스택은 가드레일·SSM·IAM 인라인 정책만 |
| II. 비밀값 비공개 | 통과 | 비밀값 없음. 가드레일 ID·버전·모드는 비밀이 아니라 String 파라미터(016 지식 기반 ID와 같은 방식). 시험 문장에 실제 개인정보를 쓰지 않는다(가짜 번호·`example.com`) |
| III. 코드로 만들고 적용은 사람이 | 통과 | 가드레일·버전·SSM·권한 모두 Terraform. 콘솔 가드레일은 시험용이며 코드로 만든 뒤 지운다(quickstart §6). Claude는 `plan`까지. 권한 목록은 research R5 |
| IV. 데이터 계약 우선 | 통과 | D와의 약속(부르는 곳, 넘길 내용, 결과 읽기, 모드, 실패 시 동작)을 `contracts/agent-guard-connection.md`로 먼저 정한다. Silver 계약과 무관 |
| V. 정직한 비교 | 통과 | ①정규식과 ②가드레일은 같은 시험 문장 목록·같은 기대값으로 비교하고, 결과 기록에 가드레일 버전을 적는다 |
| VI. 설명 가능한 결과 | 통과 | 검사 결과마다 걸린 정책·이유를 활동 기록으로 남기고 Dashboards에서 본다 |
| 개인정보(II 확장) | 통과 | 질문 문장은 가드에 걸린 것만, 에이전트와 라우터에서 두 번 가린 앞 300자를 28일. 014 규칙 변경으로 기록(R11) |
| 운영: 비용 | 기록 | 가드레일 자체 상시 비용 없음, 검사한 글자 수만큼 과금. 질문당 입력+출력 약 0.1~0.3센트(근거 확인에 조각을 넘기면 조금 더) → 하루 수백 건이면 하루 1달러 미만(research R6). 시험 1회 몇 센트 |
| 운영: 외부 패키지 | 기록 | pyyaml은 로컬 시험 도구만(rag-docs와 같음). 서버에 새 패키지 없음(boto3만) |

재점검(설계 뒤): 위반 없음. Complexity Tracking 없음.

## Project Structure

### Documentation (this feature)

```text
specs/a-platform/017-agent-guardrail/
├── spec.md
├── plan.md
├── research.md          # 등급·교차 리전, 감지 모드 방식, 정책 값, 권한, 비용
├── data-model.md        # 가드레일 정책 값, SSM 파라미터, 시험 문장·결과 형식
├── quickstart.md        # 콘솔 시험 → apply → 시험 → 서버 확인 → 콘솔 가드레일 삭제
├── contracts/
│   ├── agent-guard-connection.md  # D에게 넘길 호출 방법
│   └── guard-eval-cli.md          # 시험 도구 입력·출력
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
infra/stacks/tms-agent-guard/          # 새 스택
├── backend.tf  versions.tf  variables.tf  outputs.tf
├── guardrail.tf                       # aws_bedrock_guardrail tms-agent + 버전(정책 바뀌면 새 버전)
├── agent_access.tf                    # tms-app-server 역할에 bedrock:ApplyGuardrail(이 가드레일·프로필만)
└── config.tf                          # SSM String: guardrail-id · guardrail-version · guardrail-enforce

services/agent-guard/                  # 새 폴더(A, 017)
├── README.md
├── pyproject.toml  requirements.txt
├── guard_cases.yaml                   # 시험 문장(묶음·방향·기대·출처)
├── guard_eval.py                      # 단독 시험(+ --regex-guard 비교) → 표·요약·기록
├── guard_result.py                    # ApplyGuardrail 응답 해석(에이전트도 같은 규칙으로 옮겨 씀)
├── eval_results/                      # 날짜별 시험 기록 md
└── tests/                             # pytest(가짜 응답)

services/log-search/                   # 기존(014)에 더함
├── router.py                          # 활동 문서의 json.question·message 개인정보 가림
├── tests/test_router.py               # 가림 시험
├── opensearch/index-templates/activity.json   # json.question(text+keyword)·json.ms
└── dashboards/guard.ndjson            # "에이전트 가드" 화면(새)

specs/a-platform/014-log-opensearch/spec.md·data-model.md   # FR-021 변경 반영
AGENTS.md                               # 저장소 구조에 스택·폴더 한 줄씩
```

**Structure Decision**: 가드레일은 RAG만이 아니라 에이전트 전체(측정값·경고·법령·보고서·알림)에 쓰므로 `tms-rag`가 아니라 새 스택 `tms-agent-guard`로 독립 apply한다(AGENTS.md: 스택 = 업무 단위). #84(016)와 파일이 겹치지 않아 따로 머지할 수 있다. 응답 해석 규칙(`guard_result.py`)은 시험 도구와 에이전트가 같은 규칙을 쓰도록 표준 라이브러리만으로 작게 둔다(016 `rag_query.py`와 같은 방식).
