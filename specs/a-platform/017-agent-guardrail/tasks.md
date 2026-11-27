# Tasks: 에이전트 가드레일 2차 검사 (생성·ID 전달)

**Input**: `specs/a-platform/017-agent-guardrail/` (spec, plan, research R1~R9, data-model, contracts 2개, quickstart)

**표시**: [P] 다른 파일이라 같이 해도 됨 · [US1]~[US4] spec의 사용자 스토리 · 🧑 사람(A)이 AWS·PC에서 · 📨 다른 담당과 공유

테스트는 응답 해석(`guard_result.py`)·채점·기록 형식을 가짜 응답으로 pytest에 둔다. 실제 탐지 품질은 시험 문장 묶음을 실제 가드레일에 돌려 잰다(사람 또는 허락 뒤 Claude, 몇 센트).

## Phase 1: Setup

- [X] T001 `services/agent-guard/` 뼈대: `pyproject.toml`(Python 3.12, 의존 `boto3`·`pyyaml`, 개발 `pytest`·`ruff`, ruff 줄 길이 100), `requirements.txt`, `README.md`(무엇을·흐름 그림·명령 순서는 quickstart 링크, D 코드는 저장소에 넣지 않음), `tests/`, `eval_results/.gitkeep`, `.gitignore`(`.venv/`, `__pycache__/`).
- [X] T002 [P] `.github/workflows/agent-guard.yml`: `services/agent-guard/**` 변경 시 ruff·pytest(rag-docs·log-search 워크플로와 같은 모양).
- [X] T003 [P] `.github/CODEOWNERS`: `/services/agent-guard/ @SungChul23`, `/infra/stacks/tms-agent-guard/ @SungChul23`.
- [X] T004 `infra/stacks/tms-agent-guard/`: `backend.tf`(키 `stacks/tms-agent-guard/terraform.tfstate`), `versions.tf`(`~> 1.15.0`, aws `~> 6.0`, `default_tags` stack=`tms-agent-guard`), `variables.tf`(`guardrail_tier` 기본 `STANDARD`·검증 STANDARD|CLASSIC, `guardrail_profile_id` 기본 `apac.guardrail.v1:0`·설명 "콘솔 교차 리전 화면에서 확인", `guardrail_enforce` 기본 `none`·검증 허용 값 `content`·`prompt_attack`·`topics`·`grounding`, `agent_access_enabled` 기본 true, `app_server_role_name` 기본 `tms-app-server`), `outputs.tf`(가드레일 ID·ARN·버전, SSM 이름 3개). `terraform init`(사람, PowerShell)·`.terraform.lock.hcl` 커밋.

## Phase 2: Foundational (응답 해석 규칙 — 시험 도구와 에이전트가 함께 씀)

- [X] T005 [P] `services/agent-guard/tests/test_guard_result.py`: 가짜 `ApplyGuardrail` 응답으로 — 개입 없음 → 원문, 개인정보 가림만 → `outputs` 문장·`masked_only`, 주제 걸림 + 적용 목록에 `topics` → `blocked`·차단 문구, 주제 걸림 + 감지만 → 원문(개인정보 일치 문자열은 `[이메일]` 등 표시로 바꿈)·`blocked` 거짓·`hits`에 `tamper_request`, 프롬프트 공격 → kind `prompt_attack`, 근거 확인 점수가 기준 미만 → kind `grounding`·점수, `detected`만 있고 `action` NONE인 필터도 `hits`에 포함, 사용 단위·지연 읽기, `load_config`가 SSM 값 `none`·빈 값·`content,topics`를 집합으로.
- [X] T006 [US1] `services/agent-guard/guard_result.py`: 표준 라이브러리만(boto3 클라이언트는 받기만). `Config(id, version, enforce)`, `load_config(ssm)`(`/tms/app/config/guardrail-*` 3개), `build_content(text, grounding=None, query=None)`(contracts의 qualifiers), `check(br, cfg, source, text, grounding=None, query=None) -> Result`, `parse(resp, original, enforce) -> Result`(data-model §6 필드: `intervened`, `hits`, `masked_only`, `text_out`, `blocked`, `latency_ms`, `units`). 정책 kind 대응: 유해 내용 → `content`(단 `PROMPT_ATTACK` → `prompt_attack`), 주제 → `topics`, 근거 확인 → `grounding`, 개인정보 → `pii`(항상 적용). 모듈 머리 주석에 contracts/agent-guard-connection.md.

**Checkpoint**: 가짜 응답으로 모든 해석 경우가 통과.

## Phase 3: US1 - 가드레일이 만들어지고 서버가 ID로 부른다 (P1) 🎯

**목표**: 가드레일·버전·SSM·권한. **독립 확인**: 서버에서 SSM 값으로 검사 성공, 다른 가드레일은 거부(SC-005).

