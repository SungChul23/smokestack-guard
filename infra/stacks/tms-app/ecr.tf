# 앱 이미지 저장소 (research R13). 태그 = 커밋 SHA, 바꿀 수 없음, 최근 10개만 남김.

resource "aws_ecr_repository" "app" {
  for_each = local.apps

  name                 = "tms-dashboard-${each.key}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  for_each = local.apps

  repository = aws_ecr_repository.app[each.key].name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}
