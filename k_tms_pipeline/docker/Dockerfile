# Airflow 버전 
FROM apache/airflow:2.10.5-python3.12

# 추가 라이브러리
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.12.txt"
