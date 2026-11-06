# Spark 마이그레이션 체크리스트 (이슈 #14)

대만 CEMS Silver(`tw_cems.py`, pandas)를 Spark(`tw_cems_spark.py`)로 옮긴 결과와 실행 방법.
Spark 구현은 pandas 구현과 같은 규칙을 쓰며, 항목 매핑·허용 코드·컬럼 목록은 `tw_cems.py`에서 가져온다.

## 1. 실행 환경

- 운영 대상: AWS Glue 4.0 / 5.0 (Spark 3.3 / 3.5). 코드는 Spark 3.3 이상에서 동작한다.
- 로컬 검증: **Docker (Linux, Spark 3.5.4, Java 17)**. native Windows는 쓰지 않는다.
  - 이 PC의 PySpark 4.1.0은 `socketserver.UnixStreamServer`가 없어 import에 실패하고, Java도 11이라 Spark 4가 요구하는 17보다 낮다.
  - 그래서 Windows 우회 코드(`sitecustomize.py` 등)는 쓰지 않는다. 삭제해도 된다.
- 검증 이미지: `apache/spark:3.5.4-scala2.12-java17-python3-ubuntu` 위에 아래를 설치한 것.
  - `numpy<2`, `pandas==2.2.3`, `pyarrow==16.1.0`, `pyspark==3.5.4`, `boto3`, `pytest`
  - Spark 3.5가 pandas 3.0과 호환되지 않아 pandas를 2.2로 고정했다. `tw_cems.py`는 두 버전 모두에서 같은 결과를 낸다.

```dockerfile
FROM apache/spark:3.5.4-scala2.12-java17-python3-ubuntu
USER root
RUN pip3 install --no-cache-dir "numpy<2" "pandas==2.2.3" "pyarrow==16.1.0" "pyspark==3.5.4" boto3 pytest
USER spark
```

## 2. 실행 방법

저장소 루트에서 (이미지 이름 `sg-spark:3.5`로 빌드했다고 가정):

```bash
# 테스트 (pandas 19개 + Spark 패리티 1개)
docker run --rm -v "$PWD:/work" -w /work -e PYTHONPATH=/work/src -e HOME=/tmp sg-spark:3.5 \
  python3 -m pytest tests/test_silver_spark.py tests/test_silver.py -q -p no:cacheprovider

# 실데이터 패리티 (원본 JSON Lines의 일부를 떼어 pandas와 Spark 결과를 비교)
head -n 1500000 2025-10.jsonl > data_sample/s2025-10.jsonl
docker run --rm -v "$PWD:/work" -v "$PWD/data_sample:/data" -w /work -e PYTHONPATH=/work/src -e HOME=/tmp sg-spark:3.5 \
  python3 scripts/validate_spark_parity.py /data/s2025-10.jsonl --master "local[4]"

# 변환 실행 (year/month 파티션 Parquet로 저장)
python3 -m smokestack_guard.silver.tw_cems_spark <source.jsonl> <output_dir>
```

## 3. 검증 결과

| 확인 | 결과 |
| --- | --- |
| 단위 테스트 (모든 `status` 경우를 pandas와 비교) | 통과. `ok`·`not_monitored`·`other_code`·`partial`·`invalid` 5종이 모두 한 번씩 검증됨 |
| 실데이터 2025-10 앞 150만 줄 (`T`/공백 시각 혼재) | 785,635행 일치, 모든 컬럼 불일치 0 |
| 실데이터 2024-01 앞 150만 줄 | 756,172행 일치, 불일치 0 |
| 실데이터 2023-11 앞 100만 줄 (초 없는 시각) | 501,356행 일치, 불일치 0 |
| 쓰기 경로 | 다른 달을 같은 폴더에 쓰면 기존 달이 유지되고, 같은 달을 다시 쓰면 그 달만 교체됨 (동적 파티션 덮어쓰기) |

- 비교는 `stack_code × item × unit × ts_kst` 키로 정렬한 뒤 13개 컬럼을 모두 확인한다 (실수는 1e-9 상대 오차).
- 위 실데이터 검증은 **월 전체가 아니라 앞부분**이다. 월 전체와 36개월 전체 비교는 Glue에서 한다.

## 4. 남은 일

- [ ] Glue에서 실행 (5장)
  - [ ] 입력 `s3://smokestack-tms-raw-952900391026/bronze/tw_cems/historical/YYYY-MM.jsonl`
  - [ ] 출력 위치·쓰기 권한 확정 (김성철 님)
  - [ ] 한 달 전체를 pandas 결과(`silver_months`)와 비교
- [ ] ML-ready의 Spark 이식 (윈도우 함수). 현재는 pandas만 있고, 입력이 물질별 수백~천만 행이라 우선순위는 낮다
- [ ] 실행 비용·시간 측정 (워커 수, 월당 실행 시간)
- [ ] CI에 Spark 패리티 테스트 추가 (PySpark가 없는 환경에서는 건너뜀)

## 5. Glue 작업

| 항목 | 값 |
| --- | --- |
| 스크립트 | `scripts/glue_tw_cems_silver.py` (Glue 5.0 권장, 4.0 가능) |
| 입력 `--source` | `s3://smokestack-tms-raw-952900391026/bronze/tw_cems/historical/YYYY-MM.jsonl` (월당 약 2~3GB) |
| 출력 `--output` | `s3://<bucket>/silver/tw_cems/` (위치·권한은 김성철 님과 확정 필요) |
| 패키지 | `--extra-py-files smokestack_guard.zip` (`src/smokestack_guard` zip). Glue 이미지에 pandas가 없으면 `--additional-python-modules pandas` |

- 월은 서로 독립이고, 같은 달을 다시 돌리면 그 달 파티션만 교체된다.
- 완료 기준: 같은 달의 pandas Silver와 모든 컬럼이 일치하고, 36개월이 규칙 차이 없이 실행될 것.
- 2023-11은 11-27 16:30에서 끊기고 2023-12는 12-01 00:00~06:15가 없다 (원본 공백, 채우지 않음).

## 6. 알아둘 점

- Spark의 `toPandas()`와 `createDataFrame(pandas)`는 pandas 버전에 민감하다. 테스트는 pandas를 거치지 않고 Spark DataFrame을 직접 만든다.
- `NaN`과 `null`: pandas의 NaN을 Spark에서는 null로 통일했다 (`m_value`가 문자열 `"nan"`이면 값 없음).
- 같은 시각에 값이 다른 행이 2건일 때 `code2` 앞뒤 값은 시간순이 같아 정렬이 모호하다. 실데이터 비교에서는 차이가 없었다.
- Spark는 결과를 정렬해서 저장하지 않는다. 비교·조회 시 `stack_code, item, unit, ts_kst`로 정렬한다.
