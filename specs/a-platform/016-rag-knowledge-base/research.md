# Research: RAG 문서 지식 기반 (016)

## R1. 관리형 지식 기반 + 기존 OpenSearch 도메인

- **Decision**: Amazon Bedrock Knowledge Bases, 벡터 저장소 = OpenSearch 관리형 클러스터 `tms-logs`(014)의 새 인덱스 `rag-docs`.
- **Rationale**: 읽기·조각·임베딩·동기화(바뀐 파일만)를 관리형으로 받는다. 도메인 조건(공개 접근, 2.13 이상, FGAC)을 `tms-logs`(공개, 2.19, FGAC)가 이미 만족한다. 추가 서버가 없다.
- **Alternatives**: OpenSearch Serverless(최소 월 $170+), RDS pgvector(지식 기반은 Aurora만 지원, 일반 RDS는 직접 구현 필요), S3 Vectors(싸지만 한국어 키워드 혼합 검색이 없음), 직접 구현(Lambda로 추출·조각·임베딩 — 먼저 관리형으로 품질을 본 뒤 필요하면 같은 인덱스로 옮김).
- **조건(AWS 문서)**: 도메인 접근 정책이 지식 기반 역할을 허용, FGAC 역할에 그 역할 ARN을 백엔드 역할로 매핑, 인덱스를 미리 만듦, 지식 기반 역할 IAM에 `es:ESHttp*`·`es:DescribeDomain`.

- **nori(2026-11-23 정정)**: OpenSearch Service에서 nori는 기본 포함이 아니라 **선택 플러그인**(`analysis-nori`, 2.19 패키지 `G5688189`)이다. 도메인에 연결해야 하고 연결 때 블루/그린 배포가 한 번 돈다. 내장 `cjk`(두 글자 자르기) 대안도 있었으나 법령 용어 키워드 정확도와, 나중에 바꾸면 인덱스 재생성·전체 재동기화(파서 비용 반복)가 들어 지금 nori로 결정.

## R2. Terraform으로 지식 기반까지 만든다

- **Decision**: `aws_bedrockagent_knowledge_base`(storage `OPENSEARCH_MANAGED_CLUSTER`, `opensearch_managed_cluster_configuration`)와 `aws_bedrockagent_data_source`(파싱 `BEDROCK_FOUNDATION_MODEL` + `parsing_prompt`, 조각 설정)를 새 스택에 둔다. 잠금 provider 6.73.0 바이너리에 해당 스키마가 있음을 확인(2026-11-23).
- **Rationale**: 원칙 III(콘솔 리소스는 임시). 처음부터 코드로 두면 다시 만들 때 같은 결과.
- **순서 문제**: 지식 기반 생성 때 인덱스·권한을 검사한다 → 스위치 `rag_kb_enabled`(기본 false)로 두 번 apply(plan "적용 순서").
- **Alternatives**: 콘솔로 만들고 나중에 import(원칙 III상 결국 코드 필요, import는 사람이 해야 해서 번거로움).

## R3. 임베딩 모델

- **Decision**: `amazon.titan-embed-text-v2:0`, 1024차원, float. 서울 리전 ON_DEMAND 확인(2026-11-23 `list-foundation-models`).
- **Rationale**: 다국어(한국어), 가장 쌈(1,000토큰당 약 $0.00002), 1024에서 가장 정확. 조각 수천 개라 메모리 부담 없음(약 12MB + 그래프).
- **Alternatives**: Cohere Embed v4(서울은 추론 프로필만, 비교는 품질이 모자랄 때), 512차원(AWS 발표상 정확도 약 99% 유지, 저장 절반 — 규모가 작아 이득 없음).
- 만든 뒤에는 모델·차원을 바꾸지 않는다(바꾸면 인덱스·지식 기반을 다시 만든다).

## R4. 읽기(파싱)와 조각