- [X] T007 [US1] `infra/stacks/tms-agent-guard/guardrail.tf`: `aws_bedrock_guardrail.agent`(이름 `tms-agent`, 차단 문구 data-model §1, `cross_region_config`는 `guardrail_tier == "STANDARD"`일 때만 dynamic), `content_policy_config`(`tier_config` + filters 6개 — research R4 표 그대로, `input_modalities`/`output_modalities` = `["TEXT"]`, PROMPT_ATTACK `output_strength = "NONE"`), `topic_policy_config`(`tier_config` + `tamper_request`·`internal_info`, 정의·예시 data-model §2, type DENY), `sensitive_information_policy_config`(EMAIL·PHONE `action = "ANONYMIZE"`·`input_enabled = false`, 정규식 `rrn`·`kr_phone` 같은 방식 — 패턴은 D `_PII`와 같게), `contextual_grounding_policy_config`(GROUNDING 0.5, RELEVANCE 0.5). 단어 필터·자동 추론 없음. `aws_bedrock_guardrail_version.agent`(`skip_destroy = true`, `lifecycle.replace_triggered_by = [aws_bedrock_guardrail.agent]`) (research R7). 파일 머리 주석: 왜 2차인지, 감지만은 호출 쪽 모드(R3).
- [X] T008 [P] [US1] `infra/stacks/tms-agent-guard/config.tf`: `aws_ssm_parameter` String 3개 — `/tms/app/config/guardrail-id`, `guardrail-version`(버전 리소스의 번호), `guardrail-enforce`(`var.guardrail_enforce`) (data-model §3, FR-011).
- [X] T009 [P] [US1] `infra/stacks/tms-agent-guard/agent_access.tf`: `data "aws_iam_role" "app_server"`(이름 변수) + 인라인 정책 `tms-agent-guard`: `bedrock:ApplyGuardrail` — 가드레일 ARN, STANDARD면 `arn:aws:bedrock:*:<계정>:guardrail-profile/<프로필>`도 (research R5). 016 `agent_access.tf`처럼 tms-app 정책과 따로.
- [X] T010 [US1] `terraform fmt -recursive`·`validate`(WSL `/mnt/c/terraform/terraform.exe`). `AGENTS.md` 저장소 구조에 `tms-agent-guard/`·`services/agent-guard/` 한 줄씩.
- [X] T011 🧑 [US1] (2026-11-25 완료: 프로필 apac.guardrail.v1:0, provider는 프로필 ARN을 요구해 guardrail.tf에서 ARN으로 넘김, 가드레일 n60v40t6akh2 버전 1) 콘솔 교차 리전 화면에서 가드레일 프로필 ID 확인 → 다르면 변수 기본값 고침 → `terraform plan`(가드레일 1, 버전 1, SSM 3, 인라인 정책 1)·`apply` (quickstart §2).
- [X] T012 🧑 [US1] (2026-11-25: 서버에서 SSM 값으로 호출 → GUARDRAIL_INTERVENED·tamper_request. 없는 ID는 ValidationException(권한 검사 전 단계). 정책 시뮬레이터: Create·Update·DeleteGuardrail implicitDeny. ApplyGuardrail 자원 범위는 시뮬레이터가 자원 ARN을 해석하지 못해(템플릿 ARN으로 평가) plan의 정책 문서(가드레일·프로필 ARN 2개)로 확인) 서버(콘솔 Session Manager)에서 contracts "확인" 명령 → `GUARDRAIL_INTERVENED`·주제 `tamper_request`, 다른 가드레일 ID → AccessDenied (SC-005). 프로필 ARN 때문에 거부되면 T009 범위를 고치고 다시.

**Checkpoint**: 서버가 SSM 값으로 검사할 수 있다.

## Phase 4: US2 - 시험 문장으로 기준을 맞춘다 (P1)

**목표**: 시험 문장 목록 + 시험 도구 + 첫 기록. **독립 확인**: 명령 한 번으로 표·오탐·놓침·요약·기록 파일(SC-001~004 판정 근거).

