# Implementation Plan: RAG 문서 지식 기반 (법령·고시·업무편람)

**Branch**: `80-a-rag-문서-지식-기반-s3-bedrock-knowledge-bases-opensearch` | **Date**: 2026-11-23 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/a-platform/016-rag-knowledge-base/spec.md`

## Summary

PDF 39개(대기환경보전법·시행령·시행규칙 본문과 별표, 관제센터 규정, 부과금·측정기기 고시, 환경시험검사법, 업무편람 구판)를 새 S3 문서 버킷에 올리고, **Amazon Bedrock Knowledge Bases**가 읽기(모델 파서, 머리글 제거·표 유지 지시) → 조각 → **Titan Text Embeddings V2(1024)** → 기존 OpenSearch 도메인 `tms-logs`의 새 인덱스 `rag-docs`(faiss hnsw + nori 본문)에 넣는다. 문서마다 `.metadata.json`(법령명·제목·별표 번호는 임베딩에 포함, 나머지는 거르기·인용용)을 로컬 스크립트로 만들고 검사한다. 로컬 질문 도구(`ask.py`)가 `Retrieve`/`RetrieveAndGenerate`로 조각·출처·답변을 보여 주고, 시험 질문 묶음으로 품질을 잰다.

모든 AWS 리소스(버킷, 지식 기반 역할, 지식 기반, 데이터 소스 2개)는 새 스택 `infra/stacks/tms-rag`의 Terraform으로 만든다(AWS provider 6.73에 관리형 클러스터 저장소·파싱 지시문이 있음, research R2). 인덱스와 FGAC 역할은 기존 `setup_opensearch.py`에 더한다. 도메인 접근 정책은 `tms-log-search`가 이름으로 지식 기반 역할을 찾아 허용한다.

## Technical Context

**Language/Version**: Python 3.12(로컬 스크립트), Terraform ~> 1.15.0, AWS provider ~> 6.0(잠금 6.73.0)
**Primary Dependencies**: boto3(질문 도구·인덱스 설정), pypdf(메타데이터 쪽수 확인·별표 8 자르기, 로컬 전용), 기존 `setup_opensearch.py`의 SigV4 클라이언트
**Storage**: S3 문서 버킷 `smokestack-tms-rag-952900391026`(새), OpenSearch `tms-logs` 인덱스 `rag-docs`(새)
**Testing**: pytest(메타데이터 생성·검사, 쪽 자르기, 질문 도구 출력 형식, setup 계획), ruff, `terraform fmt`·`validate`, 시험 질문 묶음(실제 지식 기반 대상, 사람이 실행)
**Target Platform**: A의 PC(WSL), AWS 서울 리전
**Project Type**: 인프라 스택 + 로컬 CLI 스크립트
**Performance Goals**: 질문 하나의 조각 결과 10초 이내(SC-006)
**Constraints**: 추가 서버 없음, 검색 도메인 메모리 최대 90% 미만(SC-007), 메타데이터 파일 10KB 이하, 값 종류 4가지, 문서 버킷에는 PDF·메타데이터만
**Scale/Scope**: 문서 39개 약 500쪽, 조각 수천 개(벡터 약 12MB + 그래프)

## Constitution Check

| 원칙 | 판정 | 근거 |
|---|---|---|
| I. 수집 연속성 | 통과 | 수집 스케줄·원본 버킷을 건드리지 않는다. 문서 버킷은 원본 버킷과 따로다. 검색 도메인 공유는 로그 수집에만 영향 가능 → 메모리 관찰(SC-007) |
| II. 비밀값 비공개 | 통과 | 비밀값 없음. 로컬 도구는 사용자 AWS 프로필을 쓴다. 문서는 공개 법령 |
| III. 코드로 만들고 적용은 사람이 | 통과 | 버킷·역할·지식 기반·데이터 소스 모두 Terraform(`tms-rag`), 인덱스·FGAC는 저장소 정의 + 사람이 실행하는 `setup_opensearch.py`. 콘솔은 결과 확인·시험 화면으로만 쓴다. 권한 목록은 research R5 |
| IV. 데이터 계약 우선 | 통과 | 메타데이터 형식·인덱스 매핑·질문 도구 출력·에이전트 연결을 contracts/에 먼저 정한다. Silver 계약과 무관 |
| V. 정직한 비교 | 해당 없음(시험 질문 통과율은 같은 질문 묶음·같은 지식 기반으로만 비교) |
| VI. 설명 가능한 결과 | 통과 | 답변마다 출처(법령명·별표·시행일·쪽·효력 상태)를 돌려준다. 구판·간접 문서를 표시한다 |
| 운영: 비용 | 기록 | 구축 1회: 모델 파서 약 500쪽 + 임베딩 → $10 이하(R8). 상시: S3 수 MB(1센트 미만), OpenSearch 추가 비용 없음(기존 도메인), 질문당 임베딩·답변 생성 비용 |
| 운영: 외부 패키지 | 기록 | `pypdf`는 로컬 메타데이터 도구(쪽수, 별표 8 자르기)에만. Lambda 없음 |

재점검(설계 뒤): 위반 없음. Complexity Tracking 없음.

## Project Structure

### Documentation (this feature)

```text
specs/a-platform/016-rag-knowledge-base/
├── spec.md
├── plan.md
├── research.md
├── data-model.md        # 메타데이터 항목, 인덱스 필드, 문서 목록 규칙
├── quickstart.md        # 적용·업로드·동기화·시험 순서
├── contracts/
│   ├── metadata-file.md     # <파일>.metadata.json 형식
│   ├── rag-index.md         # rag-docs 인덱스 매핑, FGAC 역할
│   ├── ask-cli.md           # 로컬 질문 도구 입력·출력
│   └── agent-connection.md  # D에게 넘길 호출 방법
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
infra/stacks/tms-rag/              # 새 스택
├── backend.tf  versions.tf  variables.tf  outputs.tf
├── bucket.tf                      # 문서 버킷(비공개, 암호화, 버전 관리)
├── kb_role.tf                     # 지식 기반 서비스 역할
├── knowledge_base.tf              # 지식 기반 + 데이터 소스 laws/·handbook/ (스위치 rag_kb_enabled)
└── agent_access.tf                # tms-app-server 역할에 Retrieve 권한(스위치)

