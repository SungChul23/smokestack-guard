# Implementation Plan: 403 모델 평가·임계값·Event Recall

**Spec** [spec.md](spec.md) · [Issue #20](https://github.com/SungChul23/smokestack-guard/issues/20)

## Summary

동일한 평가 단위에서 분류·회귀 성능과 경보 부담을 비교한다.

## Technical Context & Project Structure

[evaluation.py](../../../services/ml-training/evaluation.py)와 [train_entrypoint.py](../../../services/ml-training/train_entrypoint.py)에서 행 지표와 임계값 고정 적용을 구현한다. 일부 실험의 Recall ≥65% 최대 Precision 지점은 보조 비교로 기록한다. 사건 분석은 동일 굴뚝·물질에서 정확한 30분 간격의 <90→≥90을 한 사건으로 정의하고 -60/-30분 두 시점이 모두 평가 가능한 사건을 별도 집계한다.

## Constitution Check

기존 수집과 원천 계약을 보존한다. 승인된 입력·시간·평가 조건을 기록하고 동일한 비교 집합의 근거를 남긴다. AWS 실행과 적용은 별도 권한 절차를 따른다.

## Decisions & Open Questions

A 공통 코드에 사건 집계와 ppm 환산 검증이 일괄 연결된 상태는 아니다. 운영 오경보 기준·성능 합격점은 별도 합의 대상이다.
