# =============================================================================
# Veridian Health — Medallion Lakehouse Governance Chain in Terraform (IaC)
# Storage (S3) -> Catalog (AWS Glue) -> Access Control (AWS Lake Formation)
# =============================================================================

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "lakehouse_database" {
  type    = string
  default = "veridian_lakehouse"
}

data "aws_caller_identity" "current" {}

# 1. Storage Layer — Medallion S3 Bucket (Bronze / Silver / Gold prefixes)
resource "aws_s3_bucket" "medallion_lakehouse" {
  bucket = "${data.aws_caller_identity.current.account_id}-veridian-lakehouse"
}

resource "aws_s3_bucket_server_side_encryption_configuration" "phi_encryption" {
  bucket = aws_s3_bucket.medallion_lakehouse.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# 2. Catalog Layer — AWS Glue Data Catalog Database
resource "aws_glue_catalog_database" "veridian" {
  name        = var.lakehouse_database
  description = "Veridian Health Medallion Lakehouse (HIPAA / GDPR / CMS eCQM)"
}

# 3. Access Control Layer — Register S3 with AWS Lake Formation & Define LF-Tags
resource "aws_lakeformation_resource" "medallion_storage" {
  arn                     = aws_s3_bucket.medallion_lakehouse.arn
  use_service_linked_role = true
}

resource "aws_lakeformation_lf_tag" "phi_governed" {
  key    = "phi_governed"
  values = ["true", "false"]
}

resource "aws_lakeformation_lf_tag" "medallion_zone" {
  key    = "medallion_zone"
  values = ["bronze", "silver", "gold"]
}

# 4. Healthcare Persona IAM Roles (Assumed via STS for Athena / Glue enforcement)
locals {
  healthcare_personas = toset([
    "vh_clinical_researcher",
    "vh_eu_care_coordinator",
    "vh_him_steward",
    "vh_hipaa_compliance_auditor",
  ])
}

resource "aws_iam_role" "persona" {
  for_each = local.healthcare_personas
  name     = each.value

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
    }]
  })
}
