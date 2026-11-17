'''
- spark_ingest: Kafka 토픽의 메시지를 읽어 Bronze 모양의 파일로 쓴다
'''
import argparse
from synth_train import ingest_core, s3_sink

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", default="kafka:19092")
    parser.add_argument("--topic", default="tms.synthetic.train")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--max-offsets", type=int, default=500, help="배치 하나가 읽는 최대 메시지 수")
    parser.add_argument("--out", default=None, help="로컬 폴더에 쓸 때의 출력 폴더")
    parser.add_argument("--sink", choices=["local", "s3"], default="local")
    parser.add_argument("--bucket", default=None)
    parser.add_argument("--endpoint", default=None, help="MinIO 주소. AWS S3는 비워 둔다")
    parser.add_argument("--create-bucket", action="store_true", help="버킷이 없으면 만든다 (로컬 MinIO 전용)")
    args = parser.parse_args()
    if args.sink == "local" and not args.out:
        parser.error("--sink local에는 --out이 필요")
    if args.sink == "s3" and not args.bucket:
        parser.error("--sink s3에는 --bucket이 필요")

    client = None
    if args.sink == "s3":
        client = s3_sink.make_client(args.endpoint)
        if args.create_bucket:
            s3_sink.ensure_bucket(client, args.bucket)

    from pyspark.sql import SparkSession
    spark = (SparkSession.builder.appName("synth-train-ingest").config("spark.sql.shuffle.partitions", "1").getOrCreate())
    spark.sparkContext.setLogLevel("WARN")

    df = (spark.readStream.format("kafka")
          .option("kafka.bootstrap.servers", args.bootstrap)
          .option("subscribe", args.topic)
          .option("startingOffsets", "earliest")
          .option("includeHeaders", "true")
          .option("maxOffsetsPerTrigger", args.max_offsets)
          .load()
          .select("key", "value", "headers"))

    def handle(batch_df, batch_id):
        msgs = [{
            "key": bytes(r["key"]),
            "value": bytes(r["value"]),
            "headers": [(h["key"], bytes(h["value"])) for h in (r["headers"] or [])],
        } for r in batch_df.collect()]                        
        if args.sink == "s3":
            n = ingest_core.write_messages_to(
                msgs, lambda prefix, files: s3_sink.write_files_s3(client, args.bucket, prefix, files))
        else:
            n = ingest_core.write_messages(msgs, args.out)
        print(f"[batch {batch_id}] {n}개 기록")
        
    query = (df.writeStream
             .foreachBatch(handle)
             .option("checkpointLocation", args.checkpoint)
             .trigger(availableNow=True)
             .start())
    query.awaitTermination()
    spark.stop()

if __name__ == "__main__":
    main()