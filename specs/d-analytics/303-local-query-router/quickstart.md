# 구현 후 검증 안내

2026-11-13 현재는 명세·계획·작업 목록만 작성했다. 아래 새 모듈/테스트 명령은 해당 작업을 구현한 후에 실행할 절차이며 현재 실행·통과한 테스트가 아니다.

## 준비

- 현재 로컬 대시보드와 보관 자료가 있어야 한다. 진입점 `D/dashboard-preview/regional-console/ui-review-20261109/hatch-thin.html`.
- Node 내장 테스트, Python 기존 정적 서버 사용. 추가 설치·AWS 로그인·키 입력·모델 호출 불필요.
- 새 checkout에는 ignore된 D 실행 기반/자료가 없을 수 있다. 이 경우 로컬 자료 준비를 먼저 확인하고 새 환경 재현 성공으로 보고하지 않는다.
- 원본 자료·좌표 해시를 기록하고 구현 대상 파일을 백업한다. `.specify` 설치 파일과 브랜치는 변경하지 않는다.

## 실행 명령

```powershell
# 이미 실행 중인 8765 서버가 있으면 재실행하지 않는다.
python -m http.server 8765 --directory D/dashboard-preview/regional-console

# 303 테스트를 구현한 후
node --test D/dashboard-preview/regional-console/tests/query-router/*.test.cjs
node D/dashboard-preview/qa-query-router-20261113.cjs

# 기존 회귀 검사
node --test D/dashboard-preview/regional-console/tests/chart-ratio-axis.test.cjs
node D/dashboard-preview/qa-chart-focus-20261112.cjs
node D/dashboard-preview/qa-law-evidence-20261112.cjs
node D/dashboard-preview/qa-map-inline-20261112.cjs
node D/dashboard-preview/qa-naver-drag-20261112.cjs
```

브라우저 검사는 기존 CDP 환경을 사용한다. 네이버 실제 지도 검사는 이미 준비된 앱 설정/연결을 재사용하는 별도 사례로 수행하고, 검사하지 않았으면 미검증으로 적는다. 지도 타일 요청은 모델/수집 API 호출과 별도로 센다. 운영 권한 검증 성공으로 표현하지 않는다.

## 독립 검증 시나리오

1. **US1**: 굴뚝 선택 → NOx 최신값 → 실제 측정시각·원문·비실시간 확인. 최신 상태가 문자인 표본에서 이전 숫자 대체 없음. CO 요청은 잠금.
2. **US2**: “NOx 높은 10개” → 범위·지표 선택. 선택 전 조회/조작 호출 0. UI/정책 버전을 바꾼 뒤 이전 버튼은 무효. F~K 원본 카탈로그는 각 예상 경로·추출 조건·금지 실행을 대조한다.
3. **US3**: 명시한 사업장 이동·12시간·NOx 표시·표 열기 → 즉시 반영 및 안내. 두 지도 배경에서 반복. 읽기 질문으로 지도 이동 없음. 느린 A 응답 중 B로 전환하여 늦은 A의 화면 변경/답변 덮어쓰기 없음.
4. **US4**: 0/10/20/상태/NULL 테스트 표본 → 평균 10·최대 20·포함 3/제외 2. 실자료와 테스트 전용 표본은 구분. 어제/최근 6시간 기준 분리. 100%의 `>`/`≥` 구분. 화면 사업장 방문 순서를 바꿔도 최신 전체 순위 동일. 전체 이력 평균 순위는 미지원.
5. **US5**: 기존 법령 검색 결과·원문·출처 동일. ‘오늘’은 실제 날짜를 기준일로 전달하고 미확보 날짜 대체 없음. 예측·원인·운전 제어는 실행하지 않음.
6. **공통 상태**: 단계/경계/버전을 바꾸면 지도·목록·범례·설명이 함께 변경. 대표 상태가 잠금 물질에서 나왔을 때 NOx 원인으로 설명하지 않음. 수치 부등호·사용자 경고선·원본 기준값은 별도로 유지.

## 결과 기록

`D/query-router-planning/validation-results.json`에 단위/브라우저/실제 지도별 실행 여부·통과/실패·미지원 범위·외부 호출 여부·원본 해시를 남긴다. 미실행 검사는 통과로 표시하지 않는다. 모델/학습/법령 적용성/정식 인증은 이번 검증 대상이 아니다.
