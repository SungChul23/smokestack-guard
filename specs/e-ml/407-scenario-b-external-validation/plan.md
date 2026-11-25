# Implementation Plan: 407 시나리오 B 성능 평가·국내 외부 검증

**Spec** [spec.md](spec.md) · [Issue #58](https://github.com/SungChul23/smokestack-guard/issues/58)

## Summary

국내 실측에서 경보 성능을 검증하고 시나리오 A와 같은 조건에서 비교한다.

## Technical Context & Project Structure

[evaluation.py](https://github.com/SungChul23/smokestack-guard/blob/caf114c20c3d430a5d714368fec76ebbec9add71/services/ml-training-b/evaluation.py)와 [train_entrypoint.py](https://github.com/SungChul23/smokestack-guard/blob/caf114c20c3d430a5d714368fec76ebbec9add71/services/ml-training-b/train_entrypoint.py)는 국내 Validation 임계값과 Test 행 지표를 처리한다. A 모델 재사용 비교는 입력·임계값·평가 키가 일치하는 별도 산출물로 관리한다.

## Constitution Check

기존 수집과 원천 계약을 보존한다. 승인된 입력·시간·평가 조건을 기록하고 동일한 비교 집합의 근거를 남긴다. AWS 실행과 적용은 별도 권한 절차를 따른다.

## Decisions & Open Questions

N2-C weights-A 저장 결과로 전달된 국내 Test는 223,205행, TP/FP/FN/TN 326/1,455/427/220,997이다. 이 수치만으로 A/B 행 동일성이나 합성의 순효과를 증명할 수 없다. 후속 후보·다른 기간 성적은 E파트 목차의 이력으로 구분한다.