infra/stacks/tms-log-search/domain.tf   # 접근 정책에 지식 기반 역할(이름으로 조회) 추가

services/rag-docs/                 # 새 폴더(A, 016)
├── README.md
├── docs_catalog.csv               # 39개 문서의 확인된 메타데이터 원장 (사람이 고침)
├── parsing_prompt.md              # 모델 파서 지시문(머리글 제거, 표 유지)
├── make_metadata.py               # 원장 + PDF → <파일>.metadata.json, 빠진 항목 목록
├── check_metadata.py              # 짝·이름·형식·값 종류·크기·쪽수 검사
├── trim_pdf.py                    # 쪽 범위 자르기(시행규칙 별표 8 → 21~55쪽)
├── stage_upload.py                # 업로드 폴더 구성(laws/·handbook/, PDF+JSON만) → aws s3 sync 명령 출력
├── ask.py                         # 로컬 질문 도구(Retrieve / RetrieveAndGenerate)
├── eval_questions.yaml            # 시험 질문 묶음(질문, 기대 문서)
├── run_eval.py                    # 시험 질문 실행 → 통과율 표
└── tests/                         # pytest

services/log-search/
├── opensearch/indices/rag-docs.json   # 인덱스 설정·매핑(새)
├── opensearch/roles/rag_kb_writer.json # rag-docs* 읽기·쓰기 역할(새)
└── setup_opensearch.py                # 인덱스 생성 단계 + 역할 매핑 추가
```

**Structure Decision**: 지식 기반은 로그 수집과 업무가 달라 새 스택 `tms-rag`로 독립 apply한다(AGENTS.md 스택 = 업무 단위). OpenSearch 안의 설정(인덱스·역할)은 도메인 설정을 이미 맡은 `setup_opensearch.py` 한 곳에 둔다. 문서 도구는 수집·로그 코드와 섞지 않게 `services/rag-docs/`에 둔다. PDF 원본은 저장소에 넣지 않는다(A의 PC·S3에만, 원장 CSV만 커밋).

## 적용 순서 (사람)

1. `tms-rag` apply (기본 `rag_kb_enabled=false`): 버킷 + 지식 기반 역할
2. `tms-log-search` apply: 접근 정책이 `tms-rag-kb` 역할을 찾아 허용
3. `setup_opensearch.py --dry-run` → 실행: `rag-docs` 인덱스, `rag_kb_writer` 역할 매핑
4. 로컬: `trim_pdf.py`(별표 8) → `make_metadata.py` → `check_metadata.py` 39/39 → `stage_upload.py` → `aws s3 sync`
5. `tms-rag` apply `-var rag_kb_enabled=true`: 지식 기반 + 데이터 소스 2개(만들 때 인덱스·권한을 검사하므로 1~3 뒤)
6. 동기화 시작(콘솔 버튼 또는 `aws bedrock-agent start-ingestion-job`) → 39개 확인
7. `ask.py`로 질문, `run_eval.py`로 시험 묶음 → 결과를 spec Status에 기록
8. 에이전트 연결: `-var agent_retrieve_enabled=true` apply, `contracts/agent-connection.md`를 D에게 공유
