# smokestack-guard

[SK 플래닛 - 파이널 프로젝트] EPA CAMPD/ECMPS 배출 데이터를 전국 단위로 RAW 누적 수집하는 파이프라인. TMS는 제외하고 정제 단계에서 재검토한다.

## 방향

- 메인 소스: EPA CAMPD / ECMPS (규제 기준, 장기 이력이 정형화되어 있음)
- 실데이터만 사용 (샘플/가짜 데이터 경로 없음), append-only RAW 저장
- Airflow DAG `smokestack_guard_epa_daily`: 하루 1회, 활성 monitoring plan 전체의 직전·현재 분기 export

## 빠른 시작

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # EPA_API_KEY 입력
python -m pytest -q
```

emissions export 수집 (유효한 monitorPlanId 필요):

```bash
PYTHONPATH=src python -m smokestack_guard.data.collector --source epa \
  --monitor-plan-id <ID> --year 2025 --quarter 1 --output-dir data/raw
```

## 구조

- `src/smokestack_guard/data/collector.py`: 수집 + RAW 누적 저장
- `src/smokestack_guard/data/epa_probe.py`: 엔드포인트 상태 점검
- `src/smokestack_guard/data/pipeline.py`: 위험도/경고 계산 (data.go.kr TMS 스키마 기준, EPA 스키마로 재작성 예정)
- `dags/smokestack_guard_daily.py`: EPA 일 1회 DAG
- `dags/smokestack_guard_ktms_30min.py`: K-TMS(data.go.kr) 30분 스냅샷 DAG
- `data/raw/`: RAW CSV/JSON (git 제외)

## 할 일
1. 정제(Silver) 스키마 및 경고 로직을 EPA 구조로 재작성, TMS 도입 재검토 (RAW 데이터를 확인한 뒤 판단)
