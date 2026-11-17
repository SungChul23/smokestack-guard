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
      stack      = "tms-serving"
    }
  }
}

# CloudFront 인증서는 us-east-1에 있어야 한다.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      project    = "tms"
      managed_by = "terraform"
      stack      = "tms-serving"
    }
  }
}
