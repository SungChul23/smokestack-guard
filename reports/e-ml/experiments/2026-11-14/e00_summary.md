# P01 / E00 — 시나리오 A 기존 산출물 조사

- 실제 조사일: 2026-11-17 (Asia/Seoul). 사용자 지정 보관 경로 날짜는 2026-11-14로 유지.
- 브랜치: `20-e-ml-model-training` / HEAD: `5f5b03ad927c8bbc8477f4f595e9810fce899719`.
- 시작 git status --porcelain: 빈 출력(미커밋 변경 없음). 기존 파일·모델·데이터·Git 이력은 수정하지 않음.
- 수행: E00 목록화·해시·객체 설정 열람·기존 결과 점검·AWS 읽기 전용 조회. fit=0, predict=0, 신규 평가=0, AWS 쓰기=0.
- 결론: E00 조사 기록 완료. 미확인 증거가 있으므로 전체 증거 게이트 충족 또는 E01 실행 완료로 표시하지 않음.

## 기준 문서

- 발견 자료: `C:\Users\NT551_11TH\Desktop\tms-test\1114_V1.2\TMS_AI_6개모델_최적화_확정_실험명세서_2026-11-13.pdf` (19페이지, SPEC-R1). SHA-256: `194c42d004ac833a4519134d1c299bff2ae153be3a7293de5f70a8776199d638`.
- 사용자 지정 `(1).pdf` 파일명과 직접 일치하는 자료는 발견하지 못함. 발견 SPEC-R1과 새로 보낸 파일의 동일성은 미확인으로 남김. 첨부 20페이지 실행계획을 최우선 명세 대신 사용하지 않음.
- 이번 작업은 정책 선택·후보 변경 없이 기존 산출물의 증거만 수집. 발견 SPEC-R1 6페이지 E00 필수 키를 manifest의 models 배열에 모델별 보존.

## 모델별 확인 상태

|모델|버전|모델·metrics·metadata|실제 완료 Job 후보|전체 파라미터|기존 국내 결과 / 행 수|E01|
|---|---|---|---|---|---|---|
|N1-C|V1.0|확인됨(각 SHA-256 기록)|확인됨(1개)|미확인: 로드 오류|확인됨 / 663,618행 / 행 위치·예측 NPZ 있음|조건부 감사 착수 가능|
|S1-C|V1.0|확인됨(각 SHA-256 기록)|확인됨(1개)|미확인: 로드 오류|확인됨 / 292,570행 / 행 위치·예측 NPZ 있음|조건부 감사 착수 가능|
|N1-R|V1.0|확인됨(각 SHA-256 기록)|확인됨(1개)|미확인: 로드 오류|확인됨 / 694,916행 / 행 위치·예측 NPZ 있음|조건부 감사 착수 가능|
|S1-R|V1.0|확인됨(각 SHA-256 기록)|확인됨(1개)|미확인: 로드 오류|확인됨 / 310,352행 / 행 위치·예측 NPZ 있음|조건부 감사 착수 가능|
|RN1|V1.1|확인됨(각 SHA-256 기록)|확인됨(1개)|확인됨|확인됨 / 694,916행 / 행별 예측 파일 부재|조건부 감사 착수 가능|
|RS1|V1.1|확인됨(각 SHA-256 기록)|확인됨(1개)|확인됨|확인됨 / 310,352행 / 행별 예측 파일 부재|조건부 감사 착수 가능|

RF metrics는 `RN1_1_metrics.json` / `RS1_1_metrics.json`으로 존재한다. 해당 폴더의 정확한 이름 `metrics.json`은 부재지만 평가 결과 자체는 부재가 아니다.

## 실제 AWS Job·입출력 경로

서울 리전 ListTrainingJobs에서 11개를 확인했고 완료 Job 6개를 DescribeTrainingJob으로 조회했다. 동일 모델 ID 완료 후보는 각각 1개다. 이름·출력 prefix만으로 로컬 joblib과의 바이트 동일성을 증명하지 않았으며 원격 tar 내용 비교는 수행하지 않았다.

