# Quickstart: 학습용 합성 데이터 생성 → Kafka → Spark → Bronze

모든 명령은 `k_tms_synthetic_train/` 폴더에서 실행한다(PowerShell). 접속 정보 같은 비밀값은 화면·파일·커밋에 남기지 않는다.

## 0. 준비

```powershell
python -m pip install -r requirements.txt
python -m pytest -q                                   # 전체 통과 확인
```

- 참조 통계 `data/ref_stats.csv`가 있어야 한다(커밋하지 않음, `stats_version = ref-1030-1110`).
- Kafka·Spark 단계는 Docker Desktop이 필요하다.

## 1. 하루 생성과 backfill (파일 모드, Docker 불필요)

```powershell
python -m synth_train generate-day --date 2026-11-15 --out out
python -m synth_train backfill --from 2026-10-30 --to 2026-11-15 --out out
python -m synth_train validate --out out              # 기대: 통과
python -m synth_train summary --manifest-dir out/manifest
```

- 날짜마다 스냅샷 48개. 같은 날짜는 항상 같은 바이트이고 날짜를 만드는 순서와 무관하다.
- `out/tms_synthetic_train/…`(Bronze 모양)와 `out/manifest/<날짜>.jsonl`이 생긴다.

## 2. Docker 환경 (처음 한 번)

```powershell
docker build -t sg-spark:3.5 -f docker/Dockerfile.spark docker
docker compose -f kafka/docker-compose.yml up -d
docker exec sg-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --topic tms.synthetic.train --partitions 1 --replication-factor 1
```

## 3. 발행 (배치)

```powershell
python -m synth_train publish --src out               # out의 스냅샷을 run_ts 순서로 발행
docker exec sg-kafka /opt/kafka/bin/kafka-get-offsets.sh --bootstrap-server localhost:9092 --topic tms.synthetic.train
```

## 4. Spark 적재

로컬 폴더로:

```powershell
New-Item -ItemType Directory -Force out_kafka, ckpt_kafka | Out-Null
docker run --rm --network sg-net `
  -v "${PWD}:/work" -v "${PWD}/out_kafka:/out" -v "${PWD}/ckpt_kafka:/ckpt" `
  -w /work -e PYTHONPATH=/work -e HOME=/tmp `
  sg-spark:3.5 /opt/spark/bin/spark-submit --master "local[2]" ingest/spark_ingest.py `
  --bootstrap kafka:19092 --out /out --checkpoint /ckpt
python tests/integration/compare_dirs.py out/tms_synthetic_train out_kafka/tms_synthetic_train   # 기대: 같음
python -m synth_train validate --out out_kafka                                                  # 기대: 통과
```

로컬 MinIO(S3 호환)로: MinIO를 켜고 접속 정보를 **현재 세션의 환경 변수로만** 읽는다.

```powershell
docker start k_tms_pipeline-minio-1
Get-Content ..\k_tms_pipeline\.env | Where-Object { $_ -match '^(MINIO_ROOT_USER|MINIO_ROOT_PASSWORD)=' } | ForEach-Object { $k,$v = $_ -split '=',2; Set-Item -Path "Env:$k" -Value $v }
New-Item -ItemType Directory -Force ckpt_s3 | Out-Null
docker run --rm --network sg-net `
  -v "${PWD}:/work" -v "${PWD}/ckpt_s3:/ckpt" `
  -w /work -e PYTHONPATH=/work -e HOME=/tmp -e MINIO_ROOT_USER -e MINIO_ROOT_PASSWORD `
  sg-spark:3.5 /opt/spark/bin/spark-submit --master "local[2]" ingest/spark_ingest.py `
  --bootstrap kafka:19092 --checkpoint /ckpt --sink s3 `
  --endpoint http://host.docker.internal:9000 --bucket sg-synth-bronze --create-bucket
# 확인: MinIO 콘솔(http://localhost:9001)의 sg-synth-bronze 버킷에서 tms_synthetic_train/ 객체 수 = 스냅샷 수 x 4 (816개면 3,264개)
```

- `host.docker.internal`로 MinIO에 닿지 않으면 `docker network connect --alias minio sg-net k_tms_pipeline-minio-1` 후 `--endpoint http://minio:9000`을 쓴다.
- 체크포인트 폴더를 지우고 다시 실행하면 토픽을 처음부터 다시 읽는다. 같은 메시지는 같은 경로·같은 바이트로 쓰이므로 결과는 같다(멱등).
- 토픽을 지우고 다시 만들었다면 체크포인트 폴더도 같이 지운다.

## 5. 방출 (지금부터, 30분마다)

```powershell
python -m synth_train release --config config/daily.yaml                       # run_ts가 지금 이전이고 최근 3시간 안인 스냅샷만 발행
python -m synth_train release --config config/daily.yaml --lookback-min 2000   # 운영 시작 직후·오래 건너뛴 뒤 한 번 따라잡기
```

- 어제·오늘·내일 하루치가 없으면 먼저 생성한다. 몇 번 실행해도 결과가 같다(멱등).
- Bronze에 파일이 생기려면 발행 뒤에 Spark 적재(4번)도 실행해야 한다. 스케줄러는 두 명령을 30분마다 순서대로 부르면 된다(스케줄러 구성은 후속).
- 시험용으로 시각을 바꾸려면 `--now 2026-11-16T03:00:00+00:00`처럼 **시간대를 붙여서** 준다.

## 6. 정리 (시험용 폴더·토픽)

```powershell
Remove-Item out_check, out_kafka, ckpt_kafka, ckpt_s3 -Recurse -Force -ErrorAction SilentlyContinue
docker exec sg-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic tms.synthetic.train
```