- **Decision**:
  - 두 데이터 소스 모두 **모델 파서**(쪽을 그림으로 읽음)에 지시문 `services/rag-docs/parsing_prompt.md`: 쪽 머리글·쪽 번호(`법제처 N 국가법령정보센터 …`) 제외, 표는 마크다운 표로 유지(병합 칸은 반복), 조문 번호·별표 번호·"(제○조 관련)"·개정표시 유지, 글자를 고치거나 요약하지 않음.
  - 파서 모델: **Claude Haiku 4.5**(서울은 추론 프로필 `global.`/`apac.`로만 호출, 공개 법령이라 다른 리전 처리 무방). 지식 기반 파싱 허용 목록에 없으면 목록 안의 가장 싼 Claude로. 변수 `parser_model_arn`. 쪽당 입력 약 2,000·출력 약 1,000~1,500토큰 추정 → 500쪽 약 $4~5. Sonnet 4.5는 약 $12~15(한도 초과·과함), Nova Lite는 약 $0.2지만 한국어 병합 표 정확도 우려(2026-11-23 사용자 결정: Haiku 4.5. Haiku 5.5는 약 1/10 가격($0.10/$0.50)이나 출시 직후라 사례가 쌓인 뒤 어려운 문서 3개로 비교).
  - **먼저 어려운 문서 3개만 시험**(시행규칙 별표 36, 별표 8 현행, 관제센터 별표 1): 시험용 접두어로 동기화해 조각의 표·머리글을 Dev Tools로 확인한 뒤 39개 전체.
  - 법령·고시(`laws/`): **계층 조각**(부모 약 1,500토큰, 자식 약 300토큰, 겹침 약 60토큰) — 작은 조각으로 찾고 큰 조각(별표 표·조문 묶음)을 넘긴다.
  - 편람(`handbook/`): **의미 단위 조각**(최대 약 300토큰, 문장 사이 거리 백분위 95) — 질의·회신 문단이 주제 단위로 묶이게.
- **Rationale**: D 교차검증의 품질 문제(머리글 반복, 표 평탄화, 편람 글자 겹침)는 글자층 추출에서 생긴다. 그림으로 읽는 파서가 셋 다 줄인다. 조각 방식은 데이터 소스마다 하나라 폴더를 나눴다.
- **Alternatives**: 기본 파서(무료지만 위 문제 그대로), Bedrock Data Automation 파서(표에 강하나 요금 단위가 다르고 지시문이 없음), 미리 글자로 바꿔 올리기(사용자 결정: PDF 그대로).
- 조각 설정은 데이터 소스를 만든 뒤 바꿀 수 없다 → 바꿀 땐 데이터 소스를 다시 만들고 동기화(39개라 수 분).

### R4a. 파서 모델 교체 (2026-11-23)

- 어려운 문서 3개 첫 동기화(Haiku 4.5) 결과, 시행규칙 별표 36 행정처분 표에서 근거법령 칸을 빼고 4칸으로 읽어 값이 밀렸다("일부 미부착 3차 = 조업정지 5일", 원본은 10일). 같은 쪽 그림을 같은 지시문으로 직접 비교:
  - Haiku 4.5: 가)~마) 다섯 행을 한 칸에 뭉침, 한국어 오타("일부"→"입박", "청정연료"→"정정연료", "연속하여"→"인속여여")
  - **Sonnet 4.6: 7행 모두 원본과 일치**(입력 1,985·출력 1,229토큰, 12초)
  - Sonnet 4.5: 레거시로 호출 거부. Haiku 5.5·Sonnet 5·5.5: 이 계정에서 아직 사용 불가
- **Decision**: 두 데이터 소스 모두 파서 = Sonnet 4.6(`global.anthropic.claude-sonnet-4-6`). 일반 글자도 틀리므로 표 문서만 나누지 않는다. 비용 약 500쪽 × 쪽당 약 $0.024 ≈ **$12**(spec 목표 $10을 약간 넘지만 틀린 처분 단계를 인용하는 위험이 더 크다). 답변 기본 모델은 Haiku 4.5 유지(이미 옮겨진 글자를 읽으므로 OCR 실수 없음).
- 머리글 제거·이름표 부착·단순 표(별표 8 3칸)는 Haiku에서도 정상이었다.

