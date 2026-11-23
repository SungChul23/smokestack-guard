# Tasks: RAG 문서 지식 기반 (법령·고시·업무편람)

**Input**: `specs/a-platform/016-rag-knowledge-base/` (spec, plan, research R1~R10, data-model, contracts 4개, quickstart)

**표시**: [P] 다른 파일이라 같이 해도 됨 · [US1]~[US4] spec의 사용자 스토리 · 🧑 사람(A)이 AWS·PC에서 · 📨 다른 담당과 공유

테스트는 로컬 스크립트(메타데이터 생성·검사, 쪽 자르기, 업로드 구성, 질문 도구 출력, 시험 채점)와 `setup_opensearch.py` 계획에 둔다. 실제 검색 품질은 시험 질문 묶음(사람이 실행)으로 잰다.

## Phase 1: Setup

- [X] T001 `services/rag-docs/` 뼈대: `pyproject.toml`(Python 3.12, 의존 `boto3`·`pypdf`·`pyyaml`, 개발 `pytest`·`ruff`, ruff 줄 길이 100), `requirements.txt`, `README.md`(무엇을, 폴더 규칙 — PDF 원본은 저장소에 넣지 않음, 명령 순서는 quickstart 링크), `tests/`, `.gitignore`(`missing_fields.csv`는 커밋, 업로드 폴더 경로·`*.pdf`는 무시).
- [X] T002 [P] `.github/workflows/rag-docs.yml`: `services/rag-docs/**` 변경 시 ruff·pytest (log-search 워크플로와 같은 모양).
- [X] T003 [P] `.github/CODEOWNERS`: `/services/rag-docs/ @SungChul23`, `/infra/stacks/tms-rag/ @SungChul23`.
- [X] T004 `infra/stacks/tms-rag/`: `backend.tf`(상태 버킷 `smokestack-tfstate-952900391026`, 키 `stacks/tms-rag/terraform.tfstate`), `versions.tf`(`~> 1.15.0`, aws `~> 6.0`, `default_tags` stack=`tms-rag`), `variables.tf`(`rag_kb_enabled` 기본 false, `agent_retrieve_enabled` 기본 false, `embedding_model_id` 기본 `amazon.titan-embed-text-v2:0`, `parser_profile_id`(기본 `global.anthropic.claude-haiku-4-5-20251001-v1:0`, 설명에 "지식 기반 파싱 허용 목록에서 확인"), `answer_profile_id`(기본 Claude Haiku 4.5), `embedding_dimensions` 1024, `opensearch_domain_name` 기본 `tms-logs`, `index_name` 기본 `rag-docs`), `outputs.tf`(버킷 이름, 역할 ARN, `knowledge_base_id`·데이터 소스 ID 2개는 스위치 켰을 때). `terraform init`(사람이 PowerShell)·`.terraform.lock.hcl` 커밋.

## Phase 2: Foundational (버킷·역할·인덱스 — 모든 스토리의 전제)

