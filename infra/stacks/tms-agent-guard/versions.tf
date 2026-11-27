terraform {
  required_version = "~> 1.15.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "ap-northeast-2"

  default_tags {
    tags = {
      project    = "tms"
      managed_by = "terraform"
      stack      = "tms-agent-guard"
    }
  }
}

data "aws_caller_identity" "current" {}
