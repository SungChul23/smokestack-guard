# Implementation Plan: 401 시나리오 A 모델 학습

**Spec** [spec.md](spec.md) · [Issue #20](https://github.com/SungChul23/smokestack-guard/issues/20)

## Summary

대만 CEMS로 물질별 분류·회귀 모델을 학습하고 각 실행을 재현한다.

## Technical Context & Project Structure

[train_entrypoint.py](../../../services/ml-training/train_entrypoint.py) → [train_n1.py](../../../services/ml-training/train_n1.py) / [train_s1.py](../../../services/ml-training/train_s1.py) / [train_rf.py](../../../services/ml-training/train_rf.py). 모델에는 Train의 X/y만 전달한다. XGBoost 기준선은 seed 42와 기본 설정을 사용하고, RN1·RS1 V1.1은 트리 100개, 깊이 20, min_samples_leaf=1, n_jobs=2, seed 42를 사용한다.

## Constitution Check

기존 수집과 원천 계약을 보존한다. 승인된 입력·시간·평가 조건을 기록하고 동일한 비교 집합의 근거를 남긴다. AWS 실행과 적용은 별도 권한 절차를 따른다.

## Decisions & Open Questions

이전 깊이 3/10 등 초기 제안은 채택 설정이 아니다. D4·W10(N1-C), W5(S1-C)는 기준선과 분리된 실험 분기이며 코드 존재만으로 채택을 뜻하지 않는다.

## 변경 이력

401 통합 문서의 원본은 [분리 전 plan.md](https://github.com/SungChul23/smokestack-guard/blob/4c31c393de9e33a218a2799e1ecf6b118543882b/specs/e-ml/401-scenario-a-ml-training/plan.md)에 보존되어 있다. 이전 요구사항과 작업의 새 위치는 [401 문서 이관표](README.md#문서-이관표)를 참조한다.
