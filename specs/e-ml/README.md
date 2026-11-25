# E파트 판정·AI 경고·MLOps 명세

담당 E (`doeun-1202`), 번호 대역 401–500. 각 기능의 spec·plan·tasks·checklist를 독립적으로 관리한다.

| 번호 | 기능 | 이슈 | 구현 근거 |
|---|---|---|---|
| 401 | [시나리오 A 모델 학습](401-scenario-a-ml-training/spec.md) | [Issue #20](https://github.com/SungChul23/smokestack-guard/issues/20) | [`services/ml-training/`](../../services/ml-training/) |
| 402 | [ML-ready 계약·Feature·적격성 및 누수 방지](402-ml-ready-data-contract/spec.md) | [Issue #20](https://github.com/SungChul23/smokestack-guard/issues/20) | [`services/ml-training/`](../../services/ml-training/) |
| 403 | [모델 평가·임계값·Event Recall](403-model-evaluation/spec.md) | [Issue #20](https://github.com/SungChul23/smokestack-guard/issues/20) | [`services/ml-training/`](../../services/ml-training/) |
| 404 | [SageMaker 학습 Job·아티팩트 관리](404-sagemaker-artifacts/spec.md) | [Issue #20](https://github.com/SungChul23/smokestack-guard/issues/20) | [`services/ml-training/`](../../services/ml-training/) |
| 405 | [대만 CEMS·국내 실측·합성 데이터 혼합](405-scenario-b-data-mix/spec.md) | [Issue #58](https://github.com/SungChul23/smokestack-guard/issues/58) | [`services/ml-training-b/`](https://github.com/SungChul23/smokestack-guard/tree/caf114c20c3d430a5d714368fec76ebbec9add71/services/ml-training-b) |
| 406 | [출처별 가중치 및 모델 실험](406-source-weight-experiments/spec.md) | [Issue #58](https://github.com/SungChul23/smokestack-guard/issues/58) | [`services/ml-training-b/`](https://github.com/SungChul23/smokestack-guard/tree/caf114c20c3d430a5d714368fec76ebbec9add71/services/ml-training-b) |
| 407 | [시나리오 B 성능 평가·국내 외부 검증](407-scenario-b-external-validation/spec.md) | [Issue #58](https://github.com/SungChul23/smokestack-guard/issues/58) | [`services/ml-training-b/`](https://github.com/SungChul23/smokestack-guard/tree/caf114c20c3d430a5d714368fec76ebbec9add71/services/ml-training-b) |

이 문서 정리는 401 원본이 있는 `20-e-ml-model-training`에서 진행했다. B 구현 링크는 `58-e-ml-scenario-b`의 확인된 리비전을 가리킨다. 로컬 A 브랜치에 B 소스가 포함됐다는 의미는 아니다.

## 후속 후보와 실험 이력

- **N3-C / S3-C**는 V2 부분 이력 후보이다. 대만 단독 학습과 부분 이력 입력·NaN 적격성은 별도 명세가 필요하다. 401~407의 완전 이력 및 원래 B 혼합 정책은 각각 해당 문서를 따른다.
- **N3.1-C** A형 보조 모델은 대만 Validation의 거의 같은 A형 FP 행 수(32,367 → 32,366)에서 A형 Event Recall이 59.87% → 57.53%였다. 비교 지점은 미채택이고 Test는 미평가다. 이전 시간 초과와 구현 이력은 [n31 경로](https://github.com/SungChul23/smokestack-guard/tree/caf114c20c3d430a5d714368fec76ebbec9add71/services/ml-training-b/n31)에 연결한다.
- **S3.1-C** 혼합·부분 이력 후보는 S3-C 대비 11/11~21 탐색에서 사건 탐지가 247 → 260건으로 늘었으나 FP가 1,950 → 2,111행으로 증가했다. 11/22 단일 날짜에서는 평가 가능 사건 25건 중 11 → 10건을 탐지했다. 교체 근거 부족으로 S3-C 유지를 권고한 평가 이력이다. [s31 경로](https://github.com/SungChul23/smokestack-guard/tree/caf114c20c3d430a5d714368fec76ebbec9add71/services/ml-training-b/s31)
- **LSTM**은 후속 아키텍처로 별도 명세가 필요하다. 시계열 입력, 결측 표현, 학습 방식, 기준선 비교 및 독립 평가를 따로 정의한다. 401~407에서 적용 여부나 번호를 확정하지 않는다.
