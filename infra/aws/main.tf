terraform {
  required_version = ">= 1.10, < 2.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
  backend "s3" {}
}
provider "aws" {
  region = var.region
  default_tags { tags = { Project = "trimbin", ManagedBy = "terraform" } }
}
variable "region" { default = "us-east-1" }
variable "instance_type" { default = "m7i-flex.xlarge" }
variable "data_gib" { default = 200 }
variable "domain" { default = "trimbin.qleam.com" }
variable "github_repository" { default = "tanvir4hmed/trimbin" }
data "aws_caller_identity" "trimbin" {}
data "aws_iam_openid_connect_provider" "trimbin_github" {
  url = "https://token.actions.githubusercontent.com"
}
data "aws_ssm_parameter" "trimbin_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}
data "aws_availability_zones" "trimbin" { state = "available" }
data "aws_ec2_managed_prefix_list" "trimbin_cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}
resource "aws_vpc" "trimbin" {
  cidr_block           = "10.73.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = "trimbin" }
}
resource "aws_subnet" "trimbin" {
  vpc_id                  = aws_vpc.trimbin.id
  cidr_block              = "10.73.1.0/24"
  availability_zone       = data.aws_availability_zones.trimbin.names[0]
  map_public_ip_on_launch = true
  tags                    = { Name = "trimbin" }
}
resource "aws_internet_gateway" "trimbin" {
  vpc_id = aws_vpc.trimbin.id
  tags   = { Name = "trimbin" }
}
resource "aws_route_table" "trimbin" {
  vpc_id = aws_vpc.trimbin.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.trimbin.id
  }
  tags = { Name = "trimbin" }
}
resource "aws_route_table_association" "trimbin" {
  subnet_id      = aws_subnet.trimbin.id
  route_table_id = aws_route_table.trimbin.id
}
resource "aws_security_group" "trimbin" {
  name        = "trimbin"
  description = "Trimbin ingress through CloudFront only; administration through SSM"
  vpc_id      = aws_vpc.trimbin.id
  ingress {
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    prefix_list_ids = [data.aws_ec2_managed_prefix_list.trimbin_cloudfront.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "trimbin" }
}
resource "aws_iam_role" "trimbin_host" {
  name               = "trimbin-host"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ec2.amazonaws.com" } }] })
}
resource "aws_iam_role_policy_attachment" "trimbin_ssm" {
  role       = aws_iam_role.trimbin_host.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
resource "aws_iam_instance_profile" "trimbin" {
  name = "trimbin"
  role = aws_iam_role.trimbin_host.name
}
resource "aws_ecr_repository" "trimbin" {
  for_each             = toset(["api", "web"])
  name                 = "trimbin-${each.key}"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
}
resource "aws_s3_bucket" "trimbin_releases" {
  bucket = "trimbin-releases-${data.aws_caller_identity.trimbin.account_id}"
  lifecycle { prevent_destroy = true }
}
resource "aws_s3_bucket" "trimbin_backups" {
  bucket = "trimbin-backups-${data.aws_caller_identity.trimbin.account_id}"
  lifecycle { prevent_destroy = true }
}
resource "aws_s3_bucket_versioning" "trimbin" {
  for_each = { releases = aws_s3_bucket.trimbin_releases.id, backups = aws_s3_bucket.trimbin_backups.id }
  bucket   = each.value
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_public_access_block" "trimbin" {
  for_each                = { releases = aws_s3_bucket.trimbin_releases.id, backups = aws_s3_bucket.trimbin_backups.id }
  bucket                  = each.value
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "trimbin" {
  for_each = { releases = aws_s3_bucket.trimbin_releases.id, backups = aws_s3_bucket.trimbin_backups.id }
  bucket   = each.value
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_ssm_parameter" "trimbin_runtime" {
  name  = "/trimbin/runtime"
  type  = "SecureString"
  tier  = "Advanced"
  value = "{}"
  lifecycle { ignore_changes = [value] }
}
resource "aws_iam_role_policy" "trimbin_host" {
  name = "trimbin-runtime"
  role = aws_iam_role.trimbin_host.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["ssm:GetParameter"], Resource = aws_ssm_parameter.trimbin_runtime.arn },
    { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
    { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"], Resource = [for r in aws_ecr_repository.trimbin : r.arn] },
    { Effect = "Allow", Action = ["s3:GetObject"], Resource = "${aws_s3_bucket.trimbin_releases.arn}/*" },
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = [aws_s3_bucket.trimbin_backups.arn] },
    { Effect = "Allow", Action = ["s3:PutObject", "s3:GetObject"], Resource = "${aws_s3_bucket.trimbin_backups.arn}/*" }
  ] })
}
resource "aws_instance" "trimbin" {
  ami                    = data.aws_ssm_parameter.trimbin_ami.value
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.trimbin.id
  vpc_security_group_ids = [aws_security_group.trimbin.id]
  iam_instance_profile   = aws_iam_instance_profile.trimbin.name
  metadata_options { http_tokens = "required" }
  root_block_device {
    volume_size = 40
    volume_type = "gp3"
    encrypted   = true
  }
  user_data                   = file("${path.module}/bootstrap.sh")
  user_data_replace_on_change = false
  tags                        = { Name = "trimbin" }
  lifecycle { ignore_changes = [ami, user_data] }
}
resource "aws_ebs_volume" "trimbin" {
  availability_zone = aws_instance.trimbin.availability_zone
  size              = var.data_gib
  type              = "gp3"
  encrypted         = true
  tags              = { Name = "trimbin-data" }
  lifecycle { prevent_destroy = true }
}
resource "aws_volume_attachment" "trimbin" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.trimbin.id
  instance_id = aws_instance.trimbin.id
}
resource "aws_eip" "trimbin" {
  domain   = "vpc"
  instance = aws_instance.trimbin.id
  tags     = { Name = "trimbin" }
}
resource "aws_cloudfront_distribution" "trimbin_live" {
  enabled     = true
  comment     = "trimbin"
  web_acl_id  = "arn:aws:wafv2:us-east-1:552794253321:global/webacl/CreatedByCloudFront-5fc2e1f9/9386f83d-335c-49dc-b1f8-14b66f09da17"
  aliases     = [var.domain]
  price_class = "PriceClass_All"
  origin {
    domain_name = aws_eip.trimbin.public_dns
    origin_id   = "trimbin"
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }
  default_cache_behavior {
    target_origin_id         = "trimbin"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    origin_request_policy_id = "b689b0a8-53d0-40ab-baf2-68738e2966ac"
  }
  restrictions {
    geo_restriction { restriction_type = "none" }
  }
  viewer_certificate {
    acm_certificate_arn      = "arn:aws:acm:us-east-1:552794253321:certificate/80b3f83b-1a4c-41a7-93b7-62abcadb3e92"
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
  tags = { Name = "trimbin" }
}
resource "aws_iam_role" "trimbin_github" {
  name               = "trimbin-github-deploy"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRoleWithWebIdentity", Principal = { Federated = data.aws_iam_openid_connect_provider.trimbin_github.arn }, Condition = { StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com", "token.actions.githubusercontent.com:sub" = "repo:${var.github_repository}:ref:refs/heads/main" } } }] })
}
resource "aws_iam_role_policy" "trimbin_github" {
  name = "trimbin-release"
  role = aws_iam_role.trimbin_github.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
    { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability", "ecr:DescribeImages", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage"], Resource = [for r in aws_ecr_repository.trimbin : r.arn] },
    { Effect = "Allow", Action = ["s3:PutObject"], Resource = "${aws_s3_bucket.trimbin_releases.arn}/*" },
    { Effect = "Allow", Action = ["ssm:SendCommand"], Resource = [aws_instance.trimbin.arn, "arn:aws:ssm:${var.region}::document/AWS-RunShellScript"] },
    { Effect = "Allow", Action = ["ssm:GetCommandInvocation"], Resource = "*" },
    { Effect = "Allow", Action = ["cloudfront:CreateInvalidation"], Resource = aws_cloudfront_distribution.trimbin_live.arn }
  ] })
}
output "instance_id" { value = aws_instance.trimbin.id }
output "deploy_role" { value = aws_iam_role.trimbin_github.arn }
output "api_repository" { value = aws_ecr_repository.trimbin["api"].repository_url }
output "web_repository" { value = aws_ecr_repository.trimbin["web"].repository_url }
output "release_bucket" { value = aws_s3_bucket.trimbin_releases.id }
output "backup_bucket" { value = aws_s3_bucket.trimbin_backups.id }
output "data_volume" { value = aws_ebs_volume.trimbin.id }
output "distribution_id" { value = aws_cloudfront_distribution.trimbin_live.id }
output "url" { value = "https://${var.domain}" }
