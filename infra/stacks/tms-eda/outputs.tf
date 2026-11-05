output "eda_bucket_name" {
  description = "Athena EDA 전용 버킷 이름"
  value       = aws_s3_bucket.eda.id
}

output "glue_role_arn" {
  description = "변환 Job과 크롤러가 쓰는 Glue 실행 역할 ARN"
  value       = aws_iam_role.glue.arn
}

output "glue_job_names" {
  description = "변환 Glue Job 이름 목록"
  value       = keys(aws_glue_job.this)
}

output "crawler_name" {
  description = "수동 실행 크롤러 이름"
  value       = aws_glue_crawler.tw_cems_raw.name
}

output "athena_workgroup_name" {
  description = "EDA 조회용 Athena 워크그룹 이름"
  value       = aws_athena_workgroup.eda.name
}

output "glue_database_name" {
  description = "EDA Glue 카탈로그 DB 이름"
  value       = aws_glue_catalog_database.eda.name
}
