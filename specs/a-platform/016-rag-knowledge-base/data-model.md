# Data Model: RAG 문서 지식 기반 (016)

## 1. 문서 원장 `services/rag-docs/docs_catalog.csv`

문서 하나 = 한 행. 사람이 고치고 PR로 리뷰한다. 빈 칸은 "확인 안 됨"이다(메타데이터에 넣지 않음).

| 열 | 예 | 규칙 |
|---|---|---|
| `file` | `대기환경보전법시행규칙_별표8_배출허용기준_현행_제71호_20261112.pdf` | 업로드 폴더의 실제 파일명. 유일 |
| `folder` | `laws` / `handbook` | 데이터 소스 |
| `doc_id` | `air-rule_appx-08` | 영문 소문자·숫자·`-`·`_`. 유일 |
| `law_name` | `대기환경보전법 시행규칙` | 소속 법령·고시의 정식 이름 |
| `title_ko` | `별표 8 대기오염물질의 배출허용기준` | 문서 제목 |
| `doc_type` | `별표` | 법률·시행령·시행규칙·고시·훈령·별표·편람 |
| `part` | `별표8` / `본문` | 공백 없이 |
| `doc_no` | `기후에너지환경부령 제71호` | 소속 법령의 호수 |
| `effective_date` | `2026-11-12` | `YYYY-MM-DD`, 편람처럼 일이 없으면 `YYYY-MM` |
| `amendment_mark` | `<개정 2026. 11. 4.>` | 별표 머리의 개정표시(있을 때) |
| `effective_status` | `현행` | `현행` / `구판` / `과거` |
| `authority_class` | `시행규칙` | `법률` / `시행령` / `시행규칙` / `위임 고시` / `훈령` / `업무편람` (D manifest의 statute·enforcement_decree·enforcement_rule·delegated_notice·official_manual에 대응) |
| `tms_relevance` | `직접` | `직접` / `간접` |
| `source_org` | `기후에너지환경부` | |
| `related_articles` | `시행규칙 제15조;시행규칙 제33조` | `;` 구분 |
| `table_heavy` | `true` | |
| `page_count` | `35` | PDF 쪽수와 같아야 함 |
| `caveat` | `구판. 부과금 숫자 인용 금지` | 짧게 |
| `notes_private` | 미확인·메모 | 메타데이터에 넣지 않음 |

## 2. 메타데이터 파일 `<file>.metadata.json`

형식은 [contracts/metadata-file.md](contracts/metadata-file.md). 원장 → 키 대응:

| 키 | 타입 | 임베딩 포함 | 원장 열 |
|---|---|---|---|
| `law_name` | STRING | ✅ | law_name |
| `title_ko` | STRING | ✅ | title_ko |
| `part` | STRING | ✅ | part |
| `doc_id` | STRING | | doc_id |
| `doc_type` | STRING | | doc_type |
| `doc_no` | STRING | | doc_no |
| `effective_date` | STRING | | effective_date |
| `effective_ymd` | NUMBER | | effective_date가 일까지 있을 때만 `YYYYMMDD` |
| `amendment_mark` | STRING | | amendment_mark |
| `effective_status` | STRING | | effective_status |
| `authority_class` | STRING | | authority_class |
| `tms_relevance` | STRING | | tms_relevance |
| `source_org` | STRING | | source_org |
| `related_articles` | STRING_LIST | | related_articles |
| `table_heavy` | BOOLEAN | | table_heavy |
| `page_count` | NUMBER | | page_count |
| `caveat` | STRING | | caveat |

## 3. 인덱스 `rag-docs` 필드

형식·매핑은 [contracts/rag-index.md](contracts/rag-index.md).

| 필드 | 타입 | 쓰는 쪽 |
|---|---|---|
| `bedrock-vector` | knn_vector 1024, faiss hnsw, l2 | 지식 기반 |
| `bedrock-text` | text, analyzer `nori` | 지식 기반(조각 본문) |
| `bedrock-metadata` | text, 색인 안 함 | 지식 기반(출처 원본) |
| 메타데이터 키들 | 동적 매핑(글자 = text + keyword) | 지식 기반이 최상위 필드로 씀 → 거르기 |

## 4. 조각 (지식 기반이 만든다)

본문(`bedrock-text`) + 벡터 + 메타데이터 키 + 출처 위치(S3 URI, 쪽 번호). 법령은 계층 조각(부모·자식), 편람은 의미 단위.

## 5. 시험 질문 `services/rag-docs/eval_questions.yaml`

```yaml
- id: q01
  question: 질소산화물 배출허용기준은 어디에 정해져 있나?
  expect_doc_ids: [air-rule_appx-08]
  forbid_doc_ids: [air-decree_appx-08]   # 같은 번호 별표
  check: 같은 번호 별표 구분
  level: 중간          # 쉬움 / 중간 / 어려움
```

난이도: **쉬움** = 질문 단어가 문서 제목·조문에 그대로 있음(예: "과태료 부과기준은 어디에?"), **중간** = 말을 바꿨거나 같은 번호 별표 구분·표 안 값 찾기, **어려움** = 여러 문서를 이어야 함(제9조 → 별표 2 → 시행규칙 별표 8)이나 구판·현행 구분, 편람 질의·회신. 약 15개를 쉬움 5·중간 5·어려움 5로.

통과 = 상위 5개 안에 `expect_doc_ids` 중 하나가 있고, `forbid_doc_ids`가 1위가 아님.

## 6. 문서 상태 흐름

```
PC 원본 폴더 ─(trim_pdf: 별표 8만)─▶ 업로드 폴더 laws/·handbook/ ─(make_metadata)─▶ +.metadata.json
   ─(check_metadata 39/39)─▶ aws s3 sync ─▶ 동기화(ingestion job) ─▶ 색인됨 ─(문서 교체·삭제 + 재동기화)─▶ 갱신
```
