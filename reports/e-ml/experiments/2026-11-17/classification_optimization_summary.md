# N1-C · S1-C 분류 최적화: CEMS Validation 분석 완료

## 실행 범위·증거

- 2026-11-17, 브랜치 `20-e-ml-model-training`. Docker 시작 및 독립 Linux xgboost3.4.1 --no-deps 설치는 사용자 승인 후 수행. 호스트/프로젝트 패키지·requirements는 변경하지 않음.
- 기존 모델2종으로 CEMS Validation만 배치 predict_proba. fit=0, Test 추론=0, 국내 데이터 사용=0, S3 쓰기=0, Job 제출=0.
- Windows input stream corrupted와 달리 Linux 두 모델 로드 성공. 플랫폼/환경 관련 가능성을 확인했지만 세부 원인은 이번 범위에서 단정하지 않음.
- 35열 전체 재검증 대신 필요한 Feature·Label·시각·물질·플래그·버전 열과 Validation 겹침 row-group만 읽음. 대만 UTC 표기는 확정 벽시계 의미로 해석. 기존 60분 제외된 Validation 경계를 metadata에서 그대로 사용.
- 입력 S3 파일 목록·크기·ETag·수정시각은 실행 전후 동일. ETag를 SHA256으로 간주하지 않음. 검사 사이 일시 변경 후 복구까지 차단하는 불변성 보장은 아님.
- 모델·metrics·metadata 실행 전후 SHA256 동일. Feature22 순서 및 각 모델 Validation 행 수·기준 혼동행렬·AP 저장값 일치 확인.
- 운영 임계값 적용 없음. CSV policy_id는 후보 분석용이며 기존 Baseline과 정책을 교체하지 않음.

## 목표별 실제 결과

### N1-C
- 평가 1,199,946행, 양성 28,590행, 음성 1,171,356행. AP=0.318142969273.

|목표|threshold|Precision|Recall|F2|FP|FN|경고 행|
|---|---:|---:|---:|---:|---:|---:|---:|
|baseline|0.0932040140033 | 23.87% | 69.56% | 0.503040 | 63,421 | 8,703 | 83,308|
|precision>=0.30|0.151931837201 | 30.00% | 55.92% | 0.476824 | 37,303 | 12,602 | 53,291|
|precision>=0.40|0.277207612991 | 40.01% | 31.72% | 0.330947 | 13,601 | 19,520 | 22,671|
|precision>=0.50|0.440933763981 | 50.02% | 11.33% | 0.134064 | 3,238 | 25,350 | 6,478|
|recall>=0.70|0.0911758989096 | 23.63% | 70.01% | 0.502713 | 64,695 | 8,575 | 84,710|
|recall>=0.80|0.0483307614923 | 18.31% | 80.01% | 0.478028 | 102,020 | 5,716 | 124,894|

### S1-C
- 평가 956,982행, 양성 7,112행, 음성 949,870행. AP=0.156162421021.

|목표|threshold|Precision|Recall|F2|FP|FN|경고 행|
|---|---:|---:|---:|---:|---:|---:|---:|
|baseline|0.0423957742751 | 14.88% | 44.02% | 0.316365 | 17,905 | 3,981 | 21,036|
|precision>=0.30|0.220344260335 | 30.04% | 21.13% | 0.224657 | 3,500 | 5,609 | 5,003|
|precision>=0.40|0.999884605408 | 40.01% | 7.92% | 0.094289 | 844 | 6,549 | 1,407|
|precision>=0.50|달성 불가능|||||||
|recall>=0.70|0.00248970976099 | 4.13% | 70.02% | 0.166998 | 115,676 | 2,132 | 120,656|
|recall>=0.80|3.00663579414e-39 | 0.74% | 100.00% | 0.036086 | 949,870 | 0 | 956,982|

## 해석과 후보 준비 판단

