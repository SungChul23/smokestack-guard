# smokestack-guard

이 브랜치는 EPA 데이터 수집을 사용하지 않고, 대만 CEMS와 K-TMS 정제 파이프라인에 집중합니다.

## 방향

- 메인 소스: 대만 CEMS 월별 JSONL, K-TMS 10분 스냅샷
- 출력: Silver Parquet 파티션 (`data/silver/tw_cems`, `data/silver/ktms`)
- 원본 데이터는 읽기 전용으로 유지하고, 정제 단계에서 필요한 값만 Silver로 생성

## 빠른 시작

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
PYTHONPATH=src python -m pytest -q
```

## 구조

- `src/smokestack_guard/silver/tw_cems.py`: 15분 관측 데이터를 30분 Silver로 변환
- `src/smokestack_guard/silver/ktms.py`: K-TMS 스냅샷을 long-form Silver로 변환
- `data/silver/`: Silver parquet 출력 디렉터리

## 현재 목표

1. 대만 CEMS 15분 → 30분 정제 규칙을 월 단위로 안정화
2. K-TMS 상태/비율 값 정제를 검증
3. 187 기반 고급 구간 검증은 이후 단계에서 진행
