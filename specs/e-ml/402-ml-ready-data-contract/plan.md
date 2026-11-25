# Implementation Plan: 402 ML-ready 계약·Feature·적격성 및 누수 방지

**Spec** [spec.md](spec.md) · [Issue #20](https://github.com/SungChul23/smokestack-guard/issues/20)

## Summary

C파트 입력의 의미와 시간 경계를 보존해 모델별 X/y를 만든다.

## Technical Context & Project Structure

[contract.py](../../../services/ml-training/contract.py) → [split.py](../../../services/ml-training/split.py) / [features.py](../../../services/ml-training/features.py) → [dataset.py](../../../services/ml-training/dataset.py). 대만 CEMS의 UTC 표기가 붙은 현지 벽시계는 Asia/Taipei로 해석한다. 두 단계 Parquet 스캔은 전역 시간을 확인한 뒤 물질·적격 행을 선별하고 파일 목록·지문을 비교한다.

## Constitution Check

기존 수집과 원천 계약을 보존한다. 승인된 입력·시간·평가 조건을 기록하고 동일한 비교 집합의 근거를 남긴다. AWS 실행과 적용은 별도 권한 절차를 따른다.

## Decisions & Open Questions

초기 70/15/15는 이력이다. 파일 지문은 검사 시점의 일치 여부를 확인한다. 기준치 변경·결측 제외가 원천에서 정확히 적용됐는지 표본·경계 사례로 별도 확인해야 한다.