- Precision 목표는 조건을 만족하는 후보 중 Recall 최대 → Precision 최대 → 낮은 임계값으로 선택. Recall 목표는 Precision 최대 → Recall 최대 → 낮은 임계값으로 선택. 전체 고유 확률을 비교했으며 고정 격자 탐색이 아님.
- N1-C: Precision30%의 최대 Recall55.92%, Precision40%는31.72%, Precision50%는11.33%. Recall70%는Precision23.63%, Recall80%는18.31%. 오경보 감소는 가능하지만 Recall 대가가 명확함.
- S1-C: Precision30%의 최대 Recall21.13%, Precision40%는7.92%, Precision50%는불가능. Recall70%에서Precision4.13%. Recall80% 이상은 후보중 전행 양성 예측(Recall100%, Precision0.7432%)만 충족하므로 실용적 개선으로 볼 수 없음. 확률값의 계단/동점 때문에 정확히80% 후보가 없을 수 있음.
- 위 Precision/Recall 목표는 진단 요청값이며 새 운영 합격선이 아님. 운영 FP·Recall 허용량은 여전히 별도 결정. S1-C의 낮은 분리도와 임계값만으로 AP/F2최대값 개선 불가를 근거로, SPEC-R1 사전등록 W5 단일 변경의 검증 후보 준비는 타당하다고 판단. W5 개선 보장 또는 운영상 필요성 확정은 아님.
- AP는 확률 순위가 같으면 임계값만으로 변하지 않음. 이번 두 AP는 실제 새 추론에서 계산하여 저장 Baseline과 일치.

## 최소 코드 변경 및 로컬 검증

- train_s1.py: 분류 함수에 선택적 experiment_id 경로. W5만 scale_pos_weight5, XGBoost3.4.1 실행 보호. 실제 get_params와 effective Booster config·experiment 기록. S1-R 함수 AST는 HEAD와 동일.
- train_entrypoint.py: --experiment-id를 S1-C/1.1 조합에서만 전달하며 W5 metadata 보존. 기존 다른 모델 호출은 그대로.
- sagemaker_job.py: --experiment-id S1-C-V1.1-W5를 선택한 경우만 V1.1·실험 태그·하이퍼파라미터를 전달. 기존 Baseline S1-C는 V1.0 유지. W5 변경값·XGBoost 요구 버전을 review_only에 표시.
- PASS: 문법/Import, 실제 생성자 get_params 단일 차이(scale_pos_weight), 모의 Train fit호출1회·메타데이터 strictJSON, W5 review_only(m5.xlarge1대/7200초/V1.1), Baseline CLI V1.0 유지, git diff --check. 실제 fit은0회이며 RF·회귀 학습/평가는 수행하지 않음.
- 마지막 실험 태그 추가는 정적 diff로 확인. 실제 AWS 태그 등록은 미실행.

## 아직 제출 전인 이유

- 현재 requirements는 버전 무고정. 동일 이미지명만으로 V1.0 전체 패키지 재현을 보장하지 않음. W5는 xgboost3.4.1이 아니면 학습 전 실패하도록 했으며, 실제 컨테이너 의존성 고정/검증이 남음.
- 과거 학습 CEMS 파일별 내용 SHA256과 현재 입력의 동일성, 해결된 전체 학습 환경·학습 코드 SHA는 E00의 미확인 사항을 유지. 새 Training Job 제출 승인·비용·출력 권한/충돌 확인은 별도.
- review_only는 전달 설정의 로컬 검토이며 IAM·S3 쓰기 권한·훈련 성공을 검증하지 않음.

## 다음 승인 작업

W5 전용 환경 재현/의존성 고정 방식을 확정하고, 새 출력 prefix·7200초·ml.m5.xlarge1대 및 비용을 검토한 후 사용자가 실제 제출. 입력·환경의 미확인 사항을 해소하기 전 학습 성공 준비 완료라고 표시하지 않는다.

## 재사용 가능한 로컬 증거

- 분석 폴더: `C:\Users\NT551_11TH\Documents\ChatGPT\최종프로젝트\outputs\classification-opt-20261117\validation_run`.
- validation_analysis.json: S3스냅샷·읽은 row-group·모델 해시·환경·입력 행 digest·전체 실효 설정·목표별 결과.
- 모델별 validation_scores.npz: y/probability/ratio_pct/file_index/row_position. 원본 행 식별은 JSON의 파일 목록과 결합.
- 모델별 validation_curve.csv: 고유 확률별 전체 곡선. 대용량이므로 보고서 CSV에는 Baseline·요청 목표 후보12개만 요약.
- linux_validation.log, s1c_w5_review_only.json, check_candidate.py: 실행·로컬 검증 증거. 설치된 Linux 분석 라이브러리는 독립 linux-deps에만 존재.
- 초기 차단 상태의 보고서는 분석 폴더 prior_reports_before_linux에 보존. 기존 E00·모델·원본·과거 평가 파일은 덮어쓰지 않음.
