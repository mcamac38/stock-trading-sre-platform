output "ecr_repository_name" {
  description = "Name of the ecr repository"
  value = aws_ecr_repository.backend.name
}

output "ecr_repository_url" {
  description = "URL of the ECR Repository"
  value = aws_ecr_repository.backend.repository_url
}

output "ecr_repository_arn" {
  description = "ARN of the ECR Repository"
  value = aws_ecr_repository.backend.arn
}