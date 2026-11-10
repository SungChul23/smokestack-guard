# Tasks: TW CEMS 재수집 원본 비교 (bronze2 → silver2)

**Input**: `specs/a-platform/006-tw-cems-silver2-compare/` (spec.md, plan.md)

**실행 주체**: Terraform plan·apply와 Glue 실행 명령은 사람(A)이 한다. 에이전트는 코드·문서와 `fmt`/`validate`, 로컬 테스트까지 한다.

## Phase 1: 원본 비교

- [x] T001 두 원본의 월별 파일 크기 비교 (`aws s3 ls`): 36개월, 차이 −88KB ~ +113KB
- [x] T002 Athena 줄 단위 비교: 줄 수 같음, 기존에만 있는 줄 0, 새 원본에만 있는 줄 3,432,371
- [x] T003 비교용 임시 테이블 삭제 (`DROP TABLE tms_eda.tw_cems_line_cmp`)

## Phase 2: US1 Silver2

- [x] T004 `main.tf` 컬럼 정의를 `locals`로 이동 (기존 리소스 변경 없음)
- [x] T005 `silver2.tf`: Silver2 역할·Job, ML-ready2 역할·Job, `tms_silver2` DB·테이블 2개
- [x] T006 출력값 3개, 변수 설명 보완
- [x] T007 `AGENTS.md` S3 경로 규칙에 `bronze2/`, `silver2/` 추가, `services/tms-silver/README.md` 실행 명령
- [x] T008 plan·apply (11 to add) — 사람
- [x] T009 한 달 시험 2024-03 (`ok` 451,984 → 471,113) — 사람
- [x] T010 나머지 35개월 `--only-missing` (실패 0) — 사람
- [x] T011 Athena 비교: 월별 status, 슬롯 상태 변화, 복구 슬롯 시간대, 48슬롯 미만 날 (66 = 66)

## Phase 3: US2 ML-ready2 (v2)

- [x] T012 #32 브랜치에 main 머지 (PR #30·#31·#34) — 사람
- [x] T013 `ml_ready_spark.py`에 v2 적격 규칙 반영, 가짜 Silver에 빈 슬롯을 사이에 둔 기준치 변경 사례(F006) 추가, 테스트 85개 통과 (005 범위 코드)
- [x] T014 plan·apply (패키지·스크립트·Job 인자 6개 변경) — 사람
- [x] T015 ML-ready2 build (18,436,379행) — 사람
- [x] T016 정답지 경로 변수·읽기 권한·`--reference` 추가 → plan·apply (2개 변경) — 사람
- [x] T017 compare `passed=True` — 사람

## Phase 4: US3 비교와 공유

- [x] T018 Athena ML-ready 비교: 월별 증가·양성 비율, 새로 생긴 행 분포, 굴뚝별 증가율
- [x] T019 spec·plan·tasks 작성 (이 문서)
- [ ] T020 C·E에게 결과 공유: 학습 데이터는 `tms_silver2.tw_cems_ml_ready` (Glue 결과, C pandas와 35컬럼 일치)

## 남은 결정 (팀)

- [ ] D1 정식 원본·Silver 경로: `bronze2/`·`silver2/`를 그대로 정식으로 쓸지, 정식 경로로 옮길지 (C·B)
- [ ] D2 기존 `bronze/tw_cems/historical/`(91.2GB, 약 $2.3/월)과 `silver/tw_cems*` 정리 여부와 시점. 원본 버킷 객체 삭제라 사람이 확인하고 결정한다
- [ ] D3 C의 T039(원본 공백 재다운로드 여부): 다시 받아도 공백 66일은 그대로라 "재다운로드로 채울 수 없음"으로 닫을 수 있다
- [ ] D4 정리할 때 `silver2.tf`를 지우거나, 정식 경로로 바꾸면 기존 Job의 입력 경로를 바꾼다
