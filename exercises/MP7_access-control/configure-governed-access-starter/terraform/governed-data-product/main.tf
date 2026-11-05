# governed-data-product — Terraform module (PROVIDED, READ-ONLY)
#
# This module packages ONE governed data product on the Trailhead Provisions platform.
# Your task: read this module and explain what it provisions and how the pieces enforce
# governance together. You do NOT run `terraform apply`.
#
# The shape to notice: a storage location (S3) -> a catalog table (Glue) -> fine-grained
# permissions (Lake Formation) -> a consumer identity (IAM role). That chain is exactly
# what you configured by hand in the notebook; this module makes it repeatable.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "product_name" {
  description = "Logical name of the data product, e.g. \"customer\"."
  type        = string
}

variable "domain" {
  description = "Owning domain, e.g. \"Customer Identity & Loyalty\"."
  type        = string
}

variable "pii_columns" {
  description = "Columns classified PII; Lake Formation will column-mask these by default."
  type        = list(string)
  default     = []
}

variable "data_lake_admin_arn" {
  description = "Principal that administers Lake Formation for this product."
  type        = string
}

# --- 1. Storage: the S3 location that physically holds the data product --------------
resource "aws_s3_bucket" "data" {
  bucket = "trailhead-${var.product_name}-data"
  tags = {
    Domain        = var.domain
    GovernedBy    = "lake-formation"
    DataProduct   = var.product_name
  }
}

# Register the location with Lake Formation so LF — not raw IAM/S3 — mediates access.
resource "aws_lakeformation_resource" "data" {
  arn      = aws_s3_bucket.data.arn
  role_arn = var.data_lake_admin_arn
}

# --- 2. Catalog: the Glue database + table that describe the data product ------------
resource "aws_glue_catalog_database" "db" {
  name = "trailhead"
}

resource "aws_glue_catalog_table" "table" {
  name          = var.product_name
  database_name = aws_glue_catalog_database.db.name
  table_type    = "EXTERNAL_TABLE"

  # Governance metadata lives on the table as parameters — the same owner/
  # classification/retention tags the MP2 catalog audit checks for.
  parameters = {
    owner          = "${var.domain}"
    classification = length(var.pii_columns) > 0 ? "PII" : "PUBLIC"
    retention      = "P7Y"
  }

  storage_descriptor {
    location = "s3://${aws_s3_bucket.data.bucket}/"
  }
}

# --- 3. Classification tag: an LF-Tag that drives tag-based access (LF-TBAC) ----------
resource "aws_lakeformation_lf_tag" "governed" {
  key    = "governed"
  values = ["true", "false"]
}

resource "aws_lakeformation_resource_lf_tag" "tag_table" {
  database {
    name = aws_glue_catalog_database.db.name
  }
  lf_tag {
    key   = aws_lakeformation_lf_tag.governed.key
    value = "true"
  }
}

# --- 4. Consumer identity: an IAM role that reaches data ONLY through Lake Formation --
# Note there is NO s3:GetObject on the data bucket. The only read path is LF-mediated
# Athena access — exactly the constraint the four persona roles operate under.
resource "aws_iam_role" "consumer" {
  name = "tp_${var.product_name}_consumer"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = var.data_lake_admin_arn }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "consumer" {
  role = aws_iam_role.consumer.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AthenaAndCatalogRead"
        Effect   = "Allow"
        Action   = ["athena:StartQueryExecution", "athena:GetQueryResults",
                    "glue:Get*", "lakeformation:GetDataAccess"]
        Resource = "*"
      },
      {
        Sid      = "ResultsBucketOnly"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "arn:aws:s3:::trailhead-athena-results/*"
      }
    ]
  })
}

# --- 5. The fine-grained grant: column-mask PII for this consumer by default ----------
resource "aws_lakeformation_permissions" "consumer_columns" {
  principal   = aws_iam_role.consumer.arn
  permissions = ["SELECT"]

  table_with_columns {
    database_name      = aws_glue_catalog_database.db.name
    name               = aws_glue_catalog_table.table.name
    excluded_column_names = var.pii_columns   # PII excluded -> column-level deny
  }
}

output "data_product_arn" {
  value = aws_glue_catalog_table.table.arn
}
