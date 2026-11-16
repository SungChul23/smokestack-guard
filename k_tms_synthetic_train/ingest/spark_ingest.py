'''
- spark_ingest: Kafka 토픽의 메시지를 읽어 Bronze 모양의 파일로 쓴다
'''
import argparse
from synth_train import ingest_core

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", default="kafka:19092")
    parser.add_argument("--topic", default="tms.synthetic.train")
    parser.add_argument("--out", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--max-offsets", type=int, default=500, help="배치 하나가 읽는 최대 메시지 수")
    args = parser.parse_args()

    from pyspark.sql import SparkSession
    spark = (SparkSession.builder.appName("synth-train-ingest").config("spark.sql.shuffle.partitions", "1").getCreate())
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
        } for r in batch_df.collect()]                        # 드라이버로 모음
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