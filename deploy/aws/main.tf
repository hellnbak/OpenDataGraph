data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  tags = merge(var.tags, {
    Application = "OpenDataGraph"
    ManagedBy   = "Terraform"
  })
}

resource "aws_db_subnet_group" "this" {
  name       = var.name
  subnet_ids = var.subnet_ids
  tags       = local.tags
}

resource "aws_security_group" "database" {
  name_prefix = "${var.name}-database-"
  description = "OpenDataGraph PostgreSQL access"
  vpc_id      = var.vpc_id
  tags        = local.tags
}

resource "aws_vpc_security_group_ingress_rule" "database" {
  for_each                     = toset(var.application_security_group_ids)
  security_group_id            = aws_security_group.database.id
  referenced_security_group_id = each.value
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_db_instance" "this" {
  identifier                   = var.name
  engine                       = "postgres"
  engine_version               = "16.4"
  instance_class               = "db.m7g.large"
  allocated_storage            = 100
  max_allocated_storage        = 1000
  storage_type                 = "gp3"
  storage_encrypted            = true
  db_name                      = "opendatagraph"
  username                     = "opendatagraph"
  manage_master_user_password  = true
  multi_az                     = true
  backup_retention_period      = 14
  deletion_protection          = true
  skip_final_snapshot          = false
  final_snapshot_identifier    = "${var.name}-final"
  db_subnet_group_name         = aws_db_subnet_group.this.name
  vpc_security_group_ids       = [aws_security_group.database.id]
  performance_insights_enabled = true
  apply_immediately            = false
  tags                         = local.tags
}

resource "aws_s3_bucket" "evidence" {
  bucket_prefix = "${var.name}-evidence-"
  force_destroy = false
  tags          = local.tags
}

resource "aws_s3_bucket_public_access_block" "evidence" {
  bucket                  = aws_s3_bucket.evidence.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_security_group" "opensearch" {
  name_prefix = "${var.name}-opensearch-"
  description = "OpenDataGraph OpenSearch access"
  vpc_id      = var.vpc_id
  tags        = local.tags
}

resource "aws_vpc_security_group_ingress_rule" "opensearch" {
  for_each                     = toset(var.application_security_group_ids)
  security_group_id            = aws_security_group.opensearch.id
  referenced_security_group_id = each.value
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}

resource "aws_opensearch_domain" "this" {
  domain_name    = var.name
  engine_version = "OpenSearch_2.17"

  cluster_config {
    instance_type          = "m7g.large.search"
    instance_count         = 2
    zone_awareness_enabled = true
    zone_awareness_config {
      availability_zone_count = 2
    }
  }

  ebs_options {
    ebs_enabled = true
    volume_type = "gp3"
    volume_size = 100
  }

  encrypt_at_rest {
    enabled = true
  }

  node_to_node_encryption {
    enabled = true
  }

  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }

  vpc_options {
    subnet_ids         = slice(var.subnet_ids, 0, 2)
    security_group_ids = [aws_security_group.opensearch.id]
  }

  access_policies = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = var.opensearch_principal_arns }
      Action    = "es:ESHttp*"
      Resource  = "arn:aws:es:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:domain/${var.name}/*"
    }]
  })

  tags = local.tags
}

data "aws_iam_policy_document" "runtime" {
  statement {
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = [
      "${aws_s3_bucket.evidence.arn}/evidence/*",
      "${aws_s3_bucket.evidence.arn}/graph-exports/*",
    ]
  }
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.evidence.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["evidence/*", "graph-exports/*"]
    }
  }
  statement {
    actions   = ["es:ESHttpDelete", "es:ESHttpGet", "es:ESHttpHead", "es:ESHttpPost", "es:ESHttpPut"]
    resources = ["${aws_opensearch_domain.this.arn}/*"]
  }
}

resource "aws_iam_policy" "runtime" {
  name_prefix = "${var.name}-runtime-"
  policy      = data.aws_iam_policy_document.runtime.json
  tags        = local.tags
}