- [ ] T005 `infra/stacks/tms-rag/bucket.tf`: 문서 버킷 `smokestack-tms-rag-952900391026`(퍼블릭 액세스 차단 4개, SSE-S3, 버전 관리 켬, 수명 주기 없음 — 이전 버전만 30일 뒤 삭제), 소유자 강제 (FR-016, research R5).
- [ ] T006 `infra/stacks/tms-rag/kb_role.tf`: 역할 `tms-rag-kb`(신뢰 `bedrock.amazonaws.com`, 조건 `aws:SourceAccount`=계정, `aws:SourceArn` like `arn:aws:bedrock:ap-northeast-2:<계정>:knowledge-base/*`), 정책: 버킷 `s3:GetObject`·`s3:ListBucket`(조건 `aws:ResourceAccount`), `bedrock:InvokeModel` — 임베딩 모델 ARN + 파서 추론 프로필 ARN + 그 아래 기반 모델 ARN(`arn:aws:bedrock:*::foundation-model/<id>`), `es:ESHttpGet/Post/Put/Delete/Head`·`es:DescribeDomain` — 도메인 ARN·`/*` (research R5 표 그대로).
- [ ] T007 `infra/stacks/tms-log-search/domain.tf`: `data "aws_iam_roles" "rag_kb"`(`name_regex = "^tms-rag-kb$"`)를 더하고 접근 정책 `Principal.AWS`에 `tolist(data.aws_iam_roles.rag_kb.arns)`를 이어 붙인다(역할이 없으면 빈 목록). 주석에 016 (contracts/rag-index.md).
- [ ] T008 [P] `services/log-search/opensearch/indices/rag-docs.json`: contracts/rag-index.md의 설정·매핑 그대로(`index.knn` true, 샤드 1·복제 0, 분석기 `korean`(nori_tokenizer + nori_part_of_speech·nori_readingform·lowercase), `bedrock-vector` knn_vector **1024** faiss hnsw l2 m 16 ef_construction 512, `bedrock-text` text analyzer korean, `bedrock-metadata` text index false).
- [ ] T009 [P] `services/log-search/opensearch/roles/rag_kb_writer.json`: contracts/rag-index.md 그대로(인덱스 `rag-docs*` 권한, 로그 인덱스 없음).
- [ ] T010 `services/log-search/setup_opensearch.py`: `opensearch/indices/*.json` 단계 추가 — `HEAD /<이름>`이 있으면 "있음(건너뜀)", 없으면 `PUT`(인덱스는 덮어쓰지 않음, 매핑 바꾸려면 사람이 지우고 다시), 역할 `rag_kb_writer` 생성 + 매핑 `rag_kb_writer ← arn:aws:iam::<계정>:role/tms-rag-kb`. 순서: 템플릿 → ISM → **인덱스** → 역할 → 매핑 → 알림. 문서 문자열·README 갱신.
- [ ] T011 [P] `services/log-search/tests/test_setup.py`: dry-run에 `rag-docs` 인덱스 단계와 `rag_kb_writer` 역할·매핑이 나옴, 인덱스 정의의 `dimension == 1024`·`bedrock-text` analyzer `korean`, 이미 있으면 PUT하지 않음(가짜 클라이언트), 기존 매핑(`readall` 등)은 그대로.
- [ ] T012 🧑 `tms-rag` plan·apply(버킷·역할만) → `tms-log-search` plan(접근 정책에 주체 1개 추가만)·apply → `setup_opensearch.py --dry-run` → 실행 → Dev Tools `GET rag-docs/_mapping` 확인 (quickstart §1·§2).

**Checkpoint**: 버킷·역할·인덱스가 있고, 로그 수집은 그대로(Firehose 전달 실패 0).

## Phase 3: US2 - 문서마다 정확한 출처 정보 (P1) 🎯

**목표**: 39개 PDF에 검사를 통과한 메타데이터가 붙은 업로드 폴더. **독립 확인**: `check_metadata.py` 39/39, 일부러 깨뜨린 경우 실패를 짚음.

(US1의 색인이 이 결과에 의존하므로 US2를 먼저 한다.)

