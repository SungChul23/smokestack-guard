terraform {
  backend "s3" {
    bucket       = "smokestack-tfstate-952900391026"
    key          = "stacks/tms-collection/terraform.tfstate"
    region       = "ap-northeast-2"
    use_lockfile = true
    encrypt      = true
  }
}
