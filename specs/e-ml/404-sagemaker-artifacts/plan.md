# Implementation Plan: 404 SageMaker 학습 Job·아티팩트 관리

**Spec** [spec.md](spec.md) · [Issue #20](https://github.com/SungChul23/smokestack-guard/issues/20)

## Summary

모델별 학습 실행과 입력·결과를 추적하고 기존 아티팩트를 보호한다.

## Technical Context & Project Structure

[sagemaker_job.py](../../../services/ml-training/sagemaker_job.py)는 SDK 3.x ModelTrainer를 사용한다. train 채널 → SM_CHANNEL_TRAIN, SM_MODEL_DIR → SageMaker 결과 아카이브. 현재 A 코드 기본값은 ml.r5.2xlarge 1대·3,600초이며 CLI에서 변경 가능하다. [artifacts.py](../../../services/ml-training/artifacts.py)가 원자적 저장을 담당한다.

## Constitution Check

기존 수집과 원천 계약을 보존한다. 승인된 입력·시간·평가 조건을 기록하고 동일한 비교 집합의 근거를 남긴다. AWS 실행과 적용은 별도 권한 절차를 따른다.

## Decisions & Open Questions

초기 ml.m5.xlarge 설정과 RF 실험의 10,800초는 실행 이력이다. 신규 모델 결과의 팀 지정 버킷은 `sagemaker-ap-northeast-2-952900391026`이다. 과거 URI는 기록으로 유지하며 버킷 정책 문서화는 기존 CLI가 이를 강제한다는 의미가 아니다.
