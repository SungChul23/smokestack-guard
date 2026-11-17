# S1-C-V1.1-W5 학습 후보 준비

## 결론
S1-C Validation 임계값 분석 완료. Precision50% 불가능, Precision40%에서 Recall7.92%, Recall80% 이상은 전행 양성으로만 달성. AP/F2 최대치의 개선은 임계값만으로 불가능하므로 사전등록 W5 검증 후보 연결을 구현했다. 운영 정책이나 개선 성공은 확정하지 않았다. 실제 fit/Job 제출은0회.

## 실행 연결
- sagemaker_job.py --model-id S1-C --experiment-id S1-C-V1.1-W5 → model-version1.1, experiment-id 전달 → train_entrypoint.py → train_s1_classifier(...,experiment_id=...).
- XGBClassifier(random_state=42,scale_pos_weight=5.0). XGBoost3.4.1 보호 검사. Baseline 생성자 대비 get_params 단일 차이를 확인했다. 다른 실효값은 동일 라이브러리 기본값 유지; baseline Booster config는 로컬 Validation 증거에 보존.
- Feature22·Label·적격·대만 CEMS·24/6/6·60분 제외·전체 적격 Train fit1회 유지. 기존 S1-R·N1-C 모델 및 RF 코드 변경 없음.
- mock검사에서 Train만 fit인자로1회 전달됨을 확인했으며 실제 fit은 호출하지 않았다. 후보 Validation/Test 평가는 기존 진입점 흐름 사용.

## 같은 Validation 비교
Baseline y/file_index/row_position와 입력 스냅샷·Feature순서·행 digest를 후보에서 대조해야 한다. 다르면 자동 교집합 비교하지 않고 중단. 후보 임계값은 동일 CEMS Validation의 F2최대·Recall우선·낮은threshold 규칙으로 선택. Test/국내로 선택 금지.

## SPEC-R1 합격 기준 — 모두 충족
- F2 >= 0.326364885620.
- AP >= 0.161162421021.
- Recall >= 0.420241844769.
- FP <= 19,695 (Baseline17,905의10% 증가상한 정수내림).
- Precision·FN·경고행도 비교. 행 동등성·환경·비용 조건을 별도 충족해야 하며 기준에 맞춰 임계값을 사후 재조정하지 않는다.

## review_only 확인된 구성
- S1-C V1.1 / S1-C-V1.1-W5 / ml.m5.xlarge1대 / 7200초.
- 입력 s3://smokestack-tms-raw-952900391026/silver2/tw_cems_ml_ready/
- 출력 검토용 prefix s3://sagemaker-ap-northeast-2-952900391026/e-ml-training/s1-c/v1.1/S1-C-V1.1-W5/
- Role arn:aws:iam::952900391026:role/service-role/AmazonSageMaker-ExecutionRole-20261104T140492
- 기존 출력과 분리. model.joblib/metrics.json/metadata.json 구조 유지. Job 이름v1-1 및 model-id/model-version/experiment-id/data-version/owner-team 태그, metadata 실제 설정·Booster config·experiment 기록.
- 실제 경로 쓰기 권한/충돌·현재 Role 권한은 이번에 검증하지 않음. 위 prefix는 설정 검토용이며 쓰기/Job 생성은 미실행.

## 남은 제출 차단
현재 requirements 무고정이므로 학습 컨테이너에 xgboost3.4.1과 기존 실효 환경이 설치되도록 별도 검증·고정이 필요하다. 다른 버전이면 W5가 fit전에 중단된다. 현재 CEMS와 과거 학습 스냅샷 내용 SHA, 실제 학습 패키지 전체를 재현했다는 증거는 미확인이다. 분석 환경(Python3.13.15/XGBoost3.4.1/sklearn1.9.1)을 과거 학습 환경으로 단정하지 않는다.

## 후속 승인 범위
W5 전용 환경 재현·단일변경 config 대조·Validation 행 동등성 검사와 제출 전 비용/권한/출력 검토가 다음 작업이다. 실제 --submit은 그 뒤 사용자 별도 승인/직접 실행이다. 자동 추가 후보·재시도·국내튜닝·Test선택은 하지 않는다.