### R4b. 파싱을 지식 기반 밖(로컬)으로 (2026-11-23)

- Sonnet 4.6을 지식 기반 파서로 쓴 3개 시험에서 별표 8·관제 별표 1은 통과했지만, 별표 36 4쪽(가로선 없이 여러 항목이 쌓인 표)에서 경고·4차 처분 칸을 빠뜨렸다. 같은 쪽을 같은 모델·지시문(표 칸 수 규칙 추가)으로 직접 부르면 두 번 모두 정확했다. 지식 기반 안의 렌더링·재시도·검증은 조절할 수 없다.
- Bedrock Data Automation 파서: 데이터 소스 생성이 "parsing strategy is not permitted"로 거부(이 계정).
- PyMuPDF find_tables(무료·결정적): 열은 정확히 나누지만 가로선 없는 표는 행을 합친다(보정 규칙 필요, 개발이 길어짐).
- **Decision (사용자 결정)**: `services/rag-docs/pdf_to_md.py`가 쪽마다 150dpi 그림 + `parsing_prompt.md`로 Sonnet 4.6을 부르고, 쪽마다 표 칸 수·머리글·겹친 글자를 검사해 걸리면 그 쪽만 다시(최대 3번), 쪽별 캐시. 문서마다 `.md`(쪽 표시 `<!-- 쪽 N -->`) + 이름표(`source_pdf` 추가)를 만들어 `check_metadata`·`check_chunks --local`(정답 행)을 통과한 것만 올린다. 데이터 소스는 파싱 설정 없이(md는 그대로 읽음) 조각·임베딩만. 지식 기반 역할의 파서 모델 권한 제거.
- 3개 시험: 47쪽 모두 첫 시도 통과, 별표 36 정답 행 4/4, 167초, 약 $1.24. 전체 501쪽 예상 약 $12.8.
- 출처: 이름표 `source_pdf`(원본 PDF 이름) + md 안의 쪽 표시.

## R5. 권한 (최소 범위)

| 주체 | 권한 | 범위 |
|---|---|---|
| 지식 기반 역할 `tms-rag-kb` (신뢰: `bedrock.amazonaws.com`, 조건 `aws:SourceAccount`) | `s3:GetObject`, `s3:ListBucket` | 문서 버킷 |
| | `bedrock:InvokeModel` | Titan V2 모델 ARN, 파서 모델(추론 프로필 + 그 아래 모델) |
| | `es:ESHttpGet/Post/Put/Delete/Head`, `es:DescribeDomain` | 도메인 `tms-logs` |
| 도메인 접근 정책(tms-log-search) | 위 역할에 `es:ESHttp*` | 역할은 `data "aws_iam_roles"`(이름 정규식)로 찾아 없으면 빈 목록 → 순서와 무관하게 apply 가능 |
| OpenSearch FGAC 역할 `rag_kb_writer` | 인덱스 `rag-docs*`: `crud`, `create_index`, `indices:admin/mapping/put`, `indices:data/read/search`; 클러스터: `cluster_composite_ops`, `cluster_monitor` | 백엔드 역할 = `tms-rag-kb` ARN |
| 에이전트 서버 `tms-app-server` (스위치) | `bedrock:Retrieve`, (선택) `bedrock:RetrieveAndGenerate` + 답변 모델 `InvokeModel` | 이 지식 기반 ARN만. OpenSearch 권한은 주지 않는다(검색은 지식 기반 역할이 함) |
| members(Dashboards) | 변경 없음 | `readall`이라 `rag-docs`도 읽기만 가능(시험 확인용으로 둠) |

