# 구현 계획: 지도 공통 시각·하루 재생

작성일 2026-11-13 · 기능 D 304 · 기존 main 유지

## 요약과 기술 문맥

기존 정적 HTML/일반 JavaScript/로컬 JSON 유지. Python 정적 서버와 Node 26 내장 테스트·기존 Chrome CDP로 검증한다. 신규 패키지·서버·API·자격증명 사용 없음.

`data-model.js`의 초기 지도 판정과 새 `map-time-model.js`의 재생 판정을 공통 순수 함수로 통일한다. 공통 지원 설정을 데이터 준비 이전에 로드하고 NOx/SOx로 제한한다. 굴뚝별 마지막 시각이 아니라 글로벌 최신시각과 정확히 같은 관측을 선택한다.

`StackDashboard`에 별도의 mapTime과 지도 시점 적용 함수를 추가한다. getReferenceTime과 차트 독립 기간을 바꾸지 않는다. 렌더는 카메라 이동 없는 데이터 갱신 경로를 사용한다. mapTime 변경은 지도/집계/목록만 바꾸고 차트·데이터 이력 로딩을 자동으로 반복하지 않는다.

`D/map-timeline/build-frames.cjs`는 이미 로컬에 있는 원문 이력과 콤마 보정 인덱스를 읽어 최신까지 48개 시점의 두 물질 원문을 정적 JSON으로 만든다. 일별 순위 파일은 상태문자를 NULL로 축약해 원문 구분이 불가능하므로 재생용 원문으로 사용하지 않는다. 굴뚝 ID 배열과 프레임별 `[ID인덱스, NOx원문, NOx기준, SOx원문, SOx기준]` 행으로 중복 ID를 줄인다. 범위 밖 원본·좌표는 변경하지 않는다.

`map-timeline.js`는 지도 아래에 48칸 슬라이더/시각/앞뒤/재생/정지/최신 복귀/속도를 넣는다. 프레임 JSON은 첫 조작에서만 읽고 재사용한다. 읽기 실패·최신 복귀·새 요청은 sequence로 늦은 표시를 무효화한다. 자동 실행 없음, 탭 숨김 정지, 끝에서 멈춤. 예측 칸은 ‘연결 대기’로만 만든다.

## 원칙 점검

수집 연속성: 수집기/스케줄/원본 변경 없음. 비밀값: 신규 사용 없음. 인프라: 변경/배포 없음. 계약: 기존 로컬 표현 재사용, 모델 출력 계약 대기. 비교: 모델 학습/평가 없음. 설명: 기준시각·원문 결측·보관자료임을 명시. 모든 관문 통과, 별도 승인/예외 없음. `.specify/extensions.yml` 없음. 설치된 Spec Kit 파일 변경 없음. Windows python3 별칭 대신 기존 Python 3.12의 python 사용.

## 프로젝트 구조

- 명세/계획/작업: `specs/d-analytics/304-map-shared-timeline/`
- 순수 판정: `D/dashboard-preview/regional-console/map-time-model.js`
- 화면: `ui-review-20261109/map-timeline.js`, `map-timeline.css`, 기존 console-app.js/data-model.js/진입점
- 생성: `D/map-timeline/build-frames.cjs`, `assets/map-timeline-20261112.json`
- 검사/보고: `D/map-timeline/`, 기존 `tests/query-router/`

## 실행 순서와 한계

후속 UI 변경 반영: 원형 24시간 SVG slider를 지도 내부에 두고 48개 시각과 일대일 대응한다. 바늘 드래그 중에는 preview 시각/플립만 갱신하며, pointerup 때 기존 select로 한 번 적용한다. 단일 클릭·앞뒤 버튼·키보드를 대안으로 제공하고 지도 pointer/wheel 전파를 막는다. 다크/라이트와 reduced-motion을 지원한다. 우측 라인업의 관측/예상 토글은 지도 시각과 독립이며 예상 기준은 불변 reference를 쓴다. 현재 예측 연동은 없으므로 대기 상태만 표시한다.

US1 공통 판정 → US2 실제 원문 48칸/시간 제어 → US3 예측 빈 칸 → 회귀 검사. 초기 최신 판정은 기존 latest.js에서만 읽는다. 과거 재생은 추가 파일이므로 첫 조작 때 전송량이 생긴다. 지역·좌표·지도 SDK/사용자 설정과 독립이다. 전체 D 경로는 기존 .gitignore로 무시되어 다른 checkout 자동 재현을 보장하지 않는다.
