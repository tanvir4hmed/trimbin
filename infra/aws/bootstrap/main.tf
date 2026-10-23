terraform {
  required_version = ">= 1.10, < 2.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}
provider "aws" {
  region = "us-east-1"
  default_tags { tags = { Project = "trimbin", ManagedBy = "terraform" } }
}
data "aws_caller_identity" "trimbin" {}
resource "aws_s3_bucket" "trimbin_state" {
  bucket = "trimbin-tfstate-${data.aws_caller_identity.trimbin.account_id}"
  lifecycle { prevent_destroy = true }
}
resource "aws_s3_bucket_versioning" "trimbin_state" {
  bucket = aws_s3_bucket.trimbin_state.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "trimbin_state" {
  bucket = aws_s3_bucket.trimbin_state.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_public_access_block" "trimbin_state" {
  bucket                  = aws_s3_bucket.trimbin_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
output "state_bucket" { value = aws_s3_bucket.trimbin_state.id }
