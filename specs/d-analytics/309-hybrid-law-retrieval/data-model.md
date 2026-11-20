# 데이터 모델

- IndexedPassage: passage_id, evidence_id, text, document_id, source_text_sha256. 원문 본문에서 분할하고 사람이 만든 유도 질문을 본문 대신 넣지 않는다.
- IndexManifest: model_name, dimensions, corpus_binding(문서 version·모든 chunk ID/원문해시), passages, matrix SHA256, 모델/패키지 버전.
- VectorContext: question(검색기 입력 그대로), corpus_binding, model_name, candidates[{id,score}], min_score. 다른 원문/문서 지문·알 수 없는 ID·비정상 점수·중복은 거절한다.
- SearchResult: 기존 evidence 구조 유지. retrieval_method와 의미 후보 사용·실패 대체 메타정보를 추가한다. 유사도는 확률·법적 적용 점수가 아니다.