- [ ] T013 [P] [US2] `services/rag-docs/tests/test_trim_pdf.py`: 3쪽짜리 가짜 PDF(pypdf로 생성)에서 `--pages 2-3` → 2쪽, 원본 불변, 범위 밖·역순 범위는 오류.
- [ ] T014 [P] [US2] `services/rag-docs/trim_pdf.py`: `trim_pdf.py <원본> --pages A-B --out <새 파일>` — pypdf로 쪽 복사, 원본은 열기만(FR-008), 출력 경로가 원본과 같으면 거부.
- [ ] T015 [US2] `services/rag-docs/docs_catalog.csv`: 39행 원장(data-model §1 열 그대로). 값의 출처: 파일명·PDF 첫 쪽(호수·개정표시·"(제○조 관련)"), A의 의뢰서(법령 본문 3·별표·관제센터·편람 값), D `manifest.csv`(effective_status·authority_class·caveat). 규칙: `effective_status`는 `현행`/`구판`/`과거`만, `authority_class`는 `법률`/`시행령`/`시행규칙`/`위임 고시`/`훈령`/`업무편람`만, `tms_relevance`는 `직접`/`간접`(시험검사법 4개·시험검사법 별표 3개·형식승인 고시 = 간접), 편람 `effective_date`=`2024-12`·`effective_status`=`구판`·`caveat`=`구판(2025.12 개정판 미확보). 본문의 2024년도 부과금 산정지수는 현행 아님 — 부과금 숫자 인용 금지`, 별표 8은 `…_현행_…` 파일·`page_count` 35. 전산기록 고시·IoT 운영규정의 고시 번호는 각 PDF 본문에서 확인해 적고 다르면 `notes_private`에. 확인 안 된 값은 빈 칸.
- [ ] T016 [P] [US2] `services/rag-docs/tests/test_metadata.py`: 원장 2행 + 가짜 PDF로 — 키마다 타입(`STRING`/`NUMBER`/`BOOLEAN`/`STRING_LIST`)과 `includeForEmbedding`(`law_name`·`title_ko`·`part`만 true), 빈 칸은 키 없음 + `missing_fields.csv`에 행, `effective_ymd`는 일까지 있을 때만, `related_articles` `;` 분리, 파일명 = PDF명 + `.metadata.json`, PDF 바이트 불변.
- [ ] T017 [US2] `services/rag-docs/make_metadata.py`: `--catalog docs_catalog.csv --dest <업로드 폴더>` — 원장 행마다 `<folder>/<file>`이 있는지 확인하고 contracts/metadata-file.md 형식으로 씀, `missing_fields.csv`(doc_id, 빠진 키) 저장소 쪽에 씀, 원장에 없는 PDF가 폴더에 있으면 오류.
- [ ] T018 [P] [US2] `services/rag-docs/tests/test_check_metadata.py`: 통과 폴더 → 0 종료·`N/N 통과`. 실패 각각을 짚음: 짝 없는 PDF, 짝 없는 JSON, 이름 틀림(`.json`만), JSON 깨짐, 허용 밖 타입, 빈 문자열·빈 목록·null, 필수 키 없음(`doc_id`, `law_name`, `title_ko`, `part`, `doc_type`, `effective_date`, `effective_status`, `authority_class`, `page_count`), 10KB 초과, `page_count` ≠ PDF 쪽수, `doc_id` 중복, PDF·JSON 외 파일 (SC-002).
- [ ] T019 [US2] `services/rag-docs/check_metadata.py`: `--dest <업로드 폴더>` — T018 규칙, 실패마다 `파일: 이유` 한 줄, 끝에 `통과 N/M`, 실패 있으면 종료 코드 1.
- [ ] T020 [P] [US2] `services/rag-docs/tests/test_stage_upload.py`: 원본 두 폴더 + 원장 → `laws/`·`handbook/`로 복사, 별표 8 원본(55쪽)은 복사하지 않음, 원장에 있는데 원본이 없으면 오류, 대상 폴더의 원장 밖 파일은 지우라고 경고.
- [ ] T021 [US2] `services/rag-docs/stage_upload.py`: `--src <폴더>… --dest <업로드 폴더>` — 원장대로 복사(별표 8 현행은 T014 결과를 그대로 둠), 끝에 실행할 `aws s3 sync … --exclude "*" --include "*.pdf" --include "*.metadata.json" --delete --dryrun` 명령을 출력(직접 올리지 않음).
- [ ] T022 🧑 [US2] 로컬 실행: `trim_pdf.py`(별표 8 → 21~55쪽) → `stage_upload.py` → `make_metadata.py` → `check_metadata.py` 39/39 → `missing_fields.csv` 확인 (quickstart §3).

## Phase 4: US1 - 올리면 질문으로 찾을 수 있다 (P1)