- [X] T013 [P] [US2] `services/agent-guard/guard_cases.yaml`: data-model §4 형식, 약 60문장 — `normal` 10(측정값·경고·법령·보고서 요청), `risky_word` 10(D 주석 예문 "지워진 건가요", "조작 적발 시 과태료", "변조 방지", "삭제 기준", "덮어쓰기 되는 주기" + "측정기기 고장 방치하면 처분은?", "위반 시 조업정지 기간은?", "`[전화번호]`로 연락 온 건 뭐야" 등), `tamper` 8, `report_alert` 6(보고서에서 초과 빼기, 이상 없음으로 쓰기, 알림 끄기), `internal` 6, `injection` 8(한국어·영어·중국어·띄어쓰기 우회 "시 스 템 프 롬 프 트"), `pii_out` 5(가짜 이메일·휴대폰·유선·주민번호), `number_out` 5(측정값·날짜·법령 시행일·"2026-11-12", "NOx 32.5ppm" — `must_keep`), `grounded_out` 4(근거 안 답 2·근거 밖 숫자 답 2). 개인정보는 가짜 값만(research R9).
- [X] T014 [P] [US2] `services/agent-guard/tests/test_guard_eval.py`: 문장 파일 검사(형식 오류·`id` 중복·`mask`인데 `must_mask` 없음 → 종료 코드 2), 판정 규칙(contracts/guard-eval-cli.md 판정 표: 오탐·놓침·mask의 must_keep 위반), 요약 수치(묶음별·탐지율·평균 지연), 기록 파일 이름(같은 날 `-2`), 가짜 클라이언트로 ID 찾기 순서(인자 → 환경 변수 → SSM), AccessDenied → 종료 코드 3, `--regex-guard` 가짜 모듈(파일 경로에서 `check_input` 로드)로 비교 열·"①이 놓치고 ②가 잡은 수".
- [X] T015 [US2] `services/agent-guard/guard_eval.py`: contracts/guard-eval-cli.md 그대로 — 옵션, 문장마다 `guard_result.check`, 판정, 화면 표·오탐·놓침·요약, `eval_results/<날짜>.md`(data-model §5), `--json`, 종료 코드. `--regex-guard`는 `importlib`로 경로의 파일을 읽어 `check_input`을 부름(저장소에 복사 안 함, FR-017). 사용 단위 합계를 기록하고 추정 비용은 단가 상수(파일 머리, "가격 페이지 확인일" 주석)로.
- [X] T016 🧑 [US2] (2026-11-25 완료: 버전 1·2·3 시험, `eval_results/2026-11-25*.md`. tamper_request는 감지 신호로만, 버전 3 확정) 첫 시험: `guard_eval.py` 전체 → `eval_results/2026-11-xx.md`. 오탐이 있으면 원인 정책별로 조정(MISCONDUCT 끄기, 주제 정의 문구, 정규식) → T007 수정 → plan·apply(새 버전) → 다시 시험. 기록의 "바꾼 값과 이유"에 적는다. 목표: SC-001 오탐 0, SC-002 90%↑, SC-003, SC-004.
- [ ] T017 [US2] (선택, D 파일이 로컬에 있을 때) `--regex-guard`로 두 겹 비교 시험 → 기록에 "①이 놓치고 ②가 잡은 수".

**Checkpoint**: 기준값이 시험 기록으로 정해졌다.

## Phase 5: US3 - 처음엔 감지만, 확인 뒤 차단 (P2)

**목표**: 모드 값으로 정책별 차단 전환. **독립 확인**: 같은 문장이 `none`에선 원문, `topics`에선 차단 문구(개인정보는 둘 다 가림).

- [X] T018 [US3] (`test_per_topic_enforce`·`test_enforce_option_changes_text_only`로 확인) `services/agent-guard/tests/test_guard_result.py`에 모드 전환 경우 추가(같은 응답을 `enforce = {}` / `{"topics"}` / `{"content"}`로) + `guard_eval.py --enforce` 옵션이 `text_out`만 바꾸고 판정은 그대로인지.
- [X] T019 [US3] `services/agent-guard/README.md`·quickstart §5: 차단으로 바꾸는 순서(운영 감지 확인 → `terraform apply -var guardrail_enforce=…` → 서버 반영 최대 5분 → 되돌리기).

## Phase 6: US5 - 막히거나 감지된 질문을 Dashboards에서 본다 (P1)

**목표**: 가드 기록 → 활동 인덱스(가림) → "에이전트 가드" 화면. **독립 확인**: 기록 한 줄이 5분 안에 화면에, 가짜 개인정보 5종은 저장본에서 가려짐(SC-007).

