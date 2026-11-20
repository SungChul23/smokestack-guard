# 검증 절차

1. `node D/map-timeline/build-frames.cjs`로 기존 로컬 자료에서 재생용 파생 JSON을 만든다. 원본은 읽기만 한다.
2. `node --test D/dashboard-preview/regional-console/tests/query-router/map-time.test.cjs`로 판정/시각 경계를 검사한다.
3. 기존 8765 프론트 새로고침 후 지도 내부 원형 시계의 바늘 클릭/드래그 놓기, 년월일시분 플립, 앞뒤/재생/최신 복귀를 확인한다. 우측 라인업에서 ‘초과 예상’으로 바꾸면 최신 기준 예측 대기 목록만 표시되고 지도 과거 시각과는 독립이다.
4. `node D/map-timeline/qa-timeline.cjs`로 실제 자료·시간 동기화·NULL·카메라·차트 유지·지연 응답·모바일을 검사한다.

보관 최신시각은 실제 현재시각이 아니다. 지도 시간 이동은 하단 차트의 독립 조회 범위를 바꾸지 않는다. 미래 초과 예상은 예측 미연결 대기 칸이다.
