# 작업 목록

- [x] T1 spec·plan 작성
- [x] T2 `stack_facts.py`: 굴뚝 지정 기준·최근 측정값 읽기
- [x] T3 `summarizer.py`: 요청·응답·검증(조문 번호, 숫자, chunk_id, 단정 표현)
- [x] T4 `evidence.py`: 요약 모드, 관대한 검색, 이유별 안내, 원문 발췌 되돌림
- [x] T5 `compound.py`: evidence 부분의 굴뚝 사실 연결, 후속 이어받기
- [x] T6 `api.py`: 요약기 구성
- [x] T7 단위 시험 `tests/test_doc_summary.py`
- [x] T8 검색 재현율 측정(문서 질문 300개, 요약 모델 없이)
- [x] T9 조합 질문 결정적 시험
- [x] T10 실제 모델 시험 재료(요약기 요청 배치, 평가 스크립트) 준비
- [ ] T11 실제 모델(Haiku) 시험 실행 (재영 요청 시)
- [ ] T12 부족한 문서 확보: 별표 8·9, 초과부과금, 과태료·벌칙, 고시 본문

## 색인 카드·벡터 색인·지침 보강 (2026-11-19)
- [x] cards.py: 카드 스키마, 결정적 대체 카드, 검증(`verify_card`), 카드 파일 로더(원문 지문 + 검증), 카드 지문, LLM 카드 생성 요청(CARD_SYSTEM/CARD_TOOL)
- [x] vindex.py: 글자 n-gram TF-IDF 색인, 밀집 색인(신경망), 저장·로드·지문 검사, FastEmbed 임베딩기(local_files_only), 미리 계산한 질문 벡터 임베딩기(시험용)
- [x] evidence.py: VectorRetriever, HybridRetriever(RRF, 조문 직접 지정 우선, 실패 시 degraded), build_retriever(색인 대체), raw_window(원문 창), 카드 모드 요약기 입력
- [x] summarizer.py: 카드 모드 요청 글, Source(card·full_text), 전체 원문으로 검증, 출처에 없는 제재 주제 차단, 지침 보강(모호 되묻기·문서 밖·범위 밖)
- [x] build_index.py: `python -m app.agent.build_index [--neural --cache DIR]`
- [x] 시험: tests/test_cards_index.py 19개(전체 346개 통과), 재현율·토큰 비교, 오라클 장치 점검, 조합 질문 채점 자체 점검
- [ ] (메인) 카드 생성: `card_tools.py build` → Haiku → `apply` → `build_index`(+ D 환경 `--neural`)
- [ ] (메인) 요약기 재시험: `sum2_build.py build` → Haiku 25배치 → `apply` → `eval`
- [ ] (메인) 조합 질문 시험: `combo_build.py prompts` → Haiku 7개 → `planbuild` → Haiku → `apply` → `eval`
- [ ] 계획기 회귀 시험(공격·후속 이어받기)
