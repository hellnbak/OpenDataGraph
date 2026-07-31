output "database_endpoint" {
  value = aws_db_instance.this.address
}

output "database_master_secret_arn" {
  value     = aws_db_instance.this.master_user_secret[0].secret_arn
  sensitive = true
}

output "evidence_bucket" {
  value = aws_s3_bucket.evidence.id
}

output "opensearch_endpoint" {
  value = aws_opensearch_domain.this.endpoint
}

output "runtime_policy_arn" {
  value = aws_iam_policy.runtime.arn
}
