# Implementation Plan: 406 출처별 가중치 및 모델 실험

**Spec** [spec.md](spec.md) · [Issue #58](https://github.com/SungChul23/smokestack-guard/issues/58)

## Summary

분류 모델에서 국내 실측 행의 상대 가중치 효과를 분리해 검증한다.

## Technical Context & Project Structure

[mixed_dataset.py](https://github.com/SungChul23/smokestack-guard/blob/caf114c20c3d430a5d714368fec76ebbec9add71/services/ml-training-b/mixed_dataset.py) → [train_classifier.py](https://github.com/SungChul23/smokestack-guard/blob/caf114c20c3d430a5d714368fec76ebbec9add71/services/ml-training-b/train_classifier.py) → [train_entrypoint.py](https://github.com/SungChul23/smokestack-guard/blob/caf114c20c3d430a5d714368fec76ebbec9add71/services/ml-training-b/train_entrypoint.py) 및 [sagemaker_job.py](https://github.com/SungChul23/smokestack-guard/blob/caf114c20c3d430a5d714368fec76ebbec9add71/services/ml-training-b/sagemaker_job.py). B 전용 e-ml-training-b 아래 모델·실험·실행 구분을 유지한다. A 결과에는 쓰지 않는다.

## Constitution Check

기존 수집과 원천 계약을 보존한다. 승인된 입력·시간·평가 조건을 기록하고 동일한 비교 집합의 근거를 남긴다. AWS 실행과 적용은 별도 권한 절차를 따른다.

## Decisions & Open Questions

명명 규칙의 N2-R·S2-R·RN2·RS2는 예약 ID이며 이번 B 분류 경로 구현 대상은 N2-C·S2-C다. N2-C A/B/C 결과는 대화에서 확인했으나 6개 전체 Job과 채택 여부의 독립 감사는 남아 있다. 별도 후보 이력은 [E파트 목차](../README.md#후속-후보와-실험-이력)에 남긴다.
