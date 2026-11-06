output "bucket_name" {
  description = "원본 보존 S3 버킷 이름"
  value       = aws_s3_bucket.this.bucket
}

output "bucket_arn" {
  description = "원본 보존 S3 버킷 ARN"
  value       = aws_s3_bucket.this.arn
}