**목표**: 39개가 색인되고 질문에 출처가 붙은 조각이 나온다. **독립 확인**: 동기화 통계 실패 0, "굴뚝 자동측정기기 부착대상" 1위가 시행령 별표 3.

- [ ] T023 [P] [US1] `services/rag-docs/parsing_prompt.md`: 모델 파서 지시문(한국어 법령 PDF 쪽 그림 → 글자): 쪽 머리글·바닥글·쪽 번호(`법제처 N 국가법령정보센터 <법령명>` 등) 빼기, 표는 마크다운 표(병합 칸은 값을 칸마다 반복, 칸 순서 유지), 조문 번호·항·호·목·별표 번호·"(제○조 관련)"·개정표시 `<개정 …>` 그대로, 글자 겹침(같은 글자 두 번)은 한 번으로, 내용을 고치거나 요약·번역하지 않음, 빈 쪽은 빈 출력 (research R4).
- [ ] T024 [US1] `infra/stacks/tms-rag/knowledge_base.tf`(`count = var.rag_kb_enabled ? 1 : 0`): `aws_bedrockagent_knowledge_base` `tms-rag-docs` — 역할 `tms-rag-kb`, 벡터 임베딩 `embedding_model_arn`(Titan V2, `embedding_model_configuration.bedrock_embedding_model_configuration.dimensions = 1024`, `embedding_data_type = "FLOAT32"`), 저장소 `OPENSEARCH_MANAGED_CLUSTER`(도메인 ARN·엔드포인트 data 조회, 인덱스 `rag-docs`, 필드 `bedrock-vector`·`bedrock-text`·`bedrock-metadata`).
- [ ] T025 [US1] 같은 파일: 데이터 소스 2개 — `laws`(포함 접두어 `laws/`, 계층 조각 부모 1500·자식 300·겹침 60), `handbook`(포함 접두어 `handbook/`, 의미 단위 최대 300·버퍼 0·백분위 95). 둘 다 파싱 `BEDROCK_FOUNDATION_MODEL`(`model_arn` = 계정·리전으로 조립한 `var.parser_profile_id` 추론 프로필 ARN, `parsing_prompt_string = file(…/services/rag-docs/parsing_prompt.md)`), `data_deletion_policy = "DELETE"`(버킷에서 지우면 조각도 지움, FR-012). `outputs.tf`에 ID.
- [ ] T026 [US1] `terraform fmt -recursive`·`validate`(tms-rag, tms-log-search) — AI가 실행해 결과 기록.
- [ ] T027 🧑 [US1] `aws s3 sync`(어려운 문서 3개만: 시행규칙 별표 36, 별표 8 현행, 관제센터 별표 1 + 메타데이터) → `tms-rag` apply `-var rag_kb_enabled=true`(파서 모델이 허용 목록에 없다는 오류면 변수만 바꿔 다시) → laws 동기화 → Dev Tools로 조각 10개: 표가 마크다운 표인지, 머리글 없는지, 메타데이터 키가 필드로 있는지 기록 (quickstart §4·§5, research R4).
- [ ] T028 🧑 [US1] 나머지 업로드(`--dryrun` 확인 뒤) → laws·handbook 동기화 → 통계 scanned 38/1·indexed 38/1·failed 0(SC-001), 비용 메모(Cost Explorer Bedrock 다음 날).

## Phase 5: US3 - 내 PC에서 자연어로 묻는다 (P1)

**목표**: `ask.py`와 시험 묶음. **독립 확인**: 질문 하나 10초 안 조각 5개, `run_eval.py` 통과율 표.

