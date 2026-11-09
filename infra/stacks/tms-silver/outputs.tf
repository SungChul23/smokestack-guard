output "glue_job_name" {
  description = "Silver Glue Job 이름 (run_silver.py의 --job-name 기본값)"
  value       = aws_glue_job.tw_cems.name
}

output "glue_role_arn" {
  description = "Silver Job 실행 역할 ARN (권한 확인: quickstart §8)"
  value       = aws_iam_role.glue.arn
}

output "glue_database_name" {
  description = "Silver Glue 카탈로그 DB 이름"
  value       = aws_glue_catalog_database.silver.name
}

output "silver_table_name" {
  description = "Silver 테이블 이름 (Athena: tms_silver.tw_cems, 워크그룹 tms-eda)"
  value       = aws_glue_catalog_table.tw_cems.name
}

output "silver_location" {
  description = "Silver 데이터 S3 경로 (Spark는 이 경로로 직접 읽는다)"
  value       = "s3://${local.raw_bucket}/${local.silver_table}/"
}

output "package_md5" {
  description = "배포한 smokestack_guard.zip의 MD5 (월 실행 기록의 package_md5와 비교)"
  value       = data.archive_file.package.output_md5
}

output "ml_ready_job_name" {
  description = "ML-ready Glue Job 이름 (run_ml_ready.py의 --job-name 기본값)"
  value       = aws_glue_job.tw_cems_ml_ready.name
}

output "ml_ready_role_arn" {
  description = "ML-ready Job 실행 역할 ARN"
  value       = aws_iam_role.ml_ready.arn
}

output "ml_ready_location" {
  description = "ML-ready 데이터 S3 경로 (SageMaker·Spark는 이 경로로 읽는다)"
  value       = "s3://${local.raw_bucket}/${local.ml_ready_table}/"
}
