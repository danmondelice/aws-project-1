data "archive_file" "application" {
  type        = "zip"
  source_dir  = "${path.module}/application"
  output_path = "${path.module}/.terraform/cloud-appointment-app.zip"

  excludes = [
    "__pycache__",
    "*.pyc"
  ]
}

resource "aws_s3_bucket" "application_artifacts" {
  bucket_prefix = "${local.name_prefix}-app-artifacts-"
  force_destroy = true

  tags = {
    Name    = "${local.name_prefix}-app-artifacts"
    Purpose = "immutable-application-delivery"
  }
}

resource "aws_s3_bucket_public_access_block" "application_artifacts" {
  bucket = aws_s3_bucket.application_artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "application_artifacts" {
  bucket = aws_s3_bucket.application_artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "application_artifacts" {
  bucket = aws_s3_bucket.application_artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "application_artifacts" {
  bucket = aws_s3_bucket.application_artifacts.id

  rule {
    id     = "expire-old-application-versions"
    status = "Enabled"

    filter {
      prefix = "releases/"
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.application_artifacts]
}

resource "aws_s3_object" "application" {
  bucket = aws_s3_bucket.application_artifacts.id
  key    = "releases/cloud-appointment-app.zip"
  source = data.archive_file.application.output_path

  etag                   = data.archive_file.application.output_md5
  content_type           = "application/zip"
  server_side_encryption = "AES256"

  depends_on = [
    aws_s3_bucket_public_access_block.application_artifacts,
    aws_s3_bucket_server_side_encryption_configuration.application_artifacts,
    aws_s3_bucket_versioning.application_artifacts
  ]
}
