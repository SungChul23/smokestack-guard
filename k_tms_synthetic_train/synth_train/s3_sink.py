'''
- s3_sink: Bronze 파일을 s3 호환 저장소에 씀
'''
import gzip
import hashlib
import json
import os
from synth_train import writer

# s3 클라이언트. endpoint가 있으면 MinIO, 없으면 AWS 기본 자격 증명
def make_client(endpoint = None):
    import boto3
    if not endpoint:
        return boto3.client("s3")
    return boto3.client(
        "s3", endpoint_url = endpoint,
        aws_access_key_id = os.environ["MINIO_ROOT_USER"],
        aws_secret_access_key = os.environ["MINIO_ROOT_PASSWORD"],
        region_name = "ap-northeast-2"
    )

# 버킷이 없으면 버킷 생성
def ensure_bucket(client, bucket: str) -> None:
    try:
        client.head_bucket(Bucket = bucket)
    except Exception:
        client.create_bucket(Bucket = bucket)

# 올라간 원문을 다시 읽어 meta의 해시와 같은지 확인 
def _verify(client, bucket: str, prefix: str) -> None:
    gz = client.get_object(Bucket=bucket, Key=f"{prefix}/snapshot.json.gz")["Body"].read()
    meta_raw = client.get_object(Bucket=bucket, Key=f"{prefix}/snapshot.meta.json")["Body"].read()
    try:
        raw = gzip.decompress(gz)
        meta = json.loads(meta_raw.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"올라간 파일을 읽을 수 없음 ({type(e).__name__}). 확정 표지를 쓰지 않음") from e
    if hashlib.sha256(raw).hexdigest() != meta["sha256_raw"]:
        raise ValueError("원문 해시가 meta와 다름. 확정 표지를 쓰지 않음")

# 파일 묶음을 bucket/prefix/ 아래에 쓴다. 같은 키에 같은 바이트라 다시 써도 결과가 같다
def write_files_s3(client, bucket: str, prefix: str, files: dict, commit: bool = True) -> str:
    writer.check_prefix(prefix)                                         # tms_cleansys/ 같은 경로는 여기서 거부
    for name in writer.DATA_NAMES:
        client.put_object(Bucket=bucket, Key=f"{prefix}/{name}", Body=files[name])
    _verify(client, bucket, prefix)
    if commit:
        for name in writer.COMMIT_NAMES:
            client.put_object(Bucket=bucket, Key=f"{prefix}/{name}", Body=files[name])
    return f"s3://{bucket}/{prefix}"