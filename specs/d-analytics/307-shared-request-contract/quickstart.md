# 재현

`node --test D/dashboard-preview/regional-console/tests/query-router/request-contract.test.cjs`

같은 폴더의 `*.test.cjs`로 기존 회귀를 검사한다. 전문/혼합 출력 누락, 출력 부정, 참고 조문을 가진 절차 검색, typed 슬롯과305 임의 계획을 대조한다. 외부 API는 필요하지 않다.

변경점·호환성 차이·미해결 사항은 D/query-router-lab/shared-contract-20261115/CHANGELOG_KO.md에 모은다.

로컬 작업대 번들: `node D/query-router-lab/build-workbench.cjs`. 기존 8768 작업대 서버에서 확인한다. 운영 페이지와 외부 LLM API의 연결 완료를 의미하지 않는다.

307 검증 산출물은 `D/query-router-lab/shared-contract-20261115/release-*`에 보존한다. 34,999개 회귀의 경로 보존과 신규 질문 의미 정확도는 별도로 평가한다.
