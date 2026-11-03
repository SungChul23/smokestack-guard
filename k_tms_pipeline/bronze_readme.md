# k_tms_pipeline: 굴뚝 TMS Bronze 수집
Cleansys 굴뚝자동측정기기 측정결과 OpenAPI를 10분마다 호출 후 응답 원문을 MinIO에 적재하는 Pipeline

## 1. 준비
- Docker Desktop
- Cleansys API KEY

## 2. 처음 실행
- .env파일에 DATA_GO_KR_KEY에 발급받은 API KEY 삽입
```powershell
cd k_tms_pipeline
```

- DB 초기화, 관리자 계정 생성
```powershell
docker compose up -d postgres minio
docker compose up airflow-init
docker compose up -d airflow-webserver airflow-scheduler
```

## 3. 접속
- Airflow: http://localhost:8080, admin, admin
- MinIO: http://localhost:9001, .env의 MINIO_ROOT_...

## 4. 프로젝트 구조
```
k_tms_pipeline/
├── docker-compose.yml        Airflow, Postgres, MinIO 구성
├── docker/
│   ├── Dockerfile            Airflow 이미지 (2.10.5, Python 3.12)
│   └── minio.Dockerfile      MinIO 소스 빌드
├── dags/
│   ├── cleansys_rltm_poll.py DAG (10분 주기: 가져오기 후 점검)
│   └── cleansys/
│       ├── client.py         API 호출, 재시도, 원문 점검
│       └── bronze.py         MinIO 저장, 메타 작성
├── scripts/                  프로브/시험 스크립트 (수동 실행용)
└── requirements.txt
```




