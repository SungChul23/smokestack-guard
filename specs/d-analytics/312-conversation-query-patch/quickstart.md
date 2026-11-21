# 로컬 확인

Node 테스트: `node --test D/dashboard-preview/regional-console/tests/query-router/conversation-session.test.cjs`.

작업대: `node D/query-router-lab/build-workbench.cjs`, 기존 가상환경 Python으로 `workbench_server.py --port 8776` 실행 후 `/continuity.html`을 연다. 테스트 전용 완료 기록으로 ‘어제는? → 어제는? → NOx는? → 그 전날은?’을 확인한다. 준비한 후 ‘가상 실행·전달’을 눌러야 다음 질문의 근거가 된다.

실제 조회기 미연결 상태를 유지하며 가상 완료는 simulation으로 표시한다. 운영 계정·S3·외부 LLM을 사용하지 않는다. 법령 주제 전환 뒤에는 날짜 후속을 확인으로 돌려야 한다.
