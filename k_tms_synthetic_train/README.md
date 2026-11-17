# k_tms_synthetic_train — K-TMS 학습용 합성 데이터

K-TMS(굴뚝 TMS) 학습용 합성 데이터를 **하루 단위로 만들고**, 실측 수집(cleansys)처럼 **Kafka → Spark → Bronze**로 쌓는다. 실측 경로(`tms_cleansys/`)에는 쓰지 않고, 학습용 전용 경로 `tms_synthetic_train/`에만 쓴다.

- spec: `specs/b-collection/103-synthetic-training-pool/` (spec · plan · tasks · [quickstart](../specs/b-collection/103-synthetic-training-pool/quickstart.md) · [contracts](../specs/b-collection/103-synthetic-training-pool/contracts/synthetic-train-layout.md) · [data-model](../specs/b-collection/103-synthetic-training-pool/data-model.md))
- 평가·시연용 합성(102)은 `k_tms_synthetic/`에 있고 이 폴더는 그것을 바꾸지 않는다.

## 무엇을 하나

| 단계 | 하는 일 | 모듈 |
|---|---|---|
| 모양 곡선 | 모양(EXCEED · PLATEAU · OVER · SPIKE · GRADUAL · OTHER)마다 범위 안에서 궤적을 뽑고, 의도한 모양으로 판정되지 않으면 다시 뽑음 | `shapes.py`, `assemble.py` |
| 하루 생성 | 날짜 하나의 에피소드를 seed로 만들고 30분 슬롯 48개의 스냅샷으로 묶어 Bronze 모양 파일로 씀. 자정을 걸치는 에피소드는 전날 시작분을 seed로 다시 만들어 이음 | `daily.py`, `pack.py`, `generate.py` |
| 점검·요약 | 구조·해시·슬롯·이어짐·모양·중복·실측 굴뚝 코드 충돌 점검, (날짜 × 성분 × 모양) 집계 | `validate.py`, `summary.py` |
| 발행 | 파일을 Kafka 메시지로 바꿔 발행. 과거는 배치(`publish`), 지금부터는 `release`(run_ts가 지난 최근 스냅샷만, 멱등) | `publish.py`, `release.py` |
| 적재 | Spark가 토픽을 읽어 메시지를 파일 4개로 되돌려 로컬 폴더 또는 S3 호환 저장소(MinIO)에 씀 | `ingest/spark_ingest.py`, `ingest_core.py`, `s3_sink.py` |

핵심 약속:
- 같은 날짜·같은 설정이면 **바이트까지 같은** 결과(날짜를 만드는 순서와 무관, Windows와 Linux 동일).
- Kafka → Spark → Bronze로 만든 폴더는 파일 모드(`generate-day`)로 만든 폴더와 바이트가 같다(로컬 폴더, MinIO 모두 확인).
- 합성은 경로(`tms_synthetic_train/`)와 굴뚝 코드(`SYN-T-<날짜>-<성분>-<모양>-<번호>`)로만 실측과 구분된다.

## 실행 (요약, 자세한 순서는 quickstart)

```powershell
python -m pip install -r requirements.txt
python -m pytest -q

python -m synth_train generate-day --date 2026-11-15 --out out
python -m synth_train backfill --from 2026-10-30 --to 2026-11-15 --out out
python -m synth_train validate --out out
python -m synth_train summary --manifest-dir out/manifest

python -m synth_train publish --src out                    # 배치 발행 (Kafka 필요)
python -m synth_train release --config config/daily.yaml   # 방출: run_ts가 지난 최근 스냅샷만 (10분마다 실행)
```

Spark 적재(`ingest/spark_ingest.py`)는 컨테이너 `sg-spark:3.5`에서 실행한다. 명령은 quickstart의 4번을 따른다.

### 방출을 10분마다 돌리는 예

스케줄러 구성은 이 spec의 범위 밖이고, 아래는 예시다. 둘 다 **발행 → 적재** 순서로 두 명령을 부른다.

- Windows 작업 스케줄러: 10분마다 `python -m synth_train release --config config/daily.yaml` 실행 후 `docker run … ingest/spark_ingest.py …`
- cron: `*/10 * * * * cd /path/k_tms_synthetic_train && python -m synth_train release --config config/daily.yaml && ./run_ingest.sh`

## 폴더

```
synth_train/      코드 (아래 "복사한 모듈" 외는 신규)
config/           daily.yaml (하루 에피소드 수, 모양 범위, 길이, 참조 선택, 경로)
ingest/           spark_ingest.py (Kafka → 파일/S3, 컨테이너에서 실행)
kafka/            docker-compose.yml (Kafka KRaft 단일 브로커), .env.example
docker/           Dockerfile.spark (sg-spark:3.5, Kafka 커넥터 jar 포함)
tests/            단위 테스트, tests/integration/ (폴더·S3 비교 스크립트)
data/             커밋 금지: ref_stats.csv (참조 통계)
out/              커밋 금지: 생성 결과
```

## 복사한 모듈 (출처: 102 `k_tms_synthetic/`, 커밋 `6a6acaf`)

`snapshot`, `schedule`, `writer`, `episode`, `stats`, `plan`, `scenarios/trajectory`와 해당 테스트 9개, `tests/fixtures/ref_stats_sample.csv`. 패키지 이름을 `synth_train`으로 바꾸었고(102의 `synth`와 한 환경에서 import가 충돌하지 않게), 다음을 고쳤다.

- `snapshot.py`: 학습용 루트 `TRAIN_ROOT = "tms_synthetic_train"`, 에피소드 폴더가 없는 경로(`build_prefix`의 `root`·빈 `episode_id`), gzip 헤더의 OS 표지를 `0xff`로 고정.
- `writer.py`: 두 루트(`tms_synthetic`, `tms_synthetic_train`)만 허용, `tms_cleansys/`는 계속 거부.

102의 평가용 전용 모듈(`compare.py`, 8개 시나리오 설정, `expected/`)과 `validate.py`는 복사하지 않았다(`validate.py`는 학습용 구조에 맞게 새로 작성).

## 주의

- **비밀값**(MinIO·AWS 접속 정보)은 환경 변수로만 받고 코드·설정·compose·로그·커밋에 쓰지 않는다. `kafka/.env`, `data/`, `out*/`, `ckpt*/`는 커밋하지 않는다.
- `tms_cleansys/`(실측)에는 어떤 코드도 쓰지 않는다(`check_prefix`가 거부하고 테스트로 강제한다).
- 하루 에피소드 수(실측 양성과 1:1)와 모양 범위는 **시작값**이다. 조정은 `config/daily.yaml`의 숫자만 바꾼다.
- 합성이 Silver → ML-ready로 흐르려면 C의 Silver 읽기 경로 변경(`tms_synthetic_train/`)과 E의 검증 데이터 `SYN-` 제외가 필요하다(후속, PR 본문 참고).
- AWS S3 적재는 A와 버킷·권한을 정한 뒤 같은 코드로 한다(`--endpoint` 없이 AWS 자격 증명). 이 폴더는 AWS 리소스를 만들지 않는다.