- [ ] T029 [P] [US3] `services/rag-docs/tests/test_ask.py`: 가짜 `bedrock-agent-runtime`(retrieve·retrieve_and_generate 응답 고정) — 출력 줄 형식(순위·점수·법령명·part·시행일·효력 상태·파일·쪽·본문 200자, contracts/ask-cli.md), `--status`가 `in` 필터로 들어감, `--top` 1~20 범위, `--answer` 근거 목록, `--json`, 오류 4종 메시지·종료 코드(ID 없음 2, 자격 증명 없음 2, AccessDenied 3, ResourceNotFound 3).
- [ ] T030 [US3] `services/rag-docs/ask.py`: contracts/ask-cli.md 그대로. 검색 `HYBRID`, 지식 기반 ID `--kb`/`RAG_KB_ID`, 답변 모델 `--model`/`RAG_ANSWER_MODEL`(기본 Claude Haiku 4.5 추론 프로필, 별칭 `haiku`·`sonnet`, 계정·리전으로 ARN 조립), 쪽 번호는 결과 메타데이터 `x-amz-bedrock-kb-document-page-number`가 있으면 표시.
- [ ] T031 [US3] `services/rag-docs/eval_questions.yaml`: **15개 = 쉬움 5·중간 5·어려움 5**, 형식 data-model §5(`id`, `level`, `question`, `expect_doc_ids`, 선택 `forbid_doc_ids`, `check`). 구성:
  - 쉬움(질문 단어가 제목·조문에 그대로): 과태료 부과기준(시행령 별표 15) / 굴뚝 자동측정기기 부착대상(시행령 별표 3) / 행정처분기준(시행규칙 별표 36) / 사업장 1~5종 분류기준(시행령 별표 1의3) / 관제센터 규정의 실시간 공개(관제센터 본문 제9조·별표 2)
  - 중간(말 바꿈·같은 번호 구분·표 안 값): 발전소 NOx 배출 기준(시행규칙 별표 8, forbid 시행령 별표 8) / 기본부과금 농도별 부과계수(시행령 별표 8, forbid 시행규칙 별표 8) / 측정기기 운영·관리기준(시행규칙 별표 9, forbid 시행령 별표 9) / 30분 평균치 정의(관제센터 본문 제2조) / 현행 대기 초과배출부과금 산정지수(산정지수 고시, forbid 업무편람)
  - 어려움(여러 문서 잇기·구판 구분·간접 문서·편람 Q&A): 실시간 공개자료에서 기준초과 인정 시간(관제센터 별표 2 + 시행규칙 별표 8) / 무효자료가 생기면 대체자료를 어떻게 만드나(관제센터 별표 1) / 굴뚝 자동측정기기 정도검사는 어떤 법에 따라 어떻게(시험검사법·형식승인 고시) / 측정기기를 고장 난 채 두면 몇 차에 어떤 처분(시행규칙 별표 36 + 법 본문) / 업무편람 질의·회신 중 TMS 부착 관련 사례(업무편람)
  - `doc_id`는 T015 원장 값과 같게.
- [ ] T032 [P] [US3] `services/rag-docs/tests/test_run_eval.py`: 가짜 retrieve 결과로 — 기대 문서가 5위 안이면 통과, forbid가 1위면 실패, 난이도별·전체 통과율, 같은 번호 별표 질문(`check`에 "같은 번호") 통과율, 결과 md 표 형식.
- [ ] T033 [US3] `services/rag-docs/run_eval.py`: `--kb`, `--only`, `--top`(기본 5) — 질문마다 Retrieve → 통과/실패, 기대 문서 순위, 1위 문서 → `eval_results/<YYYY-MM-DD>.md`(질문 표 + 난이도별 통과율 + 전체 통과율).
- [ ] T034 🧑 [US3] `ask.py`로 quickstart §6 질문 2개 + `--answer` 1개 → `run_eval.py` 실행 → 결과 파일 커밋. 기준: 전체 ≥ 80%, 같은 번호 별표·현행 산정지수 100%(SC-003), 답변 인용(SC-004)은 `--answer`(Haiku 4.5)로 5개 표본 확인, Haiku가 틀린 어려운 질문은 `--model sonnet`으로 다시 돌려 차이를 기록(D에게 답변 모델 근거). 못 미치면 원인(조각·파서 지시문·메타데이터) 메모 후 조정.

## Phase 6: US4 - 에이전트가 같은 지식 기반을 부른다 (P2)