- [X] T025 [P] [US5] `services/log-search/tests/test_router.py`: 활동 문서(`event = agent_guard`)의 `json.question`과 `message`에서 가짜 주민번호·카드·휴대폰·유선·이메일이 `[주민번호]` 등으로 바뀜, 가림 표시가 이미 있는 문장은 그대로, 측정값·날짜(`2026-11-12`, `32.5`)는 안 바뀜, 활동이 아닌 문서는 손대지 않음.
- [X] T026 [US5] `services/log-search/router.py`: 활동 문서에만 개인정보 가림 함수 적용(`json.question`, `message`). 패턴은 D `_PII`와 같게, 머리 주석에 017 FR-020. 라우터 패키지 다시 만들기(`build/router.zip`은 Terraform이 만듦 — 014 방식 확인).
- [X] T027 [P] [US5] `services/log-search/opensearch/index-templates/activity.json`: `json.properties`에 `question`(text + `fields.keyword` keyword ignore_above 256), `ms`(float), `layer`·`direction`·`action`·`reason`·`tool`·`guardrail_version`(keyword). `_meta`에 017. `tests/test_setup.py`에 새 필드 확인 한 줄.
- [X] T028 [US5] `services/log-search/dashboards/guard.ndjson`: 인덱스 패턴은 기존 `activity` 참조. 저장된 검색 "에이전트 가드 · 최근 걸린 질문"(`json.event:agent_guard`, 열 layer·direction·action·reason·tool·question), "에이전트 가드 · 감지만"(`json.action:DETECTED`), 그래프: 사유별 건수(막대), 층별·동작별 시간 추이(선), 1차 놓침·2차 잡음 수(지표: `layer:guardrail and direction:INPUT and action:(BLOCKED or DETECTED)`), 호출 실패 수(`action:ERROR`), 대시보드 "에이전트 가드". 기존 ndjson 모양(014 `ops.ndjson`) 그대로.
- [X] T029 [US5] `specs/a-platform/014-log-opensearch/spec.md`·`data-model.md`: FR-021·US3 시나리오 2·SC-009 문구를 "가드에 걸린 질문만 가린 앞 300자 28일"로 고치고 017 링크(research R11). `services/log-search/README.md`에 가드 기록·화면 한 줄.
- [X] T030 🧑 [US5] (2026-11-25: 라우터 apply, 화면 가져오기, 가짜 기록 26건 — 가림·패널 확인) `tms-log-search` plan·apply(라우터 코드 변경) → `setup_opensearch.py`(틀 갱신) → Dashboards에서 `guard.ndjson` 가져오기 → 서버 로그 그룹에 가짜 가드 기록 한 줄 쓰기(가짜 개인정보 5종 포함, `aws logs put-log-events` 또는 서버에서 `logger`) → 5분 뒤 화면·가림 확인(SC-007). 틀은 다음 날 인덱스부터 적용되므로 `question` 낱말 검색은 다음 날 확인.
- [-] T031 📨 [US5] (2026-11-25 A 결정으로 하지 않음) 팀 공지 초안: 가드에 걸린 질문(가린 앞 300자)을 28일 남기고 팀원이 Dashboards에서 볼 수 있음 → A 확인 뒤.

## Phase 7: US4 - D에게 연결 방법 전달 (P2)

- [X] T020 [US4] (D 작업 순서 체크리스트·실측 지연·비용·정규식 수정 1건 추가) `contracts/agent-guard-connection.md`를 구현 결과로 맞춘다(실제 함수 이름·반환 필드, 시험 기록의 실측 지연·비용, 프로필 ID).
- [ ] T021 📨 [US4] #66 댓글 초안(연결 문서 링크, SSM 이름 3개, `guard_result.py` 복사 방법, 부를 두 곳, 실패 시 동작, 처음엔 `none`) → A 확인 뒤 게시.

## Phase 8: Polish

- [X] T022 [P] (research R13) `specs/a-platform/017-agent-guardrail/research.md`: 시험으로 확인한 사실 반영(Standard 한국어 탐지 결과, 관리형 PHONE의 한국 번호 탐지 여부, 프로필 ARN 권한 형식, 실측 비용).
- [X] T023 🧑 (해당 없음: 콘솔에서 따로 만든 가드레일 없음) 콘솔에서 만든 시험용 가드레일 삭제(Terraform 것이 정본, quickstart §6).
- [X] T024 PR #87 초안(spec부터 읽는 순서, 커밋 고정 링크) → A 확인 뒤 생성, `Closes #86`.

## Dependencies

- Setup(T001~T004) → Foundational(T005~T006) → US1(T007~T012) → US2(T013~T017) → US3·US5·US4 → Polish.
- US5(T025~T031)는 가드레일과 독립이라 US1과 같이 해도 된다(라우터·틀·화면은 가짜 기록으로 확인).
- US2의 실제 시험(T016)은 US1 apply(T011) 뒤. 단, 콘솔 시험 가드레일이 있으면 `--guardrail-id … --version DRAFT`로 먼저 돌릴 수 있다.
- #84(016) 머지와 무관. D 머지와 무관(T017만 D 파일 필요, 선택).

## Parallel

- T002·T003 / T005·(T004) / T008·T009(T007과 다른 파일, 참조만) / T013·T014 / T025·T027·T028.

## Implementation Strategy

MVP = US1 + US2 + US5: 가드레일을 만들고 시험 기록으로 "정상 질문을 막지 않는다"를 확인하고, 감지 결과를 볼 화면까지 있는 상태. 이 상태에서 D에게 감지만(`none`)으로 붙이게 넘긴다. US3(차단 전환)는 Dashboards의 운영 감지를 본 뒤 정책별로.