### N1-C
- Job: `e-ml-n1-c-2026-11-11-04-10-34-604` / Completed
- 모델 결과: `s3://sagemaker-ap-northeast-2-952900391026/e-ml-training/n1-c-pilot/e-ml-n1-c-2026-11-11-04-10-34-604/output/model.tar.gz`
- 입력: `s3://smokestack-tms-raw-952900391026/silver2/tw_cems_ml_ready/`
- 이미지: `366743142698.dkr.ecr.ap-northeast-2.amazonaws.com/sagemaker-scikit-learn:1.9-0`
- 자원: `{'InstanceType': 'ml.m5.xlarge', 'InstanceCount': 1, 'VolumeSizeInGB': 30}`
- 실행시간 상한: `{'MaxRuntimeInSeconds': 3600}`

### S1-C
- Job: `e-ml-s1-c-2026-11-11-07-53-45-564` / Completed
- 모델 결과: `s3://sagemaker-ap-northeast-2-952900391026/e-ml-training/s1-c-pilot/e-ml-s1-c-2026-11-11-07-53-45-564/output/model.tar.gz`
- 입력: `s3://smokestack-tms-raw-952900391026/silver2/tw_cems_ml_ready/`
- 이미지: `366743142698.dkr.ecr.ap-northeast-2.amazonaws.com/sagemaker-scikit-learn:1.9-0`
- 자원: `{'InstanceType': 'ml.m5.xlarge', 'InstanceCount': 1, 'VolumeSizeInGB': 30}`
- 실행시간 상한: `{'MaxRuntimeInSeconds': 3600}`

### N1-R
- Job: `e-ml-n1-r-2026-11-11-08-13-03-632` / Completed
- 모델 결과: `s3://sagemaker-ap-northeast-2-952900391026/e-ml-training/n1-r-v1.0/e-ml-n1-r-2026-11-11-08-13-03-632/output/model.tar.gz`
- 입력: `s3://smokestack-tms-raw-952900391026/silver2/tw_cems_ml_ready/`
- 이미지: `366743142698.dkr.ecr.ap-northeast-2.amazonaws.com/sagemaker-scikit-learn:1.9-0`
- 자원: `{'InstanceType': 'ml.m5.xlarge', 'InstanceCount': 1, 'VolumeSizeInGB': 30}`
- 실행시간 상한: `{'MaxRuntimeInSeconds': 3600}`

### S1-R
- Job: `e-ml-s1-r-2026-11-11-08-40-12-903` / Completed
- 모델 결과: `s3://sagemaker-ap-northeast-2-952900391026/e-ml-training/s1-r-v1.0/e-ml-s1-r-2026-11-11-08-40-12-903/output/model.tar.gz`
- 입력: `s3://smokestack-tms-raw-952900391026/silver2/tw_cems_ml_ready/`
- 이미지: `366743142698.dkr.ecr.ap-northeast-2.amazonaws.com/sagemaker-scikit-learn:1.9-0`
- 자원: `{'InstanceType': 'ml.m5.xlarge', 'InstanceCount': 1, 'VolumeSizeInGB': 30}`
- 실행시간 상한: `{'MaxRuntimeInSeconds': 3600}`

### RN1
- Job: `e-ml-rn1-2026-11-13-01-04-59-340` / Completed
- 모델 결과: `s3://sagemaker-ap-northeast-2-952900391026/e-ml-training/rn1-v1.1/e-ml-rn1-2026-11-13-01-04-59-340/output/model.tar.gz`
- 입력: `s3://smokestack-tms-raw-952900391026/silver2/tw_cems_ml_ready/`
- 이미지: `366743142698.dkr.ecr.ap-northeast-2.amazonaws.com/sagemaker-scikit-learn:1.9-0`
- 자원: `{'InstanceType': 'ml.r5.2xlarge', 'InstanceCount': 1, 'VolumeSizeInGB': 30}`
- 실행시간 상한: `{'MaxRuntimeInSeconds': 10800}`

### RS1
- Job: `e-ml-rs1-2026-11-13-01-58-33-951` / Completed
- 모델 결과: `s3://sagemaker-ap-northeast-2-952900391026/e-ml-training/rs1-v1.1/e-ml-rs1-2026-11-13-01-58-33-951/output/model.tar.gz`
- 입력: `s3://smokestack-tms-raw-952900391026/silver2/tw_cems_ml_ready/`
- 이미지: `366743142698.dkr.ecr.ap-northeast-2.amazonaws.com/sagemaker-scikit-learn:1.9-0`
- 자원: `{'InstanceType': 'ml.r5.2xlarge', 'InstanceCount': 1, 'VolumeSizeInGB': 30}`
- 실행시간 상한: `{'MaxRuntimeInSeconds': 10800}`