**목표**: 서버 역할이 Retrieve할 수 있고 D가 연결 안내를 받는다. **독립 확인**: 서버 역할로 같은 질문 → 같은 조각.

- [ ] T035 [US4] `infra/stacks/tms-rag/agent_access.tf`(`count = var.rag_kb_enabled && var.agent_retrieve_enabled ? 1 : 0`): `data "aws_iam_role"` `tms-app-server`에 인라인 정책 `tms-rag-retrieve` — `bedrock:Retrieve`·`bedrock:RetrieveAndGenerate`(이 지식 기반 ARN), 답변 모델 추론 프로필·기반 모델 `bedrock:InvokeModel`. SSM `/tms/app/config/rag-knowledge-base-id`(String, 값 = 지식 기반 ID — 비밀 아님) (contracts/agent-connection.md).
- [ ] T036 🧑 [US4] apply `-var rag_kb_enabled=true -var agent_retrieve_enabled=true` → 서버(SSM 세션)에서 `aws bedrock-agent-runtime retrieve`로 쉬움 질문 1개 → 로컬 결과와 같은지.
- [ ] T037 📨 [US4] D에게 `contracts/agent-connection.md` 공유(#66 댓글): ID 위치, 권한, 호출 예, 인용 규칙(구판·간접 표시, 부과금 숫자), 효력 상태 필터.

## Phase 7: Polish

- [ ] T038 [P] `AGENTS.md`: 저장소 구조에 `infra/stacks/tms-rag/`(문서 버킷 + 지식 기반 역할·지식 기반·데이터 소스, 016)와 `services/rag-docs/`(메타데이터·질문 도구, A, 016), S3 경로 규칙에 "문서 버킷 `smokestack-tms-rag-952900391026`은 RAG 근거 PDF와 메타데이터만(laws/·handbook/), 원본 버킷과 따로" 한 줄.
- [ ] T039 [P] `services/log-search/README.md`: `rag-docs` 인덱스·`rag_kb_writer` 역할, 인덱스는 덮어쓰지 않음(바꾸려면 지우고 재동기화).
- [ ] T040 🧑 SC-005(조각 20개 머리글 0)·SC-007(일주일 JVM 최대 < 90%, 로그 전달 실패 증가 없음)·SC-008(구축 비용 ≤ $10) 확인 → spec Status 갱신, 이슈 #80 체크.
- [ ] T041 📨 D에게 2차 후보 알림: 근거 카드·사례 검토 뒤 `cards/` 데이터 소스로 넣어 같은 시험 묶음으로 비교 (research R10).

## Dependencies

- Phase 1 → Phase 2(T012 사람 적용까지) → US2 → US1 → US3 → US4 → Polish.
- US1(T024~T028)은 인덱스(T012)와 업로드 폴더(T022)가 있어야 지식 기반을 만들 수 있다(만들 때 인덱스·권한 검사).
- US3의 코드(T029~T033)는 가짜 응답으로 시험하므로 US1과 동시에 만들 수 있고, 실행(T034)만 US1 뒤.
- T007(tms-log-search)은 역할 조회라 T006 apply 전에도 plan이 깨지지 않는다.

## Parallel Example

```
Phase 2: T008 | T009 | T011  (T005·T006·T007·T010과 파일이 다름)
US2:     T013·T014 | T016 | T018 | T020   → T015 → T017 → T019 → T021
US3:     T029 | T032 | T031   → T030 → T033   (US1과 동시에)
```

## Implementation Strategy

1. **MVP**: Phase 1~2 + US2 + US1의 "어려운 문서 3개"(T027)까지 — 표·머리글 처리 품질을 몇 센트로 먼저 확인.
2. 39개 전체 동기화(T028) + 시험 묶음(US3)으로 통과율 확인, 필요하면 파서 지시문·조각 설정 조정(데이터 소스를 다시 만들고 재동기화).
3. 에이전트 연결(US4)은 품질 기준을 넘긴 뒤.
