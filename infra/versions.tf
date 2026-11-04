terraform {
  required_version = ">= 1.16.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.69.1"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "2.8.1"
    }
  }

  # state는 지금 로컬 파일(infra/terraform.tfstate)에 둔다. 팀 계정으로 옮길 때 S3로 바꾼다.
}

# 자격 증명은 환경 변수 AWS_PROFILE(예: cholog)로 받는다. 코드에 계정을 박지 않는다.
provider "aws" {
  region = var.region

  default_tags {
    tags = {
      project    = var.name
      managed-by = "terraform"
    }
  }
}