## R6. 메타데이터 원장과 생성

- **Decision**: 사람이 고치는 원장 `services/rag-docs/docs_catalog.csv`(문서 39행, 확인된 값만)를 두고, `make_metadata.py`가 PDF 폴더를 읽어 `<파일>.metadata.json`을 만든다. 원장의 효력 상태·문서 등급·주의사항은 D의 `manifest.csv`에서 옮기되 용어를 맞춘다. 빈 칸 = 키 생략 + `missing_fields.csv`(저장소에만).
- **Rationale**: 값 출처가 한 곳(원장)이고 PR로 리뷰된다. PDF는 저장소에 넣지 않는다(크기·저작권 표시 미확인).
- 형식: `contracts/metadata-file.md`. 쪽수는 PDF에서 읽어 원장 값과 대조.

## R7. 시행규칙 별표 8 자르기

- **Decision**: `trim_pdf.py`로 21~55쪽을 새 파일(`…_별표8_배출허용기준_현행_제71호_20261112.pdf`)로 만든다. 21쪽 앞부분의 과거 비고 몇 줄은 남는다(시험 질문으로 확인). 원본 55쪽은 업로드 폴더에 넣지 않는다.
- 2026-11-23 확인: 1쪽 "1. 2019년 12월 31일까지 적용되는 배출허용기준", 21쪽 중간 "2. 2020년 1월 1일부터 적용되는 배출허용기준".

## R8. 비용

| 항목 | 계산 | 금액 |
|---|---|---|
| 모델 파서 (Claude Sonnet 4.6, R4a) | 약 500쪽 × (입력 약 2,000 × $3/M + 출력 약 1,230 × $15/M) ≈ 쪽당 약 $0.024 | 약 $12 (Haiku 시험분 약 $1 별도) |
| 임베딩 | 약 50만 토큰 × $0.00002/1K | 약 $0.01 |
| S3 | 수십 MB | 월 1센트 미만 |
| OpenSearch | 기존 도메인, 인덱스 수십 MB | 0 |
| 시험 질문 | 15개 × 몇 번, 답변 모드 포함 | < $1 |
| **구축 합계** | | **약 $13~15** (SC-008 $10을 넘음 — R4a 결정) |

다시 동기화하면 바뀐 파일만 다시 읽어 비용이 거의 없다.

## R9. 로컬 질문 도구

- **Decision**: `ask.py "질문"`(Retrieve, 기본 5개, 하이브리드 검색), `--answer`(RetrieveAndGenerate, 답변 모델 기본 Claude Haiku 4.5 — 운영 비용을 가늠하려고 싼 모델이 기본, `--model sonnet`(Sonnet 4.5)은 Haiku가 틀린 어려운 질문만 비교), `--status 현행`(메타데이터 필터 `effective_status`), `--json`. 지식 기반 ID는 `terraform output` 값을 인자나 환경 변수로 받는다(코드에 넣지 않음).
- 결과 줄: 순위, 점수, 법령명, 별표/조문, 시행일, 효력 상태, 파일, 쪽, 본문 앞 200자. 형식: `contracts/ask-cli.md`.
- `run_eval.py`: `eval_questions.yaml`의 질문마다 Retrieve → 상위 5개 안에 기대 문서(`doc_id`)가 있으면 통과. 결과 표를 `services/rag-docs/eval_results/<날짜>.md`로 남김.

## R10. 2차로 미룬 것

- D의 근거 카드·사례: 검토 뒤 세 번째 데이터 소스 `cards/`(문서 등급 "참고", 효력 상태 "draft→검토됨")로 넣어 같은 시험 질문으로 비교.
- 시행규칙 별표 8 과거 구간: 1~21쪽 파일 + `effective_status=과거`로 추가 동기화, 에이전트 기본 필터는 `현행·구판`.
- 업무편람 2025.12판·대기오염공정시험기준 현행본: 구하면 추가.