## 입력 및 학습 환경의 확인 한계

- 현재 CEMS 목록: 6 Parquet / 1,714,507,867 bytes. 파일별 크기·수정 시각·ETag는 manifest에 기록.
- 현재 목록과 과거 학습 스냅샷은 동일하다고 단정하지 않음. ETag를 SHA-256으로 취급하지 않음. Parquet 다운로드·전체 데이터 스캔을 하지 않아 과거 파일별 SHA-256·실제 v1/v1/v2 값은 미확인.
- 실제 학습 컨테이너 이미지·인스턴스·시간 상한은 확인. 컨테이너에서 해결된 Python/전체 패키지 버전과 과거 학습 코드 SHA는 미확인. 현재 HEAD를 과거 학습 SHA로 대입하지 않음.
- XGBoost 4종: Windows 기존 독립 환경(XGBoost3.4.1)에서 joblib 로드 시 input stream corrupted. 과거 성공한 Linux 분석의 모델 해시와 일치하므로 파일 손상으로 단정하지 않음. 추가 환경 복구·설치·추론은 미실행.
- RF2종: 모델 get_params 전체 열람 성공. 저장 sklearn1.9.0 / 열람1.9.1 경고가 있어 동일 버전 재현은 E01에서 별도 처리.

## 기존 국내 결과 재사용

- 6종 모두 과거 분석에 기록된 모델·metrics·metadata·국내 Parquet SHA-256이 현재 파일과 일치. Feature 순서도 기존 기록·metadata 대조. Label/적격 의미의 최종 감사는 E01 범위이며 이번에 재스캔하지 않음.
- XGBoost4종: 기존 `analysis_results.json` 및 모델별 predictions.npz 확인. y/prediction(or probability)/positions/current_ratio/complete/dates 배열, 행 수·원본 위치 유일성 확인. S1-C·N1-R·S1-R 결과도 존재하므로 미실행/부재로 분류하지 않음.
- RF2종: results.json 집계는 조건부 재사용 가능. 이 기존 분석 폴더에는 RF 원본 행별 예측·키 파일이 없어 E02 동일 행 검증 및 E01 최대오차 표본 추적의 완전 재사용은 보류.
- 이전 Label 감사 기록상 분류 미래 슬롯 부족 행: NOx440 / SO₂50. 비교 가능한 분류 행의 Label 불일치는0, 회귀 missing60=0 / mismatch=0으로 기록됨. 이는 기존 기록 확인이지 신규 감사 PASS가 아님.
- 국내 파일 기간·전체 행 수는 해시가 동일한 기존 분석에서 인용: 2026-10-31~2026-11-10, 1,422,038행.

## E01 진입 판단 및 남은 항목

- 환경·정답 감사의 입력 자료는 6종 모두 확보되어 조건부 착수 가능. E01 자체 및 신규 추론을 실행하지 않음.
- 선행 확인: SPEC-R1 파일 동일성, XGBoost 동일 학습 플랫폼/패키지 로드, 실제 학습 패키지·코드 SHA, 과거 CEMS 입력 스냅샷·버전, 원격 Job 결과와 로컬 모델 해시 연결.
- RF 행별 예측 파일은 현재 조사한 기존 분석 경로에서 부재. 대체 경로 확인 또는 후속 승인 범위에서 처리하며 E00에서 신규 추론하지 않음.
- 선언: E02~E05 확대 없음. 데이터 정책·Feature·Label·분할·하이퍼파라미터 변경 없음. AWS Job 제출·S3 쓰기·Commit·Push·Merge 없음.

## 증거 파일

- `e00_manifest.json`: 모델별 파일 해시·전체 metadata/metrics·열람 파라미터·환경·기존 국내 결과 해시·예측 배열 구조·실제 AWS Job/S3 목록·불확실성 포함.
- 초기 제한 환경에서 EndpointConnectionError 후 허용된 읽기 전용 외부 조회로 성공. 각 호출과 오류는 manifest에 보존. 자격증명·키·응답 원문 전체는 저장하지 않음.
