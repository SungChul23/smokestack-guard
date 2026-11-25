# Implementation Plan: 405 대만 CEMS·국내 실측·합성 데이터 혼합

**Spec** [spec.md](spec.md) · [Issue #58](https://github.com/SungChul23/smokestack-guard/issues/58)

## Summary

세 출처를 계약에 맞춰 Train에 결합하고 국내 실측으로 검증·테스트한다.

## Technical Context & Project Structure

[config.py](https://github.com/SungChul23/smokestack-guard/blob/caf114c20c3d430a5d714368fec76ebbec9add71/services/ml-training-b/config.py) → [dataset.py](https://github.com/SungChul23/smokestack-guard/blob/caf114c20c3d430a5d714368fec76ebbec9add71/services/ml-training-b/dataset.py) → [split.py](https://github.com/SungChul23/smokestack-guard/blob/caf114c20c3d430a5d714368fec76ebbec9add71/services/ml-training-b/split.py) → [mixed_dataset.py](https://github.com/SungChul23/smokestack-guard/blob/caf114c20c3d430a5d714368fec76ebbec9add71/services/ml-training-b/mixed_dataset.py). 국내는 Athena tms_silver2 / tms-eda, awswrangler + FOR VERSION AS OF, ctas_approach=False. Iceberg 원본 Parquet 직접 읽기를 금지한다.

## Constitution Check

기존 수집과 원천 계약을 보존한다. 승인된 입력·시간·평가 조건을 기록하고 동일한 비교 집합의 근거를 남긴다. AWS 실행과 적용은 별도 권한 절차를 따른다.

## Decisions & Open Questions

합성의 참고 기간은 전달 기준 11/10까지다. 이 기간과 겹치는 초기 Validation 제안 11/07~10은 사용하지 않는다. 생성 계보·시설 중복 및 출처별 계산식 일치는 별도 검증 항목이다.
